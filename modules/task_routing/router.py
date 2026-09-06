"""Constrained LLM routing from a Korean request to a registered bank task."""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Protocol

from .models import BankTask, ModelDecision, RouteResult, RouteStatus, TaskChoice
from .repository import TaskCatalog


_BANK_ALIASES = {
    "KEB_HANA": ("하나은행", "하나", "KEB하나"),
    "KB_KOOKMIN": ("KB국민은행", "국민은행", "국민", "KB"),
    "KAKAO_BANK": ("카카오뱅크", "카카오은행", "카뱅"),
    "WOORI": ("우리은행", "우리"),
    "IBK": ("IBK기업은행", "기업은행", "IBK"),
    "SHINHAN": ("신한은행", "신한"),
}
_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?82[- ]?)?0\d{1,2}[- ]?\d{3,4}[- ]?\d{4}(?!\d)")
_SENSITIVE_NUMBER = re.compile(r"(?<!\d)\d(?:[- ]?\d){5,}(?!\d)")


class TaskSelector(Protocol):
    model: str

    def select(self, query: str, tasks: list[BankTask]) -> ModelDecision | None: ...


def normalize_query(query: str) -> str:
    value = unicodedata.normalize("NFKC", query).casefold()
    value = value.replace("카뱅", "카카오뱅크").replace("카카오 은행", "카카오뱅크")
    value = re.sub(r"[^0-9a-z가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def redact_query(query: str) -> str:
    """Remove common identifiers before sending a task-only sentence to an LLM."""
    value = _EMAIL.sub("[EMAIL_REDACTED]", query)
    value = _PHONE.sub("[PHONE_REDACTED]", value)
    return _SENSITIVE_NUMBER.sub("[NUMBER_REDACTED]", value)


class OpenAITaskSelector:
    """Responses API selector that cannot return an unregistered task ID."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout_seconds: float = 20.0,
        client: Any | None = None,
    ) -> None:
        if not api_key.strip() and client is None:
            raise ValueError("OpenAI API key is required")
        if client is None:
            from openai import OpenAI

            options: dict[str, Any] = {
                "api_key": api_key,
                "timeout": timeout_seconds,
            }
            if base_url:
                options["base_url"] = base_url.rstrip("/") + "/"
            client = OpenAI(**options)
        self._client = client
        self.model = model

    def select(self, query: str, tasks: list[BankTask]) -> ModelDecision | None:
        allowed_ids = [task.task_id for task in tasks]
        if not allowed_ids:
            return None
        catalog = [
            {
                "task_id": task.task_id,
                "bank": task.bank_name_ko,
                "operation": task.operation_name_ko,
            }
            for task in tasks
        ]
        response = self._client.responses.create(
            model=self.model,
            store=False,
            input=[
                {
                    "role": "system",
                    "content": [{
                        "type": "input_text",
                        "text": (
                            "사용자의 한국어 금융업무 요청을 분류한다. supplied catalog의 "
                            "task_id만 선택하고 은행이나 업무를 만들지 않는다. 은행 또는 행동이 "
                            "모호하면 UNKNOWN과 관련 후보를 반환한다. 계좌 개설과 한도계좌 해제는 "
                            "서로 다른 업무다. reason은 짧은 한국어 문장으로 작성한다."
                        ),
                    }],
                },
                {
                    "role": "user",
                    "content": [{
                        "type": "input_text",
                        "text": json.dumps(
                            {
                                "user_request": redact_query(query),
                                "allowed_tasks": catalog,
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    }],
                },
            ],
            text={"format": {
                "type": "json_schema",
                "name": "proofbridge_bank_task_routing",
                "strict": True,
                "schema": _response_schema(allowed_ids),
            }},
        )
        return self._parse(response, set(allowed_ids))

    @staticmethod
    def _parse(response: Any, allowed_ids: set[str]) -> ModelDecision | None:
        output_text = getattr(response, "output_text", "")
        if not output_text:
            return None
        try:
            payload = json.loads(output_text)
            selected = str(payload["selected_task_id"])
            confidence = float(payload["confidence"])
            alternatives = tuple(str(item) for item in payload["alternative_task_ids"])
            needs_clarification = bool(payload["needs_clarification"])
            reason = str(payload["reason"]).strip()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        if selected != "UNKNOWN" and selected not in allowed_ids:
            return None
        if not 0.0 <= confidence <= 1.0:
            return None
        if not set(alternatives).issubset(allowed_ids):
            return None
        return ModelDecision(
            selected_task_id=None if selected == "UNKNOWN" else selected,
            confidence=confidence,
            alternative_task_ids=alternatives[:3],
            needs_clarification=needs_clarification,
            reason=reason or "등록된 은행 업무와 입력 내용을 비교했습니다.",
        )


class NaturalLanguageTaskRouter:
    """Coordinate catalog loading, constrained LLM selection, and safe fallback."""

    def __init__(
        self,
        *,
        catalog: TaskCatalog,
        selector: TaskSelector | None = None,
        auto_resolve_confidence: float = 0.78,
    ) -> None:
        if not 0.0 < auto_resolve_confidence <= 1.0:
            raise ValueError("auto_resolve_confidence must be in (0, 1]")
        self._catalog = catalog
        self._selector = selector
        self._auto_resolve_confidence = auto_resolve_confidence

    def route(self, query: str) -> RouteResult:
        normalized = normalize_query(query)
        if not 2 <= len(normalized) <= 300:
            raise ValueError("query must contain 2 to 300 normalized characters")
        tasks = self._catalog.list_tasks()
        if not tasks:
            raise RuntimeError("bank task catalog is empty")

        decision = None
        method = "deterministic"
        model = None
        if self._selector is not None:
            try:
                decision = self._selector.select(query, tasks)
            except Exception:
                decision = None
            if decision is not None:
                method = "llm"
                model = self._selector.model
        if decision is None:
            decision = _deterministic_decision(normalized, tasks)

        by_id = {task.task_id: task for task in tasks}
        selected_task = by_id.get(decision.selected_task_id or "")
        candidate_ids = _unique_ids(
            [decision.selected_task_id, *decision.alternative_task_ids]
        )
        candidates = tuple(
            _choice(
                by_id[task_id],
                decision.confidence if index == 0 else 0.55,
            )
            for index, task_id in enumerate(candidate_ids)
            if task_id in by_id
        )
        selected = next(
            (
                candidate
                for candidate in candidates
                if selected_task is not None and candidate.task_id == selected_task.task_id
            ),
            None,
        )

        if selected is None:
            status = RouteStatus.NEEDS_CONFIRMATION if candidates else RouteStatus.UNSUPPORTED
            clarification = (
                "어느 은행에서 어떤 업무를 하려는지 조금 더 알려주세요."
                if candidates
                else None
            )
        elif (
            decision.needs_clarification
            or decision.confidence < self._auto_resolve_confidence
        ):
            status = RouteStatus.NEEDS_CONFIRMATION
            clarification = (
                f"{selected.bank_name_ko}의 ‘{selected.operation_name_ko}’ 업무가 맞나요?"
            )
        else:
            status = RouteStatus.RESOLVED
            clarification = None

        return RouteResult(
            query=query,
            normalized_query=normalized,
            status=status,
            selected=selected,
            candidates=candidates,
            clarification_question=clarification,
            reason=decision.reason,
            method=method,
            model=model,
        )


def _deterministic_decision(query: str, tasks: list[BankTask]) -> ModelDecision:
    explicit_banks = _explicit_bank_codes(query)
    candidate_tasks = (
        [task for task in tasks if task.bank_code in explicit_banks]
        if len(explicit_banks) == 1
        else tasks
    )
    ranked = sorted(
        ((_lexical_score(query, task), task) for task in candidate_tasks),
        key=lambda item: (-item[0], item[1].task_id),
    )
    relevant = [(score, task) for score, task in ranked if score >= 0.38][:3]
    if not relevant:
        return ModelDecision(
            None,
            0.0,
            (),
            False,
            "등록된 은행 업무에서 가까운 후보를 찾지 못했습니다.",
        )
    top_score, top = relevant[0]
    close = len(relevant) > 1 and relevant[1][0] >= top_score - 0.08
    needs_action_check = (
        "limit_account_release" in top.policy_key
        and not any(term in query for term in ("해제", "풀", "전환", "한도 올"))
    )
    return ModelDecision(
        selected_task_id=None if close else top.task_id,
        confidence=min(top_score, 0.72) if needs_action_check else top_score,
        alternative_task_ids=tuple(task.task_id for _score, task in relevant),
        needs_clarification=close or needs_action_check or top_score < 0.78,
        reason=(
            "은행과 계좌 종류는 찾았지만 하려는 행동을 확인해야 합니다."
            if needs_action_check
            else "입력 표현을 등록된 은행·업무명과 비교했습니다."
        ),
    )


def _explicit_bank_codes(query: str) -> set[str]:
    """Return banks explicitly named by the user, ignoring generic fragments."""
    compact = query.replace(" ", "")
    matches: set[str] = set()
    for bank_code, aliases in _BANK_ALIASES.items():
        normalized_aliases = {
            normalize_query(alias).replace(" ", "")
            for alias in aliases
            if len(normalize_query(alias).replace(" ", "")) >= 2
        }
        if any(alias in compact for alias in normalized_aliases):
            matches.add(bank_code)
    return matches


def _lexical_score(query: str, task: BankTask) -> float:
    compact = query.replace(" ", "")
    bank_aliases = [task.bank_name_ko, *_BANK_ALIASES.get(task.bank_code, ())]
    bank_present = any(
        normalize_query(alias).replace(" ", "") in compact for alias in bank_aliases
    )
    operation = normalize_query(task.operation_name_ko).replace(" ", "")
    operation_ratio = SequenceMatcher(None, compact, operation).ratio()
    operation_present = bool(operation and operation in compact)
    score = operation_ratio * 0.55 + (0.25 if bank_present else 0)
    if operation_present:
        score += 0.2
    return round(min(1.0, score), 4)


def _choice(task: BankTask, confidence: float) -> TaskChoice:
    return TaskChoice(
        task_id=task.task_id,
        bank_code=task.bank_code,
        bank_name_ko=task.bank_name_ko,
        policy_key=task.policy_key,
        operation_code=task.operation_code,
        operation_name_ko=task.operation_name_ko,
        policy_status=task.policy_status,
        confidence=max(0.0, min(1.0, confidence)),
        source_title=task.source_title,
        source_url=task.source_url,
        source_checked_at=task.source_checked_at,
    )


def _unique_ids(values: list[str | None]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _response_schema(allowed_ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "selected_task_id": {
                "type": "string",
                "enum": [*allowed_ids, "UNKNOWN"],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "alternative_task_ids": {
                "type": "array",
                "maxItems": 3,
                "items": {"type": "string", "enum": allowed_ids},
            },
            "needs_clarification": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": [
            "selected_task_id",
            "confidence",
            "alternative_task_ids",
            "needs_clarification",
            "reason",
        ],
    }
