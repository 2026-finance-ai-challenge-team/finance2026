"""Fixture-backed classification, extraction, and consistency integration tests."""

from pathlib import Path
import unittest

from hana_poc.classification import classify_ocr_file
from hana_poc.extraction import extract_structured_document
from hana_poc.validation import validate_consistency
from hana_poc.validation.validator import (
    COMPANY_NAME_MATCH,
    KNOWN_VALUES_CONFLICT,
    REPRESENTATIVE_NAME_MATCH,
)
from schemas import PocInput, RequirementStatus


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def validate_fixture(fixture_name: str):
    poc_input = PocInput.model_validate_json(
        (REPOSITORY_ROOT / "fixtures" / fixture_name / "input.json").read_text()
    )
    documents = [
        extract_structured_document(classified)
        for ocr_file in poc_input.files
        for classified in classify_ocr_file(ocr_file)
    ]
    return {
        result.check_id: result
        for result in validate_consistency(documents, poc_input.application_context)
    }


class ClassificationExtractionValidationIntegrationTests(unittest.TestCase):
    def test_ready_fixture_has_satisfied_company_and_representative_checks(self) -> None:
        results = validate_fixture("001_ready")

        self.assertEqual(
            results[COMPANY_NAME_MATCH].status, RequirementStatus.SATISFIED
        )
        self.assertEqual(
            results[REPRESENTATIVE_NAME_MATCH].status, RequirementStatus.SATISFIED
        )

    def test_company_name_mismatch_fixture_is_unsatisfied(self) -> None:
        results = validate_fixture("004_company_name_mismatch")

        self.assertEqual(
            results[COMPANY_NAME_MATCH].status, RequirementStatus.UNSATISFIED
        )
        self.assertEqual(
            results[COMPANY_NAME_MATCH].reason_code, KNOWN_VALUES_CONFLICT
        )

    def test_unknown_representative_fixture_is_unknown(self) -> None:
        results = validate_fixture("005_unknown_representative")

        self.assertEqual(
            results[REPRESENTATIVE_NAME_MATCH].status, RequirementStatus.UNKNOWN
        )


if __name__ == "__main__":
    unittest.main()
