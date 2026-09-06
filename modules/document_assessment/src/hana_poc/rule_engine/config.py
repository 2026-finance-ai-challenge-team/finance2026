"""Typed loading and validation of declarative requirement configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from schemas import DocumentType


class RuleConfigurationError(ValueError):
    """Raised when a YAML rule set does not match the supported rule contract."""


class WorkflowMetadata(BaseModel):
    """Identity of a declarative workflow rule set."""

    model_config = ConfigDict(extra="forbid")

    bank: str
    workflow: str
    version: str

    @field_validator("bank", "workflow", "version")
    @classmethod
    def requires_non_empty_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class DocumentPresenceRule(BaseModel):
    """A requirement satisfied by at least one accepted document type."""

    model_config = ConfigDict(extra="forbid")

    any_of: list[DocumentType] = Field(min_length=1)

    @field_validator("any_of")
    @classmethod
    def does_not_accept_unresolved_document_type(
        cls, value: list[DocumentType]
    ) -> list[DocumentType]:
        if DocumentType.UNKNOWN in value:
            raise ValueError("document_presence.any_of cannot include UNKNOWN")
        return value


class ConsistencyCheckRule(BaseModel):
    """A requirement that propagates a named consistency-check result."""

    model_config = ConfigDict(extra="forbid")

    check_id: str

    @field_validator("check_id")
    @classmethod
    def requires_non_empty_check_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("check_id must not be empty")
        return value


class FreshnessConfiguration(BaseModel):
    """Freshness policy attached to one document-presence requirement."""

    model_config = ConfigDict(extra="forbid")

    max_age_days: StrictInt = Field(gt=0)


class RequirementConfiguration(BaseModel):
    """One declarative requirement and exactly one supported condition."""

    model_config = ConfigDict(extra="forbid")

    id: str
    blocking: StrictBool
    document_presence: Optional[DocumentPresenceRule] = None
    consistency_check: Optional[ConsistencyCheckRule] = None
    freshness: Optional[FreshnessConfiguration] = None

    @field_validator("id")
    @classmethod
    def requires_non_empty_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("id must not be empty")
        return value

    @model_validator(mode="after")
    def has_exactly_one_supported_rule_type(self) -> "RequirementConfiguration":
        configured_rule_count = sum(
            rule is not None
            for rule in (self.document_presence, self.consistency_check)
        )
        if configured_rule_count != 1:
            raise ValueError(
                "exactly one supported rule type must be configured: "
                "document_presence or consistency_check"
            )
        if self.freshness is not None and self.document_presence is None:
            raise ValueError("freshness is only valid with document_presence")
        return self


class RuleConfiguration(BaseModel):
    """Validated root configuration consumed by the generic evaluator."""

    model_config = ConfigDict(extra="forbid")

    workflow: WorkflowMetadata
    requirements: list[RequirementConfiguration] = Field(min_length=1)

    @model_validator(mode="after")
    def has_unique_requirement_ids(self) -> "RuleConfiguration":
        requirement_ids = [requirement.id for requirement in self.requirements]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("requirement ids must be unique")
        return self


def load_rule_configuration(path: Path) -> RuleConfiguration:
    """Load one YAML rule set and expose only a typed configuration model."""

    try:
        raw_configuration = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise RuleConfigurationError(
            f"unable to read rule configuration {path}: {error}"
        ) from error
    except yaml.YAMLError as error:
        raise RuleConfigurationError(
            f"invalid YAML rule configuration {path}: {error}"
        ) from error

    return parse_rule_configuration(raw_configuration)


def parse_rule_configuration(raw_configuration: Any) -> RuleConfiguration:
    """Validate a parsed YAML value without passing untyped dictionaries onward."""

    if not isinstance(raw_configuration, Mapping):
        raise RuleConfigurationError("rule configuration root must be a mapping")

    try:
        return RuleConfiguration.model_validate(raw_configuration)
    except ValidationError as error:
        raise RuleConfigurationError(f"invalid rule configuration: {error}") from error
