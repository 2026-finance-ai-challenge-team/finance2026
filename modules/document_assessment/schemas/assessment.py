"""Typed contract for the final deterministic assessment output."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from .rule import ConsistencyResult, RequirementResult


class OverallStatus(str, Enum):
    READY = "READY"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class Assessment(BaseModel):
    """Aggregated assessment result; status calculation belongs to a later stage."""

    model_config = ConfigDict(extra="forbid")

    overall_status: OverallStatus
    requirements: list[RequirementResult]
    consistency_checks: list[ConsistencyResult]
