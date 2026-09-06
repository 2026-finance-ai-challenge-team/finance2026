"""PostgreSQL-backed deterministic policy evaluation for analyzed documents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from modules.policy_db.runtime import connect_database
from modules.policy_db.repository import find_requirements, list_document_signatures

from .contracts import (
    AcquisitionGuide,
    DocumentResult,
    DocumentStatus,
    OverallStatus,
    PreparationGuide,
    RequirementBundleResult,
    RequirementResult,
    SourceReference,
    TaskRequirementDocument,
    TaskRequirementsResponse,
    TaskSummary,
)


_BUNDLE_COMPARISON_FIELDS: dict[str, tuple[str, ...]] = {
    "management_fee_and_resident_copy": ("subject_name", "address"),
    "employment_contract_and_employer_registration": ("organization_name",),
}

# A document signature's source URL explains where a bank requires a document;
# it is not necessarily where a customer can obtain it.  Keep shared issuer
# routes separate so a policy from one bank is never presented as another
# bank's issuance route.
_ISSUER_ACQUISITION_FALLBACKS: dict[str, dict[str, object]] = {
    "business_registration_certificate": {
        "title": "국세청 홈택스에서 사업자등록 관련 증명 확인",
        "channel": "tax_online_or_offline",
        "description": "국세청 홈택스 또는 관할 세무서에서 사업자등록 관련 증명과 재발급 방법을 확인하세요.",
        "steps": [
            "국세청 홈택스에서 사업자등록 관련 민원을 찾습니다.",
            "사업자 정보와 제출처가 요구한 증명 형태를 확인합니다.",
            "은행 안내에 맞는 원본 또는 사본을 준비합니다.",
        ],
        "url": "https://www.hometax.go.kr/",
        "action_label": "국세청 홈택스 열기",
        "source_title": "국세청 홈택스",
        "source_url": "https://www.hometax.go.kr/",
        "verified": True,
    },
}


def _acquisition_for(rule: dict, signature: dict) -> dict:
    """Use a task/issuer route, never a shared document policy source as a route."""
    payload = rule.get("acquisition") or signature.get("acquisition")
    if not payload:
        payload = _ISSUER_ACQUISITION_FALLBACKS.get(rule["doc_type"], {})
    payload = dict(payload)
    # Catalog seeds historically used source_url for issuer routes.  It is safe
    # to make that link actionable only when it came from an acquisition block.
    if not payload.get("url") and payload.get("source_url"):
        payload["url"] = payload["source_url"]
    return payload


class PolicyDataError(RuntimeError):
    """Raised when a task cannot be backed by usable versioned policy data."""


class PolicySelectionRequired(PolicyDataError):
    """Raised when a purpose or route must be selected before policy lookup."""


@dataclass(frozen=True)
class PolicyContext:
    policy: dict
    signatures: list[dict]


@dataclass(frozen=True)
class PolicyAssessment:
    overall_status: OverallStatus
    requirements: list[RequirementResult]
    warnings: list[str]


class PostgreSQLPolicyService:
    """Read one published policy and evaluate its alternative document bundles."""

    def __init__(self, database_url: str | None) -> None:
        self._database_url = database_url

    def load(self, task: TaskSummary) -> PolicyContext:
        if not self._database_url:
            raise PolicyDataError("PostgreSQL database URL is missing")

        try:
            connection = connect_database(self._database_url)
        except Exception as error:
            raise PolicyDataError("PostgreSQL connection is unavailable") from error
        try:
            policy = find_requirements(
                connection,
                bank_code=task.bank_code,
                policy_key=task.policy_key,
                channel=task.channel,
                visitor_type=task.visitor_type,
                purpose_code=task.purpose_code,
                operation_code=task.operation_code,
            )
            signatures = list_document_signatures(connection)
        except ValueError as error:
            raise PolicySelectionRequired(str(error)) from error
        except LookupError as error:
            raise PolicyDataError(str(error)) from error
        except Exception as error:
            raise PolicyDataError("PostgreSQL policy query failed") from error
        finally:
            connection.close()

        if policy["task_id"] != task.task_id:
            raise PolicyDataError(
                f"task identity mismatch: {task.task_id} != {policy['task_id']}"
            )
        if not policy["requirement_sets"]:
            raise PolicyDataError(f"no requirements configured for {task.task_id}")
        return PolicyContext(policy=policy, signatures=signatures)

    def describe(
        self,
        *,
        context: PolicyContext,
        task: TaskSummary,
    ) -> TaskRequirementsResponse:
        """Return the no-upload preparation path from the same policy snapshot."""
        signatures = {
            signature["doc_type"]: signature for signature in context.signatures
        }
        documents: list[TaskRequirementDocument] = []
        preparations: dict[str, PreparationGuide] = {}
        for requirement_set in context.policy["requirement_sets"]:
            source_payload = requirement_set["source"]
            source = SourceReference(
                title=source_payload.get("title"),
                url=source_payload.get("url"),
                as_of=task.as_of,
                last_checked=source_payload.get("checked_at"),
                verified=task.verified
                and context.policy["policy_status"] == "published",
            )
            for rule in requirement_set["documents"]:
                signature = signatures.get(rule["doc_type"], {})
                acquisition_payload = _acquisition_for(rule, signature)
                issuer = signature.get("issuer") or "발급·제공 기관"
                acquisition_source = SourceReference(
                    title=acquisition_payload.get("source_title") or source.title,
                    url=acquisition_payload.get("source_url") or source.url,
                    last_checked=acquisition_payload.get("last_checked")
                    or source.last_checked,
                    verified=bool(acquisition_payload.get("verified", False)),
                )
                documents.append(
                    TaskRequirementDocument(
                        requirement_code=requirement_set["requirement_code"],
                        requirement_level=requirement_set["requirement_level"],
                        choice_group=rule.get("choice_group"),
                        bundle_code=rule.get("bundle_code"),
                        doc_type=rule["doc_type"],
                        label_ko=rule.get("label_ko")
                        or signature.get("label_ko")
                        or rule["doc_type"],
                        original_required=rule.get("original_required"),
                        issued_within_days=rule.get("issued_within_days"),
                        submission_method=rule["submission_method"],
                        submission_label={
                            "original": "원본 지참",
                            "original_or_copy": "원본 또는 사본",
                            "photo_or_pdf": "사진 또는 PDF 제출",
                            "printed_original_photo": "원본 출력 후 사진 촬영",
                            "auto_submit": "공식 제출 경로",
                        }.get(rule["submission_method"], rule["submission_method"]),
                        notes=rule.get("notes"),
                        acquisition=AcquisitionGuide(
                            title=acquisition_payload.get("title")
                            or f"{issuer}에서 서류 확보",
                            channel=acquisition_payload.get("channel")
                            or "issuer_direct",
                            description=acquisition_payload.get("description")
                            or "발급·제공 기관에서 최신 서류의 발급 방법을 확인하세요.",
                            steps=acquisition_payload.get("steps") or [],
                            url=acquisition_payload.get("url"),
                            action_label=acquisition_payload.get("action_label"),
                            source=acquisition_source,
                        ),
                        source=source,
                    )
                )
            for item in requirement_set["preparations"]:
                preparations[item["code"]] = PreparationGuide(
                    code=item["code"],
                    label_ko=item.get("label_ko")
                    or item.get("name_ko")
                    or item["code"],
                    notes=item.get("notes"),
                )
        warnings = [
            "공개된 요건을 기준으로 안내하며 은행이 추가 자료를 요청할 수 있습니다."
        ]
        if not task.verified or context.policy["policy_status"] != "published":
            warnings.append("공식 확인이 끝나지 않은 정책은 검토용 안내로만 사용합니다.")
        return TaskRequirementsResponse(
            task=task,
            documents=documents,
            preparations=list(preparations.values()),
            warnings=warnings,
        )

    def assess(
        self,
        *,
        context: PolicyContext,
        task: TaskSummary,
        documents: list[DocumentResult],
        comparison_tokens: dict[str, dict[str, str]] | None = None,
    ) -> PolicyAssessment:
        policy = context.policy
        requirements: list[RequirementResult] = []
        for requirement_set in policy["requirement_sets"]:
            requirements.extend(
                _evaluate_requirement_set(
                    requirement_set=requirement_set,
                    documents=documents,
                    task=task,
                    policy_status=policy["policy_status"],
                    comparison_tokens=comparison_tokens,
                )
            )

        blocking = [requirement for requirement in requirements if requirement.blocking]
        has_unknown_document = any(
            document.doc_type is None
            and document.status is DocumentStatus.REVIEW_REQUIRED
            for document in documents
        )
        policy_verified = task.verified and policy["policy_status"] == "published"

        if not policy_verified:
            overall_status = OverallStatus.REVIEW_REQUIRED
        elif any(
            requirement.status is DocumentStatus.REVIEW_REQUIRED
            for requirement in blocking
        ):
            overall_status = OverallStatus.REVIEW_REQUIRED
        elif has_unknown_document and any(
            requirement.status is not DocumentStatus.READY for requirement in blocking
        ):
            overall_status = OverallStatus.REVIEW_REQUIRED
        elif any(
            requirement.status
            in {DocumentStatus.MISSING, DocumentStatus.EXPIRED, DocumentStatus.MISMATCH}
            for requirement in blocking
        ):
            overall_status = OverallStatus.ACTION_REQUIRED
        elif blocking and all(
            requirement.status is DocumentStatus.READY for requirement in blocking
        ):
            overall_status = OverallStatus.READY
        else:
            overall_status = OverallStatus.REVIEW_REQUIRED

        warnings = [
            "공개된 요건을 기준으로 사전 점검하며 은행의 심사나 해제 승인을 보장하지 않습니다."
        ]
        if not policy_verified:
            warnings.append(
                "정책 버전이 공식 출처로 게시된 상태가 아니어서 사용자 확인이 필요합니다."
            )
        if any(
            document.reason_code == "UNVERIFIED_DOCUMENT_SIGNATURE"
            for document in documents
        ):
            warnings.append(
                "인정 서류명은 공식 확인됐지만 해당 문서의 자동 식별 패턴은 표본 검증 전이므로 확인이 필요합니다."
            )
        return PolicyAssessment(
            overall_status=overall_status,
            requirements=requirements,
            warnings=warnings,
        )


def _evaluate_requirement_set(
    *,
    requirement_set: dict,
    documents: list[DocumentResult],
    task: TaskSummary,
    policy_status: str,
    comparison_tokens: dict[str, dict[str, str]] | None = None,
) -> list[RequirementResult]:
    grouped_rules: dict[str, list[dict]] = {}
    for rule in requirement_set["documents"]:
        group_code = rule.get("choice_group") or f"required_{rule['doc_type']}"
        grouped_rules.setdefault(group_code, []).append(rule)

    source_payload = requirement_set["source"]
    source = SourceReference(
        title=source_payload["title"],
        url=source_payload["url"],
        as_of=task.as_of,
        last_checked=date.fromisoformat(source_payload["checked_at"]),
        verified=task.verified and policy_status == "published",
    )

    results: list[RequirementResult] = []
    for group_code, rules in grouped_rules.items():
        bundles = _build_bundles(
            rules=rules,
            documents=documents,
            comparison_tokens=comparison_tokens,
        )
        matched = next(
            (bundle for bundle in bundles if bundle.status is DocumentStatus.READY),
            None,
        )
        review = next(
            (
                bundle
                for bundle in bundles
                if bundle.status is DocumentStatus.REVIEW_REQUIRED
            ),
            None,
        )
        expired = next(
            (bundle for bundle in bundles if bundle.status is DocumentStatus.EXPIRED),
            None,
        )
        mismatch = next(
            (bundle for bundle in bundles if bundle.status is DocumentStatus.MISMATCH),
            None,
        )

        if matched is not None:
            status = DocumentStatus.READY
            reason_code = "ACCEPTED_DOCUMENT_BUNDLE_COMPLETE"
            evidence_ids = matched.evidence_document_ids
            matched_bundle_code = matched.bundle_code
        elif review is not None:
            status = DocumentStatus.REVIEW_REQUIRED
            reason_code = "DOCUMENT_BUNDLE_NEEDS_REVIEW"
            evidence_ids = review.evidence_document_ids
            matched_bundle_code = review.bundle_code
        elif expired is not None:
            status = DocumentStatus.EXPIRED
            reason_code = "DOCUMENT_BUNDLE_EXPIRED"
            evidence_ids = expired.evidence_document_ids
            matched_bundle_code = expired.bundle_code
        elif mismatch is not None:
            status = DocumentStatus.MISMATCH
            reason_code = "DOCUMENT_BUNDLE_INFORMATION_MISMATCH"
            evidence_ids = mismatch.evidence_document_ids
            matched_bundle_code = mismatch.bundle_code
        else:
            status = DocumentStatus.MISSING
            reason_code = "NO_ACCEPTED_DOCUMENT_BUNDLE_COMPLETE"
            evidence_ids = []
            matched_bundle_code = None

        results.append(
            RequirementResult(
                requirement_id=f"{requirement_set['requirement_code']}:{group_code}",
                label_ko="한도계좌 해제 인정 증빙",
                status=status,
                blocking=requirement_set["requirement_level"]
                in {"official_minimum", "official_required"},
                reason_code=reason_code,
                evidence_document_ids=evidence_ids,
                matched_bundle_code=matched_bundle_code,
                bundles=bundles,
                source=source,
            )
        )
    return results


def _build_bundles(
    *,
    rules: list[dict],
    documents: list[DocumentResult],
    comparison_tokens: dict[str, dict[str, str]] | None = None,
) -> list[RequirementBundleResult]:
    rule_bundles: dict[str, list[dict]] = {}
    for rule in rules:
        bundle_code = rule.get("bundle_code") or rule["doc_type"]
        rule_bundles.setdefault(bundle_code, []).append(rule)

    documents_by_type: dict[str, list[DocumentResult]] = {}
    for document in documents:
        if document.doc_type is not None:
            documents_by_type.setdefault(document.doc_type, []).append(document)

    results: list[RequirementBundleResult] = []
    for bundle_code, bundle_rules in rule_bundles.items():
        expected_types = [rule["doc_type"] for rule in bundle_rules]
        missing_types: list[str] = []
        evidence_ids: list[str] = []
        evidence_statuses: list[DocumentStatus] = []
        selected_documents: list[DocumentResult] = []
        labels: list[str] = []

        for rule in bundle_rules:
            doc_type = rule["doc_type"]
            labels.append(rule["label_ko"])
            candidates = documents_by_type.get(doc_type, [])
            selected = _select_best_document(candidates)
            if selected is None:
                missing_types.append(doc_type)
                continue
            evidence_ids.append(selected.document_id)
            evidence_statuses.append(selected.status)
            selected_documents.append(selected)

        if missing_types:
            status = DocumentStatus.MISSING
        elif (
            comparison_status := _bundle_comparison_status(
                bundle_code=bundle_code,
                documents=selected_documents,
                comparison_tokens=comparison_tokens,
            )
        ) is not None:
            status = comparison_status
        elif DocumentStatus.REVIEW_REQUIRED in evidence_statuses:
            status = DocumentStatus.REVIEW_REQUIRED
        elif DocumentStatus.EXPIRED in evidence_statuses:
            status = DocumentStatus.EXPIRED
        elif DocumentStatus.MISMATCH in evidence_statuses:
            status = DocumentStatus.MISMATCH
        elif evidence_statuses and all(
            status is DocumentStatus.READY for status in evidence_statuses
        ):
            status = DocumentStatus.READY
        else:
            status = DocumentStatus.REVIEW_REQUIRED

        results.append(
            RequirementBundleResult(
                bundle_code=bundle_code,
                label_ko=" + ".join(labels),
                status=status,
                document_types=expected_types,
                missing_document_types=missing_types,
                evidence_document_ids=evidence_ids,
            )
        )
    return results


def _bundle_comparison_status(
    *,
    bundle_code: str,
    documents: list[DocumentResult],
    comparison_tokens: dict[str, dict[str, str]] | None,
) -> DocumentStatus | None:
    fields = _BUNDLE_COMPARISON_FIELDS.get(bundle_code)
    if not fields or comparison_tokens is None:
        return None

    for field in fields:
        values = [
            (comparison_tokens.get(document.document_id) or {}).get(field)
            for document in documents
        ]
        if any(value is None for value in values):
            return DocumentStatus.REVIEW_REQUIRED
        if len(set(values)) > 1:
            return DocumentStatus.MISMATCH
    return None


def _select_best_document(
    candidates: list[DocumentResult],
) -> DocumentResult | None:
    priority = {
        DocumentStatus.READY: 0,
        DocumentStatus.REVIEW_REQUIRED: 1,
        DocumentStatus.EXPIRED: 2,
        DocumentStatus.MISMATCH: 3,
        DocumentStatus.MISSING: 4,
        DocumentStatus.UNNECESSARY: 5,
    }
    return min(candidates, key=lambda item: priority[item.status], default=None)
