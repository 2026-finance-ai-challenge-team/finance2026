from __future__ import annotations

import json
import hashlib
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from proofbridge_api.analysis_service import _document_status
from proofbridge_api.config import Settings
from proofbridge_api.contracts import DocumentStatus
from proofbridge_api.main import create_app
from proofbridge_api.policy_service import PolicyContext

TASK_ID = "kakaobank.limit_account_release"


def test_explicit_unrelated_document_maps_to_unnecessary() -> None:
    status, reason = _document_status(
        {
            "classification": {"doc_type": "UNRELATED"},
            "relevance": {"status": "이번 업무에는 불필요"},
            "validity": {},
            "needs_user_confirm": False,
        }
    )

    assert status is DocumentStatus.UNNECESSARY
    assert reason == "CLEARLY_UNRELATED_DOCUMENT"


def test_task_specific_issue_date_limit_marks_document_expired() -> None:
    context = PolicyContext(
        policy={
            "requirement_sets": [
                {
                    "documents": [
                        {"doc_type": "certificate", "issued_within_days": 90}
                    ]
                }
            ]
        },
        signatures=[],
    )
    status, reason = _document_status(
        {
            "classification": {
                "doc_type": "certificate",
                "unverified_signature": False,
            },
            "relevance": {"status": "관련"},
            "metadata": {
                "document_type": {
                    "value": "certificate",
                    "status": "CONFIRMED",
                },
                "owner_match": {"status": "NOT_CHECKED"},
                "issued_at": {"value": "2026-01-01", "status": "CONFIRMED"},
                "expires_at": {"value": None, "status": "NOT_FOUND"},
            },
            "needs_user_confirm": False,
        },
        policy_context=context,
        today=date(2026, 9, 6),
    )

    assert status is DocumentStatus.EXPIRED
    assert reason == "TASK_ISSUE_DATE_LIMIT_PASSED"


def test_inferred_issue_date_never_auto_satisfies_task_deadline() -> None:
    context = PolicyContext(
        policy={
            "requirement_sets": [
                {
                    "documents": [
                        {"doc_type": "certificate", "issued_within_days": 90}
                    ]
                }
            ]
        },
        signatures=[],
    )
    status, reason = _document_status(
        {
            "classification": {
                "doc_type": "certificate",
                "unverified_signature": False,
            },
            "relevance": {"status": "관련"},
            "metadata": {
                "document_type": {
                    "value": "certificate",
                    "status": "CONFIRMED",
                },
                "owner_match": {"status": "NOT_CHECKED"},
                "issued_at": {"value": "2026-09-01", "status": "INFERRED"},
                "expires_at": {"value": None, "status": "NOT_FOUND"},
            },
            "needs_user_confirm": False,
        },
        policy_context=context,
        today=date(2026, 9, 6),
    )

    assert status is DocumentStatus.REVIEW_REQUIRED
    assert reason == "ISSUE_DATE_NOT_CONFIRMED"


def _manifest(repo_root: Path) -> dict:
    return json.loads(
        (repo_root / "demo_docs" / "kakaobank_expected.json").read_text(
            encoding="utf-8"
        )
    )


