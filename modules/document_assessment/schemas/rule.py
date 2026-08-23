"""Typed contracts for deterministic validation and rule evaluation outputs."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .evidence import ConsistencyParticipant


NonEmptyString = Annotated[str, StringConstraints(min_length=1)]


class RequirementStatus(str, Enum):
    SATISFIED = "SATISFIED"
    UNSATISFIED = "UNSATISFIED"
    UNKNOWN = "UNKNOWN"


class ConsistencyResult(BaseModel):
    """A deterministic comparison result across document and application facts."""

    model_config = ConfigDict(extra="forbid")

    check_id: NonEmptyString
    status: RequirementStatus
    participants: list[ConsistencyParticipant]
    reason_code: NonEmptyString
    evidence_document_ids: list[NonEmptyString] = Field(default_factory=list)


class RequirementResult(BaseModel):
    """The deterministic outcome for one declarative business requirement."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: NonEmptyString
    status: RequirementStatus
    blocking: bool
    reason_code: NonEmptyString
    evidence: list[NonEmptyString] = Field(default_factory=list)
