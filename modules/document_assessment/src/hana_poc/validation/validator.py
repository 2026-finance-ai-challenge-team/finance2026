"""Deterministic cross-document consistency checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from schemas import (
    ApplicationContext,
    ConsistencyParticipant,
    ConsistencyResult,
    DocumentType,
    ExtractedField,
    FieldStatus,
    RequirementStatus,
    StructuredDocument,
)


APPLICATION_CONTEXT_ID = "APPLICATION_CONTEXT"
COMPANY_NAME_MATCH = "COMPANY_NAME_MATCH"
BUSINESS_REGISTRATION_NUMBER_MATCH = "BUSINESS_REGISTRATION_NUMBER_MATCH"
REPRESENTATIVE_NAME_MATCH = "REPRESENTATIVE_NAME_MATCH"

VALUES_MATCH = "VALUES_MATCH"
KNOWN_VALUES_CONFLICT = "KNOWN_VALUES_CONFLICT"
FIELD_UNKNOWN = "FIELD_UNKNOWN"


@dataclass(frozen=True)
class _ComparisonValue:
    participant: ConsistencyParticipant
    normalized_value: Optional[str]
    evidence_document_id: Optional[str]


def validate_consistency(
    documents: Sequence[StructuredDocument], application_context: ApplicationContext
) -> list[ConsistencyResult]:
    """Evaluate the initial deterministic checks without business-rule decisions."""

    return [
        _validate_company_name(documents, application_context),
        _validate_business_registration_number(documents, application_context),
        _validate_representative_name(documents, application_context),
    ]


def _validate_company_name(
    documents: Sequence[StructuredDocument], application_context: ApplicationContext
) -> ConsistencyResult:
    comparisons = _document_comparisons(documents, "corporation_name")
    context_comparison = _context_comparison(
        "corporation_name", application_context.corporation_name
    )
    if context_comparison is not None:
        comparisons.append(context_comparison)
    return _evaluate(COMPANY_NAME_MATCH, comparisons)


def _validate_business_registration_number(
    documents: Sequence[StructuredDocument], application_context: ApplicationContext
) -> ConsistencyResult:
    comparisons = _document_comparisons(
        documents, "business_registration_number"
    )
    context_comparison = _context_comparison(
        "business_registration_number",
        application_context.business_registration_number,
    )
    if context_comparison is not None:
        comparisons.append(context_comparison)
    return _evaluate(BUSINESS_REGISTRATION_NUMBER_MATCH, comparisons)


def _validate_representative_name(
    documents: Sequence[StructuredDocument], application_context: ApplicationContext
) -> ConsistencyResult:
    representative_documents = [
        document
        for document in documents
        if document.document_type
        in {
            DocumentType.BUSINESS_REGISTRATION_CERTIFICATE,
            DocumentType.CORPORATE_REGISTRY,
        }
    ]
    required_document_types = {
        DocumentType.BUSINESS_REGISTRATION_CERTIFICATE,
        DocumentType.CORPORATE_REGISTRY,
    }
    present_document_types = {
        document.document_type for document in representative_documents
    }
    comparisons = _document_comparisons(
        representative_documents, "representative_name"
    )
    context_comparison = _context_comparison(
        "representative_name", application_context.representative_name
    )
    if context_comparison is not None:
        comparisons.append(context_comparison)
    return _evaluate(
        REPRESENTATIVE_NAME_MATCH,
        comparisons,
        required_values_missing=present_document_types != required_document_types,
    )


def _document_comparisons(
    documents: Iterable[StructuredDocument], field_name: str
) -> list[_ComparisonValue]:
    comparisons: list[_ComparisonValue] = []
    for document in documents:
        field = document.fields.get(field_name)
        if field is None:
            continue
        comparisons.append(_field_comparison(document.document_id, field_name, field))
    return comparisons


def _field_comparison(
    document_id: str, field_name: str, field: ExtractedField
) -> _ComparisonValue:
    return _ComparisonValue(
        participant=ConsistencyParticipant(
            document_id=document_id,
            field=field_name,
            value=field.value,
        ),
        normalized_value=(
            field.normalized_value if field.status is FieldStatus.KNOWN else None
        ),
        evidence_document_id=document_id,
    )


def _context_comparison(
    field_name: str, value: Optional[str]
) -> Optional[_ComparisonValue]:
    if value is None:
        return None
    return _ComparisonValue(
        participant=ConsistencyParticipant(
            document_id=APPLICATION_CONTEXT_ID,
            field=field_name,
            value=value,
        ),
        normalized_value=_normalize_context_value(field_name, value),
        evidence_document_id=None,
    )


def _normalize_context_value(field_name: str, value: str) -> str:
    """Apply only the exact canonical form already defined for context inputs.

    Structured document fields retain their extraction-produced normalized values.
    Application context has no normalized-value contract, so only corporation
    names need the same explicit whitespace and ``㈜`` canonicalization to be
    compared with extracted values. No similarity or approximate matching occurs.
    """

    if field_name == "corporation_name":
        return "".join(value.replace("㈜", "주식회사").split())
    return value


def _evaluate(
    check_id: str,
    comparisons: Sequence[_ComparisonValue],
    *,
    required_values_missing: bool = False,
) -> ConsistencyResult:
    known_values = [
        comparison.normalized_value
        for comparison in comparisons
        if comparison.normalized_value is not None
    ]
    has_unknown_value = required_values_missing or any(
        comparison.normalized_value is None for comparison in comparisons
    )
    evidence_document_ids = _unique_document_ids(
        comparison.evidence_document_id for comparison in comparisons
    )

    if len(known_values) >= 2 and len(set(known_values)) > 1:
        status = RequirementStatus.UNSATISFIED
        reason_code = KNOWN_VALUES_CONFLICT
    elif has_unknown_value or len(known_values) < 2:
        status = RequirementStatus.UNKNOWN
        reason_code = FIELD_UNKNOWN
    else:
        status = RequirementStatus.SATISFIED
        reason_code = VALUES_MATCH

    return ConsistencyResult(
        check_id=check_id,
        status=status,
        participants=[comparison.participant for comparison in comparisons],
        reason_code=reason_code,
        evidence_document_ids=evidence_document_ids,
    )


def _unique_document_ids(document_ids: Iterable[Optional[str]]) -> list[str]:
    unique_ids: list[str] = []
    for document_id in document_ids:
        if document_id is not None and document_id not in unique_ids:
            unique_ids.append(document_id)
    return unique_ids
