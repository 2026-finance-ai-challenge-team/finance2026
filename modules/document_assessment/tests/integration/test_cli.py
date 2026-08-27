"""Black-box command-line integration tests for deterministic pipeline output."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = (
    REPOSITORY_ROOT
    / "rules/HANA_BANK/CORPORATE_NON_FACE_TO_FACE_ACCOUNT_OPENING/poc-v1.yaml"
)
FALLBACK_PATH = (
    REPOSITORY_ROOT
    / "fixtures/006_ambiguous_document/classification_fallback.json"
)


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "hana_poc.cli", *arguments],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class CliIntegrationTests(unittest.TestCase):
    def test_ready_cli_prints_all_sections_and_supports_rule_override(self) -> None:
        completed = run_cli(
            "--rules",
            str(RULES_PATH),
            "fixtures/001_ready/input.json",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        for section in (
            "[1] INPUT",
            "[2] CLASSIFICATION",
            "[3] EXTRACTION",
            "[4] CONSISTENCY",
            "[5] RULE RESULTS",
            "[6] ASSESSMENT",
            "[7] LLM PROMPT",
        ):
            with self.subTest(section=section):
                self.assertIn(section, completed.stdout)
        self.assertIn('"overall_status": "READY"', completed.stdout)

    def test_business_outcomes_are_successful_cli_executions(self) -> None:
        cases = {
            "002_missing_registry": "ACTION_REQUIRED",
            "005_unknown_representative": "REVIEW_REQUIRED",
            "007_multi_document_pdf": "READY",
            "008_expired_document": "ACTION_REQUIRED",
        }
        for fixture_name, expected_status in cases.items():
            with self.subTest(fixture_name=fixture_name):
                completed = run_cli(f"fixtures/{fixture_name}/input.json")

                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn(
                    f'"overall_status": "{expected_status}"', completed.stdout
                )

    def test_input_error_returns_non_zero_and_writes_stderr(self) -> None:
        completed = run_cli("fixtures/missing-input.json")

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("error:", completed.stderr)

    def test_ambiguous_fixture_without_fallback_preserves_default_behavior(self) -> None:
        completed = run_cli("fixtures/006_ambiguous_document/input.json")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"overall_status": "ACTION_REQUIRED"', completed.stdout)

    def test_ambiguous_fixture_with_file_backed_fallback_requires_review(self) -> None:
        completed = run_cli(
            "fixtures/006_ambiguous_document/input.json",
            "--classification-fallback",
            str(FALLBACK_PATH),
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"requirement_id": "CORPORATE_REGISTRY_REQUIRED"', completed.stdout)
        self.assertIn('"status": "UNKNOWN"', completed.stdout)
        self.assertIn('"reason_code": "DOCUMENT_TYPE_UNRESOLVED"', completed.stdout)
        self.assertIn('"overall_status": "REVIEW_REQUIRED"', completed.stdout)


if __name__ == "__main__":
    unittest.main()
