"""Framework-independent contracts for natural-language task routing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RouteStatus(str, Enum):
    RESOLVED = "RESOLVED"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class BankTask:
    task_id: str
    bank_code: str
    bank_name_ko: str
    policy_key: str
    operation_code: str
    operation_name_ko: str
    policy_status: str
    source_title: str | None = None
    source_url: str | None = None
    source_checked_at: str | None = None


@dataclass(frozen=True)
class TaskChoice:
    task_id: str
    bank_code: str
    bank_name_ko: str
    policy_key: str
    operation_code: str
    operation_name_ko: str
    policy_status: str
    confidence: float
    source_title: str | None = None
    source_url: str | None = None
    source_checked_at: str | None = None


@dataclass(frozen=True)
class ModelDecision:
    selected_task_id: str | None
    confidence: float
    alternative_task_ids: tuple[str, ...]
    needs_clarification: bool
    reason: str


@dataclass(frozen=True)
class RouteResult:
    query: str
    normalized_query: str
    status: RouteStatus
    selected: TaskChoice | None
    candidates: tuple[TaskChoice, ...]
    clarification_question: str | None
    reason: str
    method: str
    model: str | None
