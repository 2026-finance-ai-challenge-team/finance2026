"""Unit tests for deterministic final assessment aggregation."""

from __future__ import annotations

import unittest

from hana_poc.assessment import assess
from schemas import (
    ConsistencyResult,
    OverallStatus,
    RequirementResult,
    RequirementStatus,
)


def requirement(
    status: RequirementStatus,
    *,
    requirement_id: str = "ARBITRARY_REQUIREMENT",
    blocking: bool = True,
) -> RequirementResult:
    return RequirementResult(
        requirement_id=requirement_id,
        status=status,
        blocking=blocking,
        reason_code="ARBITRARY_REASON",
        evidence=["document_001"],
    )


def consistency() -> ConsistencyResult:
    return ConsistencyResult(
        check_id="ARBITRARY_CONSISTENCY_CHECK",
        status=RequirementStatus.UNKNOWN,
        participants=[],
        reason_code="FIELD_UNKNOWN",
        evidence_document_ids=["document_002"],
    )


class AssessmentStatusTests(unittest.TestCase):
    def test_all_blocking_requirements_satisfied_is_ready(self) -> None:
        result = assess(
            [
                requirement(RequirementStatus.SATISFIED, requirement_id="FIRST"),
                requirement(RequirementStatus.SATISFIED, requirement_id="SECOND"),
            ],
            [],
        )

        self.assertEqual(result.overall_status, OverallStatus.READY)

    def test_one_blocking_unsatisfied_requirement_is_action_required(self) -> None:
        result = assess([requirement(RequirementStatus.UNSATISFIED)], [])

        self.assertEqual(result.overall_status, OverallStatus.ACTION_REQUIRED)

    def test_multiple_blocking_unsatisfied_requirements_are_action_required(self) -> None:
        result = assess(
            [
                requirement(RequirementStatus.UNSATISFIED, requirement_id="FIRST"),
                requirement(RequirementStatus.UNSATISFIED, requirement_id="SECOND"),
            ],
            [],
        )

        self.assertEqual(result.overall_status, OverallStatus.ACTION_REQUIRED)

    def test_one_blocking_unknown_requirement_is_review_required(self) -> None:
        result = assess([requirement(RequirementStatus.UNKNOWN)], [])

        self.assertEqual(result.overall_status, OverallStatus.REVIEW_REQUIRED)

    def test_multiple_blocking_unknown_requirements_are_review_required(self) -> None:
        result = assess(
            [
                requirement(RequirementStatus.UNKNOWN, requirement_id="FIRST"),
                requirement(RequirementStatus.UNKNOWN, requirement_id="SECOND"),
            ],
            [],
        )

        self.assertEqual(result.overall_status, OverallStatus.REVIEW_REQUIRED)

    def test_unsatisfied_blocking_requirement_precedes_unknown(self) -> None:
        result = assess(
            [
                requirement(RequirementStatus.UNKNOWN, requirement_id="UNKNOWN"),
                requirement(RequirementStatus.UNSATISFIED, requirement_id="FAILED"),
            ],
            [],
        )

        self.assertEqual(result.overall_status, OverallStatus.ACTION_REQUIRED)

    def test_non_blocking_unsatisfied_requirement_does_not_change_ready(self) -> None:
        result = assess(
            [
                requirement(RequirementStatus.SATISFIED),
                requirement(
                    RequirementStatus.UNSATISFIED,
                    requirement_id="NON_BLOCKING_FAILED",
                    blocking=False,
                ),
            ],
            [],
        )

        self.assertEqual(result.overall_status, OverallStatus.READY)

    def test_non_blocking_unknown_requirement_does_not_change_ready(self) -> None:
        result = assess(
            [
                requirement(RequirementStatus.SATISFIED),
                requirement(
                    RequirementStatus.UNKNOWN,
                    requirement_id="NON_BLOCKING_UNKNOWN",
                    blocking=False,
                ),
            ],
            [],
        )

        self.assertEqual(result.overall_status, OverallStatus.READY)


class AssessmentContractTests(unittest.TestCase):
    def test_requirement_results_are_preserved_without_mutation(self) -> None:
        requirements = [
            requirement(
                RequirementStatus.UNKNOWN,
                requirement_id="PRESERVED_REQUIREMENT",
            )
        ]
        original_dump = requirements[0].model_dump(mode="json")

        result = assess(requirements, [])

        self.assertEqual(result.requirements, requirements)
        self.assertEqual(result.requirements[0].model_dump(mode="json"), original_dump)
        self.assertEqual(requirements[0].model_dump(mode="json"), original_dump)

    def test_consistency_results_are_preserved(self) -> None:
        consistency_result = consistency()

        result = assess([requirement(RequirementStatus.SATISFIED)], [consistency_result])

        self.assertEqual(result.consistency_checks, [consistency_result])
        self.assertEqual(
            result.consistency_checks[0].model_dump(mode="json"),
            consistency_result.model_dump(mode="json"),
        )

    def test_identical_inputs_produce_identical_assessments(self) -> None:
        requirements = [
            requirement(RequirementStatus.SATISFIED, requirement_id="KNOWN"),
            requirement(RequirementStatus.UNKNOWN, requirement_id="UNRESOLVED"),
        ]
        consistency_checks = [consistency()]

        first = assess(requirements, consistency_checks)
        second = assess(requirements, consistency_checks)

        self.assertEqual(first.model_dump(mode="json"), second.model_dump(mode="json"))

    def test_requirement_id_does_not_affect_status_calculation(self) -> None:
        result = assess(
            [
                requirement(
                    RequirementStatus.UNSATISFIED,
                    requirement_id="RENAMED_WITHOUT_ASSESSMENT_BRANCH",
                )
            ],
            [],
        )

        self.assertEqual(result.overall_status, OverallStatus.ACTION_REQUIRED)


if __name__ == "__main__":
    unittest.main()
