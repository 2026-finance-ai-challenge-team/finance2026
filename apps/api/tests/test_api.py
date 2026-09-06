from __future__ import annotations

from io import BytesIO
import asyncio
import json
from pathlib import Path
from uuid import UUID
from zipfile import ZipFile

from fastapi import UploadFile
from fastapi.testclient import TestClient

from proofbridge_api.analysis_service import DocumentClassificationPipeline
from proofbridge_api.config import Settings


def test_blank_session_temp_root_uses_safe_system_temp(monkeypatch) -> None:
    monkeypatch.setenv("PROOFBRIDGE_SESSION_TEMP_ROOT", "")

    settings = Settings.from_env()

    assert settings.session_temp_root.name == "proofbridge-sessions"


def test_settings_accept_openai_compatible_proxy(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:8317/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-proxy-key")
    monkeypatch.setenv("PROOFBRIDGE_OPENAI_MODEL", "proxy-model")

    settings = Settings.from_env()

    assert settings.openai_base_url == "http://127.0.0.1:8317/v1"
    assert settings.openai_api_key == "synthetic-proxy-key"
    assert settings.openai_model == "proxy-model"
    assert settings.llm_configured is True


def test_health_does_not_disclose_secrets(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "FORM:E API",
        "version": "0.1.0",
        "environment": "test",
        "ocr_configured": False,
        "llm_configured": False,
    }


def test_saved_upload_uses_magic_detected_extension_for_ocr(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    settings = Settings(
        environment="test",
        repo_root=repo_root,
        max_upload_bytes=1024,
        max_upload_files=1,
        session_temp_root=tmp_path / "sessions",
        ocr_timeout_seconds=1.0,
        ocr_invoke_url="https://example.invalid/general",
        ocr_secret_key="synthetic-secret",
    )
    pipeline = DocumentClassificationPipeline(settings)
    upload = UploadFile(
        filename="untrusted-name.jpg",
        file=BytesIO(b"\xff\xd8\xffsynthetic-jpeg"),
    )

    paths, source_names = asyncio.run(
        pipeline._save_uploads([upload], tmp_path)  # noqa: SLF001
    )

    assert paths[0].suffix == ".jpg"
    assert paths[0].read_bytes().startswith(b"\xff\xd8\xff")
    assert source_names == ["untrusted-name.jpg"]


def test_local_web_origin_can_call_analysis_api(client: TestClient) -> None:
    response = client.options(
        "/api/v1/analyze",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_task_catalog_exposes_verified_policy_binding(client: TestClient) -> None:
    response = client.get("/api/v1/tasks")

    assert response.status_code == 200
    task = next(
        task
        for task in response.json()
        if task["task_id"] == "kakaobank.limit_account_release"
    )
    assert task["task_id"] == "kakaobank.limit_account_release"
    assert task["bank_code"] == "KAKAO_BANK"
    assert task["policy_key"] == "limit_account_release"
    assert task["channel"] == "non_face_to_face"
    assert task["visitor_type"] == "account_holder"
    assert task["verified"] is True
    assert task["source_url"] == (
        "https://blog.kakaobank.com/posts/service-limit-account"
    )


def test_requirements_are_available_without_uploading_files(client: TestClient) -> None:
    response = client.get(
        "/api/v1/tasks/kakaobank.limit_account_release/requirements"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["task_id"] == "kakaobank.limit_account_release"
    assert len(payload["documents"]) == 8
    assert all(document["source"]["url"] for document in payload["documents"])
    assert any(
        document["acquisition"]["url"] for document in payload["documents"]
    )


def test_demo_never_claims_ready_for_unverified_signatures(client: TestClient) -> None:
    response = client.post("/api/v1/demo")

    assert response.status_code == 200
    payload = response.json()
    UUID(payload["session_id"])
    assert payload["overall_status"] == "REVIEW_REQUIRED"
    assert payload["task"]["verified"] is True
    assert all("text" not in document for document in payload["documents"])


def test_demo_session_can_be_read_and_deleted(client: TestClient) -> None:
    created = client.post("/api/v1/demo").json()
    session_id = created["session_id"]

    assert client.get(f"/api/v1/sessions/{session_id}").status_code == 200
    deleted = client.delete(f"/api/v1/sessions/{session_id}")
    assert deleted.json() == {"session_id": session_id, "deleted": True}
    assert client.get(f"/api/v1/sessions/{session_id}").status_code == 404


def test_preparation_kit_contains_guidance_without_uploaded_originals(
    client: TestClient,
) -> None:
    created = client.post("/api/v1/demo").json()
    response = client.get(
        f"/api/v1/sessions/{created['session_id']}/preparation-kit",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment;" in response.headers["content-disposition"]
    assert response.headers["access-control-expose-headers"] == "Content-Disposition"
    with ZipFile(BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"README.md", "analysis-result.json"}
        readme = archive.read("README.md").decode("utf-8")
        payload = json.loads(archive.read("analysis-result.json"))

    assert "은행의 승인·통과를 보장하지" in readme
    assert "이 ZIP에는 원본 문서가 없습니다" in readme
    assert payload["contains_uploaded_originals"] is False
    assert all("source_name" not in document for document in payload["documents"])


def test_preparation_kit_rejects_unknown_session(client: TestClient) -> None:
    response = client.get(
        "/api/v1/sessions/00000000-0000-0000-0000-000000000000/preparation-kit"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_invalid_file_signature_fails_safely(client: TestClient) -> None:
    response = client.post(
        "/api/v1/analyze",
        data={"task_id": "kakaobank.limit_account_release"},
        files={"files": ("synthetic.pdf", b"synthetic", "application/pdf")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "INVALID_FILE_SIGNATURE"


def test_real_analysis_classifies_synthetic_documents_and_cleans_files(
    client: TestClient,
) -> None:
    repo_root = client.app.state.settings.repo_root
    fixture_names = ["합성_전기요금청구서.pdf", "합성_세금고지서.pdf"]
    upload_files = [
        (
            "files",
            (
                fixture_name,
                (repo_root / "demo_docs" / fixture_name).read_bytes(),
                "application/pdf",
            ),
        )
        for fixture_name in fixture_names
    ]

    response = client.post(
        "/api/v1/analyze",
        data={"task_id": "kakaobank.limit_account_release"},
        files=upload_files,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "REVIEW_REQUIRED"
    assert payload["task"]["verified"] is True
    assert [document["source_name"] for document in payload["documents"]] == fixture_names
    assert {document["doc_type"] for document in payload["documents"]} == {
        "utility_bill",
        "tax_bill",
    }
    requirement = payload["requirements"][0]
    assert requirement["status"] == "REVIEW_REQUIRED"
    assert requirement["matched_bundle_code"] == "utility_bill"
    assert requirement["source"]["verified"] is True
    assert requirement["source"]["url"] == (
        "https://blog.kakaobank.com/posts/service-limit-account"
    )
    utility_bundle = next(
        bundle
        for bundle in requirement["bundles"]
        if bundle["bundle_code"] == "utility_bill"
    )
    assert utility_bundle["status"] == "REVIEW_REQUIRED"
    assert utility_bundle["evidence_document_ids"] == ["f01"]
    assert client.get(f"/api/v1/sessions/{payload['session_id']}").status_code == 200

    session_temp_root = client.app.state.settings.session_temp_root
    assert session_temp_root.is_dir()
    assert list(session_temp_root.iterdir()) == []


def test_user_can_confirm_document_type_without_creating_ready_result(
    client: TestClient,
) -> None:
    repo_root = client.app.state.settings.repo_root
    fixture_name = "합성_전기요금청구서.pdf"
    created = client.post(
        "/api/v1/analyze",
        data={"task_id": "kakaobank.limit_account_release"},
        files={
            "files": (
                fixture_name,
                (repo_root / "demo_docs" / fixture_name).read_bytes(),
                "application/pdf",
            )
        },
    ).json()

    response = client.patch(
        f"/api/v1/sessions/{created['session_id']}/documents/f01/classification",
        json={"doc_type": "health_insurance_certificate"},
    )

    assert response.status_code == 200
    payload = response.json()
    document = payload["documents"][0]
    assert document["doc_type"] == "health_insurance_certificate"
    assert document["classification_method"] == "user_confirmed"
    assert document["needs_user_confirm"] is False
    assert document["status"] == "REVIEW_REQUIRED"
    assert document["reason_code"] == "USER_CONFIRMED_DOCUMENT_TYPE"
    assert payload["overall_status"] == "REVIEW_REQUIRED"
    assert any("진위·발급일·내용 검증" in warning for warning in payload["warnings"])


def test_document_confirmation_rejects_unknown_type(client: TestClient) -> None:
    repo_root = client.app.state.settings.repo_root
    fixture_name = "합성_전기요금청구서.pdf"
    created = client.post(
        "/api/v1/analyze",
        data={"task_id": "kakaobank.limit_account_release"},
        files={
            "files": (
                fixture_name,
                (repo_root / "demo_docs" / fixture_name).read_bytes(),
                "application/pdf",
            )
        },
    ).json()

    response = client.patch(
        f"/api/v1/sessions/{created['session_id']}/documents/f01/classification",
        json={"doc_type": "invented_document_type"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DOCUMENT_TYPE_NOT_ALLOWED"


def test_unknown_task_is_rejected_before_analysis(client: TestClient) -> None:
    response = client.post(
        "/api/v1/analyze",
        data={"task_id": "unknown.task"},
        files={"files": ("synthetic.pdf", b"synthetic", "application/pdf")},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TASK_NOT_FOUND"


def test_upload_boundary_rejects_large_file(client: TestClient) -> None:
    oversized = client.app.state.settings.max_upload_bytes + 1
    response = client.post(
        "/api/v1/analyze",
        data={"task_id": "kakaobank.limit_account_release"},
        files={"files": ("synthetic.pdf", b"x" * oversized, "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_upload_boundary_rejects_unsupported_media(client: TestClient) -> None:
    response = client.post(
        "/api/v1/analyze",
        data={"task_id": "kakaobank.limit_account_release"},
        files={"files": ("synthetic.txt", b"not a document", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
