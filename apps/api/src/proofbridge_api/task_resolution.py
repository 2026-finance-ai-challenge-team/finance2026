"""FastAPI adapter for constrained natural-language bank task routing."""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from modules.task_routing import (
    NaturalLanguageTaskRouter,
    OpenAITaskSelector,
    PostgreSQLTaskCatalog,
)
from modules.task_routing.models import RouteResult, RouteStatus, TaskChoice

from .config import Settings
from .contracts import (
    TaskKnowledgeEvidence,
    TaskResolutionCandidate,
    TaskResolutionResponse,
    TaskResolutionStatus,
)


OPENING_TERMS = ("개설", "만들", "신규", "처음 계좌")
RELEASE_TERMS = ("해제", "풀", "일반계좌", "전환", "송금 한도", "이체 한도")
SOURCE_URL = "https://blog.kakaobank.com/posts/service-limit-account"


def normalize_query(query: str) -> str:
    value = unicodedata.normalize("NFKC", query).casefold()
    value = value.replace("카뱅", "카카오뱅크").replace("카카오 은행", "카카오뱅크")
    value = re.sub(r"[^0-9a-z가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


class TaskResolverUnavailable(RuntimeError):
    """Raised when no safe task catalog can answer a request."""


class TaskResolver:
    """Use the new LLM router when configured and retain a demo-safe fallback."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        supported_task_ids: set[str] | None = None,
    ) -> None:
        self._supported_task_ids = supported_task_ids or {
            "kakaobank.limit_account_release"
        }
        self._router: NaturalLanguageTaskRouter | None = None
        if settings is not None and settings.database_url:
            selector = (
                OpenAITaskSelector(
                    api_key=settings.openai_api_key or "",
                    base_url=settings.openai_base_url,
                    model=settings.openai_model,
                    timeout_seconds=settings.llm_timeout_seconds,
                )
                if settings.llm_configured
                else None
            )
            self._router = NaturalLanguageTaskRouter(
                catalog=PostgreSQLTaskCatalog(settings.database_url),
                selector=selector,
            )

    def resolve(self, query: str) -> TaskResolutionResponse:
        if self._router is None:
            return _legacy_resolve(query)
        try:
            result = self._router.route(query)
        except Exception as error:
            fallback = _legacy_resolve(query)
            if fallback.resolution is not TaskResolutionStatus.UNSUPPORTED:
                return fallback
            raise TaskResolverUnavailable(str(error)) from error
        return self._to_response(result)

    def _to_response(self, result: RouteResult) -> TaskResolutionResponse:
        candidates = [self._candidate(choice) for choice in result.candidates]
        selected = next(
            (
                candidate
                for candidate in candidates
                if result.selected is not None
                and candidate.task_id == result.selected.task_id
            ),
            None,
        )
        status = {
            RouteStatus.RESOLVED: TaskResolutionStatus.RESOLVED,
            RouteStatus.NEEDS_CONFIRMATION: TaskResolutionStatus.NEEDS_CONFIRMATION,
            RouteStatus.UNSUPPORTED: TaskResolutionStatus.UNSUPPORTED,
        }[result.status]
        return TaskResolutionResponse(
            query=result.query,
            normalized_query=result.normalized_query,
            resolution=status,
            selected_task=selected,
            candidates=candidates,
            clarification_question=result.clarification_question,
            reason=result.reason,
            evidence=_evidence(result.selected),
            retrieval_methods=[result.method],
            embedding_model=result.model or "none",
        )

    def _candidate(self, choice: TaskChoice) -> TaskResolutionCandidate:
        if choice.policy_status != "published":
            support_status = "PLANNED"
        elif choice.task_id in self._supported_task_ids:
            support_status = "SUPPORTED"
        else:
            support_status = "GUIDE_ONLY"
        return TaskResolutionCandidate(
            task_id=choice.task_id,
            label_ko=choice.operation_name_ko,
            bank_code=choice.bank_code,
            bank_name_ko=choice.bank_name_ko,
            policy_key=choice.policy_key,
            operation_code=choice.operation_code,
            support_status=support_status,
            confidence=choice.confidence,
            lexical_score=0.0,
            vector_score=0.0,
            matched_aliases=[],
        )


def _evidence(choice: TaskChoice | None) -> list[TaskKnowledgeEvidence]:
    if choice is None or not choice.source_url or not choice.source_checked_at:
        return []
    try:
        checked_at = date.fromisoformat(choice.source_checked_at)
    except ValueError:
        return []
    return [
        TaskKnowledgeEvidence(
            chunk_id=f"{choice.task_id}.official-source",
            title=choice.source_title or f"{choice.bank_name_ko} 공식 안내",
            excerpt=(
                f"{choice.bank_name_ko}에서 ‘{choice.operation_name_ko}’ 업무를 "
                "안내하고 있습니다."
            ),
            source_url=choice.source_url,
            verified=choice.policy_status == "published",
            last_checked=checked_at,
            score=choice.confidence,
        )
    ]


def _legacy_resolve(query: str) -> TaskResolutionResponse:
    """Keep the checked-in demo task available without PostgreSQL or LLM."""
    normalized = normalize_query(query)
    has_bank = "카카오뱅크" in normalized
    has_limit_account = "한도계좌" in normalized or "한도 계좌" in normalized
    has_opening = any(term in normalized for term in OPENING_TERMS)
    has_release = any(term in normalized for term in RELEASE_TERMS)
    if not (has_bank and has_limit_account):
        return TaskResolutionResponse(
            query=query,
            normalized_query=normalized,
            resolution=TaskResolutionStatus.UNSUPPORTED,
            selected_task=None,
            candidates=[],
            clarification_question=None,
            reason="현재 지원 중인 업무와 일치하지 않습니다.",
            evidence=[],
            retrieval_methods=["deterministic"],
            embedding_model="none",
        )

    confidence = 0.95 if has_release and not has_opening else 0.75
    candidate = TaskResolutionCandidate(
        task_id="kakaobank.limit_account_release",
        label_ko="한도계좌 해제",
        bank_code="KAKAO_BANK",
        bank_name_ko="카카오뱅크",
        policy_key="limit_account_release",
        operation_code="limit_account_release",
        support_status="SUPPORTED",
        confidence=confidence,
        lexical_score=confidence,
        vector_score=0.0,
        matched_aliases=["카카오뱅크 한도계좌 해제"],
    )
    if has_release and not has_opening:
        resolution = TaskResolutionStatus.RESOLVED
        question = None
        reason = "은행과 한도계좌 해제 의도가 지원 업무와 일치합니다."
    else:
        resolution = TaskResolutionStatus.NEEDS_CONFIRMATION
        question = (
            "새 계좌 개설이 아니라 카카오뱅크 한도계좌를 일반계좌로 전환하려는 업무가 맞나요?"
            if has_opening
            else "카카오뱅크 한도계좌 해제 서류를 준비하려는 게 맞나요?"
        )
        reason = "다른 계좌 업무와 혼동될 수 있어 확인이 필요합니다."
    return TaskResolutionResponse(
        query=query,
        normalized_query=normalized,
        resolution=resolution,
        selected_task=candidate,
        candidates=[candidate],
        clarification_question=question,
        reason=reason,
        evidence=[
            TaskKnowledgeEvidence(
                chunk_id="kakaobank-limit-release-official-guide",
                title="카카오뱅크 한도계좌 해제 공식 안내",
                excerpt="한도계좌 해제를 위해 금융거래 목적 확인 서류를 앱에서 제출합니다.",
                source_url=SOURCE_URL,
                verified=True,
                last_checked="2026-08-28",
                score=1.0,
            )
        ],
        retrieval_methods=["deterministic"],
        embedding_model="none",
    )
