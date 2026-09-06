from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from modules.doc_classify.classify import load_signatures

from proofbridge_api.config import Settings
from proofbridge_api.main import create_app
from proofbridge_api.policy_service import PolicyContext, PostgreSQLPolicyService


class _SeedPolicyService(PostgreSQLPolicyService):
    """Deterministic test double built from the PostgreSQL seed payload."""

    def __init__(self, repo_root: Path) -> None:
        super().__init__(database_url=None)
        self._repo_root = repo_root

    def load(self, task):
        seed = json.loads(
            (self._repo_root / "data" / "seeds" / "kakaobank_limit_release.json")
            .read_text(encoding="utf-8")
        )
        source = seed["sources"][0]
        labels = {item["doc_type"]: item["label_ko"] for item in seed["documents"]}
        requirement_sets = seed["requirement_sets"]
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
                document.setdefault("acquisition", None)
            for preparation in requirement_set["preparations"]:
                preparation["label_ko"] = preparation.get(
                    "label_ko", preparation.get("name_ko", preparation["code"])
                )
        signatures = {item["doc_type"]: item for item in load_signatures()}
        for seed_path in (self._repo_root / "data" / "seeds").glob("*.json"):
            payload = json.loads(seed_path.read_text(encoding="utf-8"))
            signatures.update(
                {
                    item["doc_type"]: item
                    for item in payload.get("documents", [])
                    if item.get("doc_type")
                }
            )
        return PolicyContext(
            policy={
                "task_id": task.task_id,
                "policy_status": seed["policy"]["status"],
                "requirement_sets": requirement_sets,
                "policy_conditions": seed["policy_conditions"],
            },
            signatures=list(signatures.values()),
        )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    repo_root = Path(__file__).resolve().parents[3]
    seed_service = _SeedPolicyService(repo_root)
    monkeypatch.setattr(
        "proofbridge_api.analysis_service.PostgreSQLPolicyService",
        lambda _database_url: seed_service,
    )
    monkeypatch.setattr(
        "proofbridge_api.routers.tasks.PostgreSQLPolicyService",
        lambda _database_url: seed_service,
    )
    settings = Settings(
        environment="test",
        repo_root=repo_root,
        max_upload_bytes=5 * 1024 * 1024,
        max_upload_files=2,
        session_temp_root=tmp_path / "sessions",
        ocr_timeout_seconds=1.0,
        ocr_invoke_url=None,
        ocr_secret_key=None,
        cors_allowed_origins=("http://localhost:3000",),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
