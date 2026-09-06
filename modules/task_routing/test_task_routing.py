from __future__ import annotations

import json
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from modules.task_routing.models import BankTask, ModelDecision, RouteStatus
from modules.task_routing.router import (
    NaturalLanguageTaskRouter,
    OpenAITaskSelector,
    redact_query,
)
from modules.task_routing.repository import PostgreSQLTaskCatalog


TASKS = [
    BankTask(
        task_id="kakaobank.limit_account_release",
        bank_code="KAKAO_BANK",
        bank_name_ko="카카오뱅크",
        policy_key="limit_account_release",
        operation_code="limit_account_release",
        operation_name_ko="한도계좌 해제",
        policy_status="published",
    ),
    BankTask(
        task_id="kakaobank.demand_deposit_opening",
        bank_code="KAKAO_BANK",
        bank_name_ko="카카오뱅크",
        policy_key="demand_deposit_opening",
        operation_code="demand_deposit_opening",
        operation_name_ko="입출금통장 개설",
        policy_status="published",
    ),
    BankTask(
        task_id="shinhan.limit_account_release",
        bank_code="SHINHAN",
        bank_name_ko="신한은행",
        policy_key="limit_account_release",
        operation_code="limit_account_release",
        operation_name_ko="금융거래 한도계좌 일반계좌 전환",
        policy_status="published",
    ),
]


class StaticCatalog:
    def list_tasks(self) -> list[BankTask]:
        return TASKS


class FixedSelector:
    model = "test-model"

    def __init__(self, decision: ModelDecision | None) -> None:
        self.decision = decision

    def select(self, query: str, tasks: list[BankTask]) -> ModelDecision | None:
        return self.decision


class FakeResponses:
    def __init__(self, output: dict) -> None:
        self.output = output
        self.request: dict | None = None

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(output_text=json.dumps(self.output, ensure_ascii=False))


class FakeClient:
    def __init__(self, output: dict) -> None:
        self.responses = FakeResponses(output)


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def execute(self, _query: str):
        return SimpleNamespace(
            fetchall=lambda: [
                {
                    "task_id": "kakaobank.limit_account_release",
                    "bank_code": "KAKAO_BANK",
                    "bank_name_ko": "카카오뱅크",
                    "policy_key": "limit_account_release",
                    "operation_code": "limit_account_release",
                    "operation_name_ko": "한도계좌 해제",
                    "policy_status": "published",
                    "source_title": "공식 안내",
                    "source_url": "https://example.com/official",
                    "source_checked_at": date(2026, 9, 3),
                }
            ]
        )

    def close(self) -> None:
        self.closed = True


class NaturalLanguageTaskRoutingTests(unittest.TestCase):
    def test_explicit_bank_name_prevents_cross_bank_selection(self) -> None:
        tasks = [
            BankTask(
                task_id="kb.balance_certificate_issuance",
                bank_code="KB_KOOKMIN",
                bank_name_ko="KB국민은행",
                policy_key="balance_certificate_issuance",
                operation_code="balance_certificate_issuance",
                operation_name_ko="예금잔액증명서 발급",
                policy_status="published",
            ),
            BankTask(
                task_id="ibk.balance_certificate_issuance",
                bank_code="IBK",
                bank_name_ko="IBK기업은행",
                policy_key="balance_certificate_issuance",
                operation_code="balance_certificate_issuance",
                operation_name_ko="잔액증명서 발급",
                policy_status="published",
            ),
        ]
        catalog = SimpleNamespace(list_tasks=lambda: tasks)

        result = NaturalLanguageTaskRouter(catalog=catalog).route(
            "국민은행 잔액증명서 발급"
        )

        self.assertIsNotNone(result.selected)
        self.assertEqual(result.selected.bank_code, "KB_KOOKMIN")

    def test_llm_selected_id_is_resolved(self) -> None:
        selector = FixedSelector(
            ModelDecision(
                selected_task_id="kakaobank.limit_account_release",
                confidence=0.96,
                alternative_task_ids=(),
                needs_clarification=False,
                reason="카카오뱅크 한도계좌 해제 요청입니다.",
            )
        )
        result = NaturalLanguageTaskRouter(
            catalog=StaticCatalog(), selector=selector
        ).route("카뱅 이체 한도를 풀고 싶어요")

        self.assertEqual(result.status, RouteStatus.RESOLVED)
        self.assertEqual(result.selected.bank_code, "KAKAO_BANK")
        self.assertEqual(result.selected.policy_key, "limit_account_release")
        self.assertEqual(result.method, "llm")

    def test_ambiguous_request_returns_candidates_without_auto_selection(self) -> None:
        selector = FixedSelector(
            ModelDecision(
                selected_task_id=None,
                confidence=0.62,
                alternative_task_ids=(
                    "kakaobank.limit_account_release",
                    "shinhan.limit_account_release",
                ),
                needs_clarification=True,
                reason="은행명이 빠져 있습니다.",
            )
        )
        result = NaturalLanguageTaskRouter(
            catalog=StaticCatalog(), selector=selector
        ).route("한도계좌를 풀고 싶어요")

        self.assertEqual(result.status, RouteStatus.NEEDS_CONFIRMATION)
        self.assertIsNone(result.selected)
        self.assertEqual(len(result.candidates), 2)

    def test_structured_output_rejects_an_id_outside_catalog(self) -> None:
        client = FakeClient(
            {
                "selected_task_id": "invented.bank_task",
                "confidence": 0.99,
                "alternative_task_ids": [],
                "needs_clarification": False,
                "reason": "",
            }
        )
        selector = OpenAITaskSelector(
            api_key="", model="test-model", client=client
        )

        self.assertIsNone(selector.select("아무 요청", TASKS))

    def test_llm_request_is_not_stored_and_common_identifiers_are_redacted(self) -> None:
        client = FakeClient(
            {
                "selected_task_id": "UNKNOWN",
                "confidence": 0.1,
                "alternative_task_ids": [],
                "needs_clarification": True,
                "reason": "업무가 모호합니다.",
            }
        )
        selector = OpenAITaskSelector(
            api_key="", model="test-model", client=client
        )
        selector.select("010-1234-5678 계좌 123456789 문의", TASKS)

        request = client.responses.request
        self.assertIsNotNone(request)
        self.assertIs(request["store"], False)
        serialized = json.dumps(request["input"], ensure_ascii=False)
        self.assertNotIn("010-1234-5678", serialized)
        self.assertNotIn("123456789", serialized)

    def test_redaction_keeps_the_banking_intent(self) -> None:
        value = redact_query("test@example.com 카뱅 한도 풀기 010-1234-5678")
        self.assertIn("카뱅 한도 풀기", value)
        self.assertNotIn("test@example.com", value)

    def test_postgresql_catalog_maps_latest_operation_rows(self) -> None:
        connection = FakeConnection()
        with patch(
            "modules.task_routing.repository.connect_database",
            return_value=connection,
        ):
            tasks = PostgreSQLTaskCatalog(
                "postgresql://user:password@localhost/proofbridge"
            ).list_tasks()

        self.assertTrue(connection.closed)
        self.assertEqual(tasks[0].bank_name_ko, "카카오뱅크")
        self.assertEqual(tasks[0].source_checked_at, "2026-09-03")


if __name__ == "__main__":
    unittest.main()
