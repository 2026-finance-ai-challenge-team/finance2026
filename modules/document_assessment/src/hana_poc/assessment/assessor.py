"""Deterministic aggregation of requirement results into an assessment."""

from __future__ import annotations

from typing import Sequence

from schemas import (
    Assessment,
    ConsistencyResult,
    OverallStatus,
    RequirementResult,
    RequirementStatus,
)


def assess(
    requirements: Sequence[RequirementResult],
    consistency_checks: Sequence[ConsistencyResult],
) -> Assessment:
    """Build an assessment while preserving all upstream result contracts.

    Only blocking requirements affect the overall status. An unsatisfied blocking
    requirement takes precedence over an unknown blocking requirement.
    """

    overall_status = _overall_status(requirements)
    return Assessment(
        overall_status=overall_status,
        requirements=list(requirements),
        consistency_checks=list(consistency_checks),
    )


def _overall_status(requirements: Sequence[RequirementResult]) -> OverallStatus:
    blocking_requirements = [
        requirement for requirement in requirements if requirement.blocking
    ]
    if any(
        requirement.status is RequirementStatus.UNSATISFIED
        for requirement in blocking_requirements
    ):
        return OverallStatus.ACTION_REQUIRED
    if any(
        requirement.status is RequirementStatus.UNKNOWN
        for requirement in blocking_requirements
    ):
        return OverallStatus.REVIEW_REQUIRED
    return OverallStatus.READY
