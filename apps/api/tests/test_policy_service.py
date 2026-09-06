from __future__ import annotations

import json
from pathlib import Path

import pytest

from proofbridge_api.catalog import TaskCatalog
from proofbridge_api.contracts import (
    DocumentResult,
    DocumentStatus,
    OverallStatus,
)
from proofbridge_api.policy_service import (
    PolicyContext,
    PolicyDataError,
    PostgreSQLPolicyService,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
TASK_ID = "kakaobank.limit_account_release"


def _service_and_task():
    task = TaskCatalog(REPO_ROOT).get_task(TASK_ID)
    seed = json.loads(
        (REPO_ROOT / "data" / "seeds" / "kakaobank_limit_release.json").read_text(
            encoding="utf-8"
        )
    )
    source = seed["sources"][0]
    requirement_sets = seed["requirement_sets"]
    labels = {item["doc_type"]: item["label_ko"] for item in seed["documents"]}
    for requirement_set in requirement_sets:
        requirement_set["source"] = {
            "title": source["title"],
            "url": source["url"],
            "checked_at": source["checked_at"],
        }
        for document in requirement_set["documents"]:
            document["label_ko"] = labels.get(
                document["doc_type"], document["doc_type"]
            )
    context = PolicyContext(
        policy={
            "task_id": TASK_ID,
            "policy_status": seed["policy"]["status"],
            "requirement_sets": requirement_sets,
        },
        signatures=[],
    )
    service = PostgreSQLPolicyService(database_url=None)
    return service, task, context


def _document(
    document_id: str,
    doc_type: str,
    status: DocumentStatus = DocumentStatus.READY,
) -> DocumentResult:
    return DocumentResult(
        document_id=document_id,
        source_name=f"{document_id}.pdf",
        doc_type=doc_type,
        label_ko=doc_type,
        confidence=0.99,
        status=status,
        reason_code="TEST_DOCUMENT",
        needs_user_confirm=status is DocumentStatus.REVIEW_REQUIRED,
    )


def _assess(
    documents: list[DocumentResult],
    comparison_tokens: dict[str, dict[str, str]] | None = None,
):
    service, task, context = _service_and_task()
    return service.assess(
        context=context,
        task=task,
        documents=documents,
        comparison_tokens=comparison_tokens,
    )


def test_single_utility_bill_bundle_is_ready() -> None:
    result = _assess([_document("f01", "utility_bill")])

    assert result.overall_status is OverallStatus.READY
    requirement = result.requirements[0]
    assert requirement.status is DocumentStatus.READY
    assert requirement.matched_bundle_code == "utility_bill"
    assert requirement.evidence_document_ids == ["f01"]


def test_management_fee_notice_alone_reports_resident_copy_missing() -> None:
    result = _assess([_document("f01", "management_fee_notice")])

    assert result.overall_status is OverallStatus.ACTION_REQUIRED
    requirement = result.requirements[0]
    bundle = next(
        item
        for item in requirement.bundles
        if item.bundle_code == "management_fee_and_resident_copy"
    )
    assert bundle.status is DocumentStatus.MISSING
    assert bundle.missing_document_types == ["resident_registration_copy"]


def test_management_fee_and_resident_copy_bundle_is_ready() -> None:
    result = _assess(
        [
            _document("f01", "management_fee_notice"),
            _document("f02", "resident_registration_copy"),
        ]
    )

    assert result.overall_status is OverallStatus.READY
    assert (
        result.requirements[0].matched_bundle_code
        == "management_fee_and_resident_copy"
    )
    assert result.requirements[0].evidence_document_ids == ["f01", "f02"]


def test_employment_contract_alone_reports_employer_registration_missing() -> None:
    result = _assess([_document("f01", "employment_contract")])

    assert result.overall_status is OverallStatus.ACTION_REQUIRED
    bundle = next(
        item
        for item in result.requirements[0].bundles
        if item.bundle_code == "employment_contract_and_employer_registration"
    )
    assert bundle.missing_document_types == ["business_registration_certificate"]


def test_complete_but_unverified_classification_requires_review() -> None:
    result = _assess(
        [
            _document(
                "f01",
                "utility_bill",
                status=DocumentStatus.REVIEW_REQUIRED,
            )
        ]
    )

    assert result.overall_status is OverallStatus.REVIEW_REQUIRED
    assert result.requirements[0].status is DocumentStatus.REVIEW_REQUIRED
    assert result.requirements[0].matched_bundle_code == "utility_bill"


def test_management_bundle_with_different_subject_is_mismatch() -> None:
    documents = [
        _document("f01", "management_fee_notice"),
        _document("f02", "resident_registration_copy"),
    ]
    result = _assess(
        documents,
        comparison_tokens={
            "f01": {"subject_name": "person-a", "address": "address-same"},
            "f02": {"subject_name": "person-b", "address": "address-same"},
        },
    )

    assert result.overall_status is OverallStatus.ACTION_REQUIRED
    requirement = result.requirements[0]
    assert requirement.status is DocumentStatus.MISMATCH
    assert requirement.reason_code == "DOCUMENT_BUNDLE_INFORMATION_MISMATCH"
    assert requirement.matched_bundle_code == "management_fee_and_resident_copy"


def test_complete_bundle_with_missing_comparison_field_requires_review() -> None:
    documents = [
        _document("f01", "management_fee_notice"),
        _document("f02", "resident_registration_copy"),
    ]
    result = _assess(
        documents,
        comparison_tokens={
            "f01": {"subject_name": "person-same"},
            "f02": {"subject_name": "person-same", "address": "address-same"},
        },
    )

    assert result.overall_status is OverallStatus.REVIEW_REQUIRED
    assert result.requirements[0].status is DocumentStatus.REVIEW_REQUIRED


def test_no_upload_description_contains_all_document_paths_and_links() -> None:
    service, task, context = _service_and_task()

    result = service.describe(context=context, task=task)

    assert len(result.documents) == 8
    assert {item.bundle_code for item in result.documents} >= {
        "utility_bill",
        "management_fee_and_resident_copy",
        "employment_contract_and_employer_registration",
    }
    assert all(item.source.url for item in result.documents)
    assert any(item.acquisition.url for item in result.documents)


def test_shared_document_policy_source_is_not_used_as_an_issuance_link() -> None:
    service, task, _ = _service_and_task()
    context = PolicyContext(
        policy={
            "task_id": TASK_ID,
            "policy_status": "published",
            "requirement_sets": [
                {
                    "requirement_code": "ibk.corporate.required",
                    "requirement_level": "official_required",
                    "source": {
                        "title": "IBK기업은행 기업인터넷뱅킹 안내",
                        "url": "https://mybank.ibk.co.kr/",
                        "checked_at": "2026-09-07",
                    },
                    "documents": [
                        {
                            "doc_type": "business_registration_certificate",
                            "submission_method": "original_or_copy",
                        }
                    ],
                    "preparations": [],
                }
            ],
        },
        signatures=[
            {
                "doc_type": "business_registration_certificate",
                "label_ko": "사업자등록증",
                "issuer": "국세청",
                # This mirrors the legacy shared signature that originated
                # from a Hana policy rather than an issuer acquisition route.
                "source_url": "https://www.hanabank.com/legacy-policy",
            }
        ],
    )

    result = service.describe(context=context, task=task)

    assert result.documents[0].acquisition.url == "https://www.hometax.go.kr/"
    assert "hanabank" not in result.documents[0].acquisition.url


def test_database_connection_failure_is_exposed_as_policy_data_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, task, _ = _service_and_task()
    service = PostgreSQLPolicyService("postgresql://invalid")
    monkeypatch.setattr(
        "proofbridge_api.policy_service.connect_database",
        lambda _database_url: (_ for _ in ()).throw(RuntimeError("connection failed")),
    )

    with pytest.raises(PolicyDataError, match="connection is unavailable"):
        service.load(task)
