"""Generic deterministic evaluation of typed declarative requirements."""

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional, Sequence

from schemas import (
    ApplicationContext,
    ConsistencyResult,
    DocumentType,
    FieldStatus,
    RequirementResult,
    RequirementStatus,
    StructuredDocument,
)

from .config import (
    ConsistencyCheckRule,
    DocumentPresenceRule,
    RequirementConfiguration,
    RuleConfiguration,
)


REQUIRED_DOCUMENT_PRESENT = "REQUIRED_DOCUMENT_PRESENT"
REQUIRED_DOCUMENT_MISSING = "REQUIRED_DOCUMENT_MISSING"
DOCUMENT_TYPE_UNRESOLVED = "DOCUMENT_TYPE_UNRESOLVED"
DOCUMENT_EXPIRED = "DOCUMENT_EXPIRED"
FIELD_UNKNOWN = "FIELD_UNKNOWN"


def evaluate_requirements(
    rule_configuration: RuleConfiguration,
    documents: Sequence[StructuredDocument],
    consistency_results: Sequence[ConsistencyResult],
    application_context: ApplicationContext,
) -> list[RequirementResult]:
    """Evaluate YAML-declared conditions without workflow-specific branches.

    Freshness is evaluated only when it is attached to a document-presence rule
    in the typed YAML configuration. The supplied application date is the sole
    time reference; no system clock is consulted.
    """

    consistency_by_check_id = {
        result.check_id: result for result in consistency_results
    }
    return [
        _evaluate_requirement(
            requirement,
            documents,
            consistency_by_check_id,
            application_context,
        )
        for requirement in rule_configuration.requirements
    ]


def _evaluate_requirement(
    requirement: RequirementConfiguration,
    documents: Sequence[StructuredDocument],
    consistency_by_check_id: dict[str, ConsistencyResult],
    application_context: ApplicationContext,
) -> RequirementResult:
    if requirement.document_presence is not None:
        return _evaluate_document_presence(
            requirement,
            requirement.document_presence,
            documents,
            application_context,
        )
    if requirement.consistency_check is not None:
        return _evaluate_consistency_check(
            requirement,
            requirement.consistency_check,
            consistency_by_check_id,
        )
    raise AssertionError("validated requirement must have one supported rule type")


def _evaluate_document_presence(
    requirement: RequirementConfiguration,
    rule: DocumentPresenceRule,
    documents: Sequence[StructuredDocument],
    application_context: ApplicationContext,
) -> RequirementResult:
    accepted_documents = [
        document
        for document in documents
        if document.document_type in rule.any_of
    ]
    relevant_unresolved_documents = _relevant_unresolved_documents(documents, rule)

    if requirement.freshness is not None:
        return _evaluate_fresh_document_presence(
            requirement,
            accepted_documents,
            relevant_unresolved_documents,
            application_context,
            requirement.freshness.max_age_days,
        )

    if accepted_documents:
        return RequirementResult(
            requirement_id=requirement.id,
            status=RequirementStatus.SATISFIED,
            blocking=requirement.blocking,
            reason_code=REQUIRED_DOCUMENT_PRESENT,
            evidence=_unique_document_ids(accepted_documents),
        )
    if relevant_unresolved_documents:
        return _unresolved_document_result(
            requirement,
            relevant_unresolved_documents,
        )
    return RequirementResult(
        requirement_id=requirement.id,
        status=RequirementStatus.UNSATISFIED,
        blocking=requirement.blocking,
        reason_code=REQUIRED_DOCUMENT_MISSING,
        evidence=[],
    )


