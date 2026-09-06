from __future__ import annotations

from fastapi.testclient import TestClient
from modules.task_routing.models import RouteResult, RouteStatus, TaskChoice

from proofbridge_api.task_resolution import TaskResolver


class _StubRouter:
    def route(self, query: str) -> RouteResult:
        choice = TaskChoice(
            task_id="shinhan.limit_account_release",
            bank_code="SHINHAN",
            bank_name_ko="신한은행",
            policy_key="limit_account_release",
            operation_code="LIMIT_ACCOUNT_RELEASE",
            operation_name_ko="한도제한계좌 해제",
            policy_status="published",
            confidence=0.91,
            source_title="신한은행 공식 안내",
            source_url="https://bank.shinhan.com/",
            source_checked_at="2026-09-06",
        )
        return RouteResult(
            query=query,
            normalized_query=query,
            status=RouteStatus.RESOLVED,
            selected=choice,
            candidates=(choice,),
            clarification_question=None,
            reason="등록된 은행 업무와 일치합니다.",
            method="llm",
            model="test-model",
        )


def test_explicit_supported_task_is_resolved_with_grounded_evidence(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/tasks/resolve",
        json={"query": "카카오뱅크 한도계좌 해제 서류 준비"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["resolution"] == "RESOLVED"
    assert payload["selected_task"]["task_id"] == (
        "kakaobank.limit_account_release"
    )
    assert payload["selected_task"]["support_status"] == "SUPPORTED"
    assert payload["selected_task"]["confidence"] >= 0.72
    assert payload["retrieval_methods"] == ["deterministic"]
    assert payload["embedding_model"] == "none"
    assert payload["evidence"]
    assert all(item["verified"] is True for item in payload["evidence"])
    assert all(
        item["source_url"].startswith("https://blog.kakaobank.com/")
        for item in payload["evidence"]
    )


def test_short_task_expression_requires_confirmation(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/resolve",
        json={"query": "카뱅 한도계좌"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["normalized_query"] == "카카오뱅크 한도계좌"
    assert payload["resolution"] == "NEEDS_CONFIRMATION"
    assert payload["selected_task"]["task_id"] == (
        "kakaobank.limit_account_release"
    )
    assert "맞나요" in payload["clarification_question"]


def test_account_opening_language_is_never_auto_routed_to_release(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/tasks/resolve",
        json={"query": "카뱅 한도계좌 만들고 싶어"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["resolution"] == "NEEDS_CONFIRMATION"
    assert "새 계좌 개설이 아니라" in payload["clarification_question"]


def test_unrelated_task_is_rejected_without_inventing_task_id(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/tasks/resolve",
        json={"query": "삼성화재 보험금 청구"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["resolution"] == "UNSUPPORTED"
    assert payload["selected_task"] is None


def test_task_query_validation_rejects_blank_or_oversized_input(
    client: TestClient,
) -> None:
    assert client.post("/api/v1/tasks/resolve", json={"query": " "}).status_code == 422
    assert (
        client.post("/api/v1/tasks/resolve", json={"query": "가" * 301}).status_code
        == 422
    )


def test_new_router_result_is_mapped_without_claiming_full_support() -> None:
    resolver = TaskResolver()
    resolver._router = _StubRouter()

    payload = resolver.resolve("신한은행 한도계좌 풀고 싶어")

    assert payload.resolution == "RESOLVED"
    assert payload.selected_task is not None
    assert payload.selected_task.bank_name_ko == "신한은행"
    assert payload.selected_task.support_status == "GUIDE_ONLY"
    assert payload.retrieval_methods == ["llm"]
    assert payload.evidence[0].source_url == "https://bank.shinhan.com/"
