"""Unit tests for deterministic, LLM-safe explanation prompt construction."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

from hana_poc.explanation import build_explanation_prompt
from schemas import (
    Assessment,
    ConsistencyParticipant,
    ConsistencyResult,
    OverallStatus,
    RequirementResult,
    RequirementStatus,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def requirement(
    requirement_id: str,
    status: RequirementStatus,
    reason_code: str,
    *,
    blocking: bool = True,
) -> RequirementResult:
    return RequirementResult(
        requirement_id=requirement_id,
        status=status,
        blocking=blocking,
        reason_code=reason_code,
        evidence=["document_001"],
    )


def assessment(
    overall_status: OverallStatus,
    requirements: list[RequirementResult],
    consistency_checks: list[ConsistencyResult] | None = None,
) -> Assessment:
    return Assessment(
        overall_status=overall_status,
        requirements=requirements,
        consistency_checks=consistency_checks or [],
    )


class ExplanationPromptTests(unittest.TestCase):
    def test_ready_action_required_and_review_required_have_valid_payloads(self) -> None:
        cases = [
            (
                OverallStatus.READY,
                requirement(
                    "READY_REQUIREMENT",
                    RequirementStatus.SATISFIED,
                    "REQUIRED_DOCUMENT_PRESENT",
                ),
                "모든 blocking 요구사항이 충족되었음을 설명하되",
            ),
            (
                OverallStatus.ACTION_REQUIRED,
                requirement(
                    "FAILED_REQUIREMENT",
                    RequirementStatus.UNSATISFIED,
                    "REQUIRED_DOCUMENT_MISSING",
                ),
                "UNSATISFIED requirement와 해당 reason_code를",
            ),
            (
                OverallStatus.REVIEW_REQUIRED,
                requirement(
                    "UNKNOWN_REQUIREMENT",
                    RequirementStatus.UNKNOWN,
                    "FIELD_UNKNOWN",
                ),
                "추가 확인 필요",
            ),
        ]

        for overall_status, requirement_result, instruction_fragment in cases:
            with self.subTest(overall_status=overall_status):
                payload = build_explanation_prompt(
                    assessment(overall_status, [requirement_result])
                )

                self.assertEqual(payload["task"], "explain_document_assessment")
                self.assertEqual(payload["language"], "ko")
                self.assertEqual(
                    payload["assessment"]["overall_status"], overall_status.value
                )
                self.assertEqual(
                    payload["assessment"]["requirements"][0]["status"],
                    requirement_result.status.value,
                )
                self.assertTrue(
                    any(
                        instruction_fragment in constraint
                        for constraint in payload["constraints"]
                    )
                )

    def test_assessment_status_and_requirement_fields_are_preserved(self) -> None:
        source_assessment = assessment(
            OverallStatus.ACTION_REQUIRED,
            [
                requirement(
                    "PRESERVED_REQUIREMENT",
                    RequirementStatus.UNSATISFIED,
                    "KNOWN_VALUES_CONFLICT",
                )
            ],
        )
        source_dump = source_assessment.model_dump(mode="json")

        payload = build_explanation_prompt(source_assessment)
        projected_requirement = payload["assessment"]["requirements"][0]

        self.assertEqual(payload["assessment"]["overall_status"], "ACTION_REQUIRED")
        self.assertEqual(projected_requirement["status"], "UNSATISFIED")
        self.assertTrue(projected_requirement["blocking"])
        self.assertEqual(projected_requirement["reason_code"], "KNOWN_VALUES_CONFLICT")
        self.assertEqual(projected_requirement["evidence"], ["document_001"])
        self.assertEqual(source_assessment.model_dump(mode="json"), source_dump)

    def test_unknown_and_unsatisfied_requirements_remain_distinct(self) -> None:
        payload = build_explanation_prompt(
            assessment(
                OverallStatus.ACTION_REQUIRED,
                [
                    requirement(
                        "DETERMINISTICALLY_UNMET",
                        RequirementStatus.UNSATISFIED,
                        "REQUIRED_DOCUMENT_MISSING",
                    ),
                    requirement(
                        "INSUFFICIENT_EVIDENCE",
                        RequirementStatus.UNKNOWN,
                        "FIELD_UNKNOWN",
                    ),
                ],
            )
        )

        statuses = {
            item["requirement_id"]: item["status"]
            for item in payload["assessment"]["requirements"]
        }

        self.assertEqual(statuses["DETERMINISTICALLY_UNMET"], "UNSATISFIED")
        self.assertEqual(statuses["INSUFFICIENT_EVIDENCE"], "UNKNOWN")
        self.assertIn("UNKNOWN을 거절로 설명하지 않는다.", payload["constraints"])
        self.assertIn(
            "UNKNOWN requirement를 UNSATISFIED requirement처럼 설명하지 않는다.",
            payload["constraints"],
        )

    def test_review_required_explicitly_prohibits_explaining_unknown_as_rejection(self) -> None:
        payload = build_explanation_prompt(
            assessment(
                OverallStatus.REVIEW_REQUIRED,
                [
                    requirement(
                        "UNKNOWN_REQUIREMENT",
                        RequirementStatus.UNKNOWN,
                        "DOCUMENT_TYPE_UNRESOLVED",
                    )
                ],
            )
        )

        self.assertTrue(
            any("거절이나 실패가 아님" in constraint for constraint in payload["constraints"])
        )
        self.assertTrue(
            any("추가 확인 필요" in constraint for constraint in payload["constraints"])
        )

    def test_constraints_prohibit_status_changes_and_new_bank_requirements(self) -> None:
        payload = build_explanation_prompt(
            assessment(
                OverallStatus.READY,
                [
                    requirement(
                        "ONLY_REQUIREMENT",
                        RequirementStatus.SATISFIED,
                        "REQUIRED_DOCUMENT_PRESENT",
                    )
                ],
            )
        )

        self.assertIn("어떠한 규칙 상태도 변경하지 않는다.", payload["constraints"])
        self.assertIn(
            "추가적인 은행 업무 요구사항을 임의로 생성하지 않는다.",
            payload["constraints"],
        )
        self.assertEqual(
            [item["requirement_id"] for item in payload["assessment"]["requirements"]],
            ["ONLY_REQUIREMENT"],
        )

    def test_projection_excludes_raw_pii_from_consistency_participants(self) -> None:
        source_assessment = assessment(
            OverallStatus.REVIEW_REQUIRED,
            [
                requirement(
                    "UNKNOWN_REQUIREMENT",
                    RequirementStatus.UNKNOWN,
                    "FIELD_UNKNOWN",
                )
            ],
            [
                ConsistencyResult(
                    check_id="REPRESENTATIVE_NAME_MATCH",
                    status=RequirementStatus.UNKNOWN,
                    participants=[
                        ConsistencyParticipant(
                            document_id="document_002",
                            field="representative_name",
                            value="김하나",
                        )
                    ],
                    reason_code="FIELD_UNKNOWN",
                    evidence_document_ids=["document_002"],
                )
            ],
        )

        serialized_payload = json.dumps(
            build_explanation_prompt(source_assessment), ensure_ascii=False
        )

        self.assertNotIn("김하나", serialized_payload)
        self.assertNotIn("participants", serialized_payload)
        self.assertEqual(
            serialized_payload.count("REPRESENTATIVE_NAME_MATCH"), 1
        )

    def test_payload_is_json_serializable_and_deterministic(self) -> None:
        source_assessment = assessment(
            OverallStatus.READY,
            [
                requirement(
                    "DETERMINISTIC_REQUIREMENT",
                    RequirementStatus.SATISFIED,
                    "REQUIRED_DOCUMENT_PRESENT",
                )
            ],
        )

        first = build_explanation_prompt(source_assessment)
        second = build_explanation_prompt(source_assessment)

        self.assertEqual(first, second)
        self.assertIsInstance(json.dumps(first), str)

    def test_explanation_package_has_no_llm_client_import(self) -> None:
        package_path = REPOSITORY_ROOT / "src/hana_poc/explanation"
        imported_modules: set[str] = set()

        for source_path in package_path.glob("*.py"):
            syntax_tree = ast.parse(source_path.read_text())
            for node in ast.walk(syntax_tree):
                if isinstance(node, ast.Import):
                    imported_modules.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    imported_modules.add(node.module)

        self.assertFalse(
            any(
                "llm" in module.lower() or "openai" in module.lower()
                for module in imported_modules
            )
        )


if __name__ == "__main__":
    unittest.main()
