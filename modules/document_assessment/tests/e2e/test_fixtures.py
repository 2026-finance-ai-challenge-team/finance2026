"""End-to-end checks for every discovered executable fixture."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hana_poc.pipeline import DEFAULT_RULES_PATH
from hana_poc.rule_engine import load_rule_configuration

from .fixture_runner import (
    FixtureAssertionError,
    FixtureExpectedValidationError,
    assert_expected_fixture,
    discover_fixtures,
    load_expected_fixture,
    run_fixture,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = REPOSITORY_ROOT / "fixtures"


class FixtureEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rule_configuration = load_rule_configuration(DEFAULT_RULES_PATH)
        cls.fixtures = discover_fixtures(FIXTURES_ROOT)

    def test_discovers_executable_fixtures(self) -> None:
        self.assertTrue(self.fixtures)

    def test_all_discovered_fixture_partial_assertions(self) -> None:
        for fixture in self.fixtures:
            with self.subTest(fixture=fixture.directory.name):
                run_fixture(fixture, self.rule_configuration)

    def test_ready_fixture_pipeline_result_is_deterministic(self) -> None:
        ready_fixture = next(
            fixture
            for fixture in self.fixtures
            if fixture.directory.name == "001_ready"
        )

        first_result = run_fixture(ready_fixture, self.rule_configuration)
        second_result = run_fixture(ready_fixture, self.rule_configuration)

        self.assertEqual(first_result, second_result)

    def test_expected_fixture_validation_rejects_malformed_contracts(self) -> None:
        malformed_cases = {
            "missing-expected.json": {},
            "unsupported-section.json": {"expected": {"unsupported": {}}},
            "invalid-status.json": {"expected": {"overall_status": "INVALID"}},
            "malformed-requirements.json": {"expected": {"requirements": []}},
            "malformed-checks.json": {"expected": {"consistency_checks": []}},
        }
        with TemporaryDirectory() as directory:
            for filename, content in malformed_cases.items():
                expected_path = Path(directory) / filename
                expected_path.write_text(json.dumps(content), encoding="utf-8")
                with self.subTest(filename=filename):
                    with self.assertRaises(FixtureExpectedValidationError):
                        load_expected_fixture(expected_path)

    def test_partial_assertion_ignores_unspecified_output_fields(self) -> None:
        ready_fixture = next(
            fixture
            for fixture in self.fixtures
            if fixture.directory.name == "001_ready"
        )
        result = run_fixture(ready_fixture, self.rule_configuration)
        with TemporaryDirectory() as directory:
            expected_path = Path(directory) / "partial.json"
            expected_path.write_text(
                json.dumps({"expected": {"overall_status": "READY"}}),
                encoding="utf-8",
            )
            expected = load_expected_fixture(expected_path)

        assert_expected_fixture("partial", expected, result)

    def test_assertion_error_identifies_fixture_and_field(self) -> None:
        ready_fixture = next(
            fixture
            for fixture in self.fixtures
            if fixture.directory.name == "001_ready"
        )
        result = run_fixture(ready_fixture, self.rule_configuration)
        with TemporaryDirectory() as directory:
            expected_path = Path(directory) / "mismatch.json"
            expected_path.write_text(
                json.dumps(
                    {"expected": {"overall_status": "ACTION_REQUIRED"}}
                ),
                encoding="utf-8",
            )
            expected = load_expected_fixture(expected_path)

        with self.assertRaisesRegex(
            FixtureAssertionError,
            "fixture-message: assessment\\.overall_status",
        ):
            assert_expected_fixture("fixture-message", expected, result)