def _upload(client: TestClient, filenames: list[str]) -> dict:
    repo_root = client.app.state.settings.repo_root
    files = [
        (
            "files",
            (
                filename,
                (repo_root / "demo_docs" / filename).read_bytes(),
                "application/pdf",
            ),
        )
        for filename in filenames
    ]
    response = client.post(
        "/api/v1/analyze",
        data={"task_id": TASK_ID},
        files=files,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_manifest_contains_eight_text_pdf_fixtures(client: TestClient) -> None:
    repo_root = client.app.state.settings.repo_root
    manifest = _manifest(repo_root)

    assert manifest["task_id"] == TASK_ID
    assert manifest["synthetic_only"] is True
    assert len(manifest["documents"]) == 8
    assert len(manifest["ready_bundles"]) == 6

    for document in manifest["documents"]:
        path = repo_root / "demo_docs" / document["filename"]
        reader = PdfReader(path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)

        assert len(reader.pages) == 1
        assert "FORM:E 테스트용 합성 샘플" in text
        assert "실제 증명서가 아니며 효력이 없습니다" in text

        scan_path = repo_root / "demo_docs" / "scans" / document["scan_filename"]
        assert scan_path.read_bytes().startswith(b"\xff\xd8\xff")


def test_each_synthetic_pdf_is_classified_as_expected(client: TestClient) -> None:
    manifest = _manifest(client.app.state.settings.repo_root)

    for expected in manifest["documents"]:
        payload = _upload(client, [expected["filename"]])
        document = payload["documents"][0]

        assert document["source_name"] == expected["filename"]
        assert document["doc_type"] == expected["doc_type"]
        assert document["status"] == "REVIEW_REQUIRED"
        assert document["reason_code"] in {
            "UNVERIFIED_DOCUMENT_SIGNATURE",
            "SYNTHETIC_SAMPLE_FILENAME_HINT",
        }
        serialized = json.dumps(payload, ensure_ascii=False)
        assert "comparison_tokens" not in serialized
        assert document["metadata"]["owner_name"]["status"] in {
            "CONFIRMED",
            "NOT_FOUND",
        }
        assert "000000-0000000" not in serialized
        assert "000동 000호" not in serialized


def test_scanned_jpegs_use_ocr_boundary_and_keep_expected_classification(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = client.app.state.settings.repo_root
    manifest = _manifest(repo_root)
    text_by_digest: dict[str, str] = {}
    for expected in manifest["documents"]:
        pdf_path = repo_root / "demo_docs" / expected["filename"]
        scan_path = repo_root / "demo_docs" / "scans" / expected["scan_filename"]
        text_by_digest[hashlib.sha256(scan_path.read_bytes()).hexdigest()] = "\n".join(
            page.extract_text() or "" for page in PdfReader(pdf_path).pages
        )

    calls: list[str] = []

    def fake_ocr(path: Path, _timeout: float, cache_dir: Path | None = None) -> dict:
        del cache_dir
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        calls.append(digest)
        return {1: (text_by_digest[digest], "")}

    monkeypatch.setattr("modules.doc_classify.extract._ocr_whole_file", fake_ocr)
    settings = Settings(
        environment="test",
        repo_root=repo_root,
        max_upload_bytes=5 * 1024 * 1024,
        max_upload_files=2,
        session_temp_root=tmp_path / "ocr-sessions",
        ocr_timeout_seconds=1.0,
        ocr_invoke_url="https://synthetic.invalid/ocr",
        ocr_secret_key="synthetic-test-key",
        cors_allowed_origins=("http://localhost:3000",),
    )

    with TestClient(create_app(settings)) as ocr_client:
        for expected in manifest["documents"]:
            scan_path = repo_root / "demo_docs" / "scans" / expected["scan_filename"]
            response = ocr_client.post(
                "/api/v1/analyze",
                data={"task_id": TASK_ID},
                files={"files": (scan_path.name, scan_path.read_bytes(), "image/jpeg")},
            )
            assert response.status_code == 200, response.text
            document = response.json()["documents"][0]
            assert document["doc_type"] == expected["doc_type"]
            assert document["status"] == "REVIEW_REQUIRED"

        by_filename = {
            document["filename"]: document for document in manifest["documents"]
        }
        for bundle_filenames in manifest["ready_bundles"]:
            expected_bundle = by_filename[bundle_filenames[0]]["bundle_code"]
            upload_files = []
            for pdf_filename in bundle_filenames:
                expected = by_filename[pdf_filename]
                scan_path = (
                    repo_root / "demo_docs" / "scans" / expected["scan_filename"]
                )
                upload_files.append(
                    ("files", (scan_path.name, scan_path.read_bytes(), "image/jpeg"))
                )

            response = ocr_client.post(
                "/api/v1/analyze",
                data={"task_id": TASK_ID},
                files=upload_files,
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["overall_status"] == "REVIEW_REQUIRED"
            assert payload["requirements"][0]["matched_bundle_code"] == expected_bundle

    assert len(calls) == 16


def test_scanned_demo_bundle_uses_safe_filename_hint_without_ocr(
    client: TestClient,
) -> None:
    repo_root = client.app.state.settings.repo_root
    scan_names = [
        "합성_관리비고지서_스캔.jpg",
        "합성_주민등록표등본_스캔.jpg",
    ]
    files = [
        (
            "files",
            (
                scan_name,
                (repo_root / "demo_docs" / "scans" / scan_name).read_bytes(),
                "image/jpeg",
            ),
        )
        for scan_name in scan_names
    ]

    response = client.post(
        "/api/v1/analyze",
        data={"task_id": TASK_ID},
        files=files,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["overall_status"] == "REVIEW_REQUIRED"
    assert [document["doc_type"] for document in payload["documents"]] == [
        "management_fee_notice",
        "resident_registration_copy",
    ]
    assert all(
        document["reason_code"] == "SYNTHETIC_SAMPLE_FILENAME_HINT"
        for document in payload["documents"]
    )
    assert payload["requirements"][0]["matched_bundle_code"] == (
        "management_fee_and_resident_copy"
    )
    plan = payload["completion_plan"]
    assert plan["bundle_code"] == "management_fee_and_resident_copy"
    assert [guide["doc_type"] for guide in plan["documents"]] == [
        "management_fee_notice",
        "resident_registration_copy",
    ]
    resident_guide = next(
        guide
        for guide in plan["documents"]
        if guide["doc_type"] == "resident_registration_copy"
    )
    assert resident_guide["acquisition"]["source"]["verified"] is True
    assert "gov.kr" in resident_guide["acquisition"]["url"]
    assert plan["submission"]["expected_review"] == (
        "서류 제출 후 심사와 통보까지 2~3영업일이 걸린다."
    )
    assert any("샘플 파일명 힌트" in warning for warning in payload["warnings"])


@pytest.mark.parametrize(
    ("filenames", "expected_bundle_code"),
    [
        (["합성_전기요금청구서.pdf"], "utility_bill"),
        (
            ["합성_관리비고지서.pdf", "합성_주민등록표등본.pdf"],
            "management_fee_and_resident_copy",
        ),
        (["합성_세금고지서.pdf"], "tax_bill"),
        (["합성_건강보험자격득실확인서.pdf"], "health_insurance_qualification"),
        (
            ["합성_근로계약서.pdf", "합성_사업자등록증.pdf"],
            "employment_contract_and_employer_registration",
        ),
        (["합성_휴대폰요금납부확인서.pdf"], "mobile_phone_payment"),
    ],
)
def test_each_official_evidence_bundle_matches_postgresql_policy(
    client: TestClient,
    filenames: list[str],
    expected_bundle_code: str,
) -> None:
    payload = _upload(client, filenames)
    requirement = payload["requirements"][0]

    assert payload["overall_status"] == "REVIEW_REQUIRED"
    assert requirement["status"] == "REVIEW_REQUIRED"
    assert requirement["matched_bundle_code"] == expected_bundle_code
    assert requirement["source"]["verified"] is True

    matched_bundle = next(
        bundle
        for bundle in requirement["bundles"]
        if bundle["bundle_code"] == expected_bundle_code
    )
    assert matched_bundle["status"] == "REVIEW_REQUIRED"
    assert matched_bundle["missing_document_types"] == []
    assert len(matched_bundle["evidence_document_ids"]) == len(filenames)


@pytest.mark.parametrize(
    ("filenames", "doc_type", "expected_channel"),
    [
        (
            ["합성_건강보험자격득실확인서.pdf"],
            "health_insurance_certificate",
            "insurer_online_or_offline",
        ),
        (
            ["합성_근로계약서.pdf", "합성_사업자등록증.pdf"],
            "business_registration_certificate",
            "employer_direct",
        ),
    ],
)
def test_completion_plan_uses_task_specific_acquisition_guide(
    client: TestClient,
    filenames: list[str],
    doc_type: str,
    expected_channel: str,
) -> None:
    payload = _upload(client, filenames)
    guide = next(
        item
        for item in payload["completion_plan"]["documents"]
        if item["doc_type"] == doc_type
    )

    assert guide["acquisition"]["channel"] == expected_channel
    assert guide["acquisition"]["steps"]
    assert guide["acquisition"]["source"]["last_checked"] == "2026-08-31"