def _evaluate_fresh_document_presence(
    requirement: RequirementConfiguration,
    accepted_documents: Sequence[StructuredDocument],
    relevant_unresolved_documents: Sequence[StructuredDocument],
    application_context: ApplicationContext,
    max_age_days: int,
) -> RequirementResult:
    if not accepted_documents:
        if relevant_unresolved_documents:
            return _unresolved_document_result(
                requirement,
                relevant_unresolved_documents,
            )
        return RequirementResult(
            requirement_id=requirement.id,
            status=RequirementStatus.UNSATISFIED,
            blocking=requirement.blocking,
            reason_code=REQUIRED_DOCUMENT_MISSING,
            evidence=[],
        )

    if application_context.application_date is None:
        return _field_unknown_result(requirement, accepted_documents)

    fresh_documents: list[StructuredDocument] = []
    unknown_date_documents: list[StructuredDocument] = []
    for document in accepted_documents:
        issue_date = _known_issue_date(document)
        if issue_date is None:
            unknown_date_documents.append(document)
        elif (application_context.application_date - issue_date).days <= max_age_days:
            fresh_documents.append(document)

    if fresh_documents:
        return RequirementResult(
            requirement_id=requirement.id,
            status=RequirementStatus.SATISFIED,
            blocking=requirement.blocking,
            reason_code=REQUIRED_DOCUMENT_PRESENT,
            evidence=_unique_document_ids(fresh_documents),
        )
    if unknown_date_documents:
        return _field_unknown_result(requirement, unknown_date_documents)
    if relevant_unresolved_documents:
        return _unresolved_document_result(requirement, relevant_unresolved_documents)
    return RequirementResult(
        requirement_id=requirement.id,
        status=RequirementStatus.UNSATISFIED,
        blocking=requirement.blocking,
        reason_code=DOCUMENT_EXPIRED,
        evidence=_unique_document_ids(accepted_documents),
    )


def _relevant_unresolved_documents(
    documents: Sequence[StructuredDocument], rule: DocumentPresenceRule
) -> list[StructuredDocument]:
    accepted_document_types = set(rule.any_of)
    return [
        document
        for document in documents
        if document.document_type is DocumentType.UNKNOWN
        and accepted_document_types.intersection(
            document.classification.candidate_document_types
        )
    ]


def _known_issue_date(document: StructuredDocument) -> Optional[date]:
    issue_date = document.issue_date
    if (
        issue_date.status is not FieldStatus.KNOWN
        or issue_date.normalized_value is None
    ):
        return None
    try:
        return date.fromisoformat(issue_date.normalized_value)
    except ValueError:
        return None


def _unresolved_document_result(
    requirement: RequirementConfiguration,
    documents: Sequence[StructuredDocument],
) -> RequirementResult:
    return RequirementResult(
        requirement_id=requirement.id,
        status=RequirementStatus.UNKNOWN,
        blocking=requirement.blocking,
        reason_code=DOCUMENT_TYPE_UNRESOLVED,
        evidence=_unique_document_ids(documents),
    )


def _field_unknown_result(
    requirement: RequirementConfiguration,
    documents: Sequence[StructuredDocument],
) -> RequirementResult:
    return RequirementResult(
        requirement_id=requirement.id,
        status=RequirementStatus.UNKNOWN,
        blocking=requirement.blocking,
        reason_code=FIELD_UNKNOWN,
        evidence=_unique_document_ids(documents),
    )


def _evaluate_consistency_check(
    requirement: RequirementConfiguration,
    rule: ConsistencyCheckRule,
    consistency_by_check_id: dict[str, ConsistencyResult],
) -> RequirementResult:
    consistency_result = consistency_by_check_id.get(rule.check_id)
    if consistency_result is None:
        return RequirementResult(
            requirement_id=requirement.id,
            status=RequirementStatus.UNKNOWN,
            blocking=requirement.blocking,
            reason_code=FIELD_UNKNOWN,
            evidence=[],
        )

    return RequirementResult(
        requirement_id=requirement.id,
        status=consistency_result.status,
        blocking=requirement.blocking,
        reason_code=consistency_result.reason_code,
        evidence=_unique_ids(consistency_result.evidence_document_ids),
    )


def _unique_document_ids(documents: Iterable[StructuredDocument]) -> list[str]:
    return _unique_ids(document.document_id for document in documents)


def _unique_ids(values: Iterable[str]) -> list[str]:
    unique_values: list[str] = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)
    return unique_values
