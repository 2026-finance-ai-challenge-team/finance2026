"""Declarative YAML loading and deterministic requirement evaluation."""

from .config import (
    ConsistencyCheckRule,
    DocumentPresenceRule,
    FreshnessConfiguration,
    RequirementConfiguration,
    RuleConfiguration,
    RuleConfigurationError,
    WorkflowMetadata,
    load_rule_configuration,
    parse_rule_configuration,
)
from .evaluator import (
    DOCUMENT_EXPIRED,
    DOCUMENT_TYPE_UNRESOLVED,
    FIELD_UNKNOWN,
    REQUIRED_DOCUMENT_MISSING,
    REQUIRED_DOCUMENT_PRESENT,
    evaluate_requirements,
)

__all__ = [
    "ConsistencyCheckRule",
    "DOCUMENT_EXPIRED",
    "DOCUMENT_TYPE_UNRESOLVED",
    "DocumentPresenceRule",
    "FIELD_UNKNOWN",
    "FreshnessConfiguration",
    "REQUIRED_DOCUMENT_MISSING",
    "REQUIRED_DOCUMENT_PRESENT",
    "RequirementConfiguration",
    "RuleConfiguration",
    "RuleConfigurationError",
    "WorkflowMetadata",
    "evaluate_requirements",
    "load_rule_configuration",
    "parse_rule_configuration",
]
