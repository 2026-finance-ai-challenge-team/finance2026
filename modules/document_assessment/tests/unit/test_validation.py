"""Unit tests for deterministic cross-document consistency validation."""

from __future__ import annotations

from pathlib import Path
import unittest

from hana_poc.classification import classify_ocr_file
from hana_poc.extraction import extract_structured_document
from hana_poc.validation import validate_consistency
from hana_poc.validation.validator import (
    APPLICATION_CONTEXT_ID,
    BUSINESS_REGISTRATION_NUMBER_MATCH,
    COMPANY_NAME_MATCH,
    FIELD_UNKNOWN,
    KNOWN_VALUES_CONFLICT,
    REPRESENTATIVE_NAME_MATCH,
    VALUES_MATCH,
)
from schemas import PocInput, RequirementStatus, StructuredDocument


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_validation_input(
    fixture_name: str,
) -> tuple[list[StructuredDocument], object]:
    poc_input = PocInput.model_validate_json(
        (REPOSITORY_ROOT / "fixtures" / fixture_name / "input.json").read_text()
    )
    documents = [
        extract_structured_document(classified)
        for ocr_file in poc_input.files
        for classified in classify_ocr_file(ocr_file)
    ]
    return documents, poc_input.application_context


def result_by_check(results: list, check_id: str):
    return next(result for result in results if result.check_id == check_id)


class ConsistencyValidationTests(unittest.TestCase):
    def test_matching_known_company_and_representative_values_are_satisfied(self) -> None:
        documents, context = load_validation_input("001_ready")
        results = validate_consistency(documents, context)

        company = result_by_check(results, COMPANY_NAME_MATCH)
        representative = result_by_check(results, REPRESENTATIVE_NAME_MATCH)

        self.assertEqual(company.status, RequirementStatus.SATISFIED)
        self.assertEqual(company.reason_code, VALUES_MATCH)
        self.assertEqual(representative.status, RequirementStatus.SATISFIED)
        self.assertEqual(representative.reason_code, VALUES_MATCH)

    def test_fixture_company_name_conflict_is_unsatisfied_with_participants(self) -> None:
        documents, context = load_validation_input("004_company_name_mismatch")
        result = result_by_check(
            validate_consistency(documents, context), COMPANY_NAME_MATCH
        )

        self.assertEqual(result.status, RequirementStatus.UNSATISFIED)
        self.assertEqual(result.reason_code, KNOWN_VALUES_CONFLICT)
        self.assertIn("file_registry_document_001", result.evidence_document_ids)
        registry_participant = next(
            participant
            for participant in result.participants
            if participant.document_id == "file_registry_document_001"
        )
        self.assertEqual(registry_participant.value, "주식회사 다른테크")

    def test_fixture_unknown_representative_stays_unknown(self) -> None:
        documents, context = load_validation_input("005_unknown_representative")
        result = result_by_check(
            validate_consistency(documents, context), REPRESENTATIVE_NAME_MATCH
        )

        self.assertEqual(result.status, RequirementStatus.UNKNOWN)
        self.assertEqual(result.reason_code, FIELD_UNKNOWN)
        registry_participant = next(
            participant
            for participant in result.participants
            if participant.document_id == "file_registry_document_001"
        )
        self.assertIsNone(registry_participant.value)

    def test_normalized_business_registration_number_matches_application_context(self) -> None:
        documents, context = load_validation_input("001_ready")
        result = result_by_check(
            validate_consistency(documents, context), BUSINESS_REGISTRATION_NUMBER_MATCH
        )

        self.assertEqual(result.status, RequirementStatus.SATISFIED)
        self.assertEqual(result.reason_code, VALUES_MATCH)

    def test_application_context_is_a_participant_not_document_evidence(self) -> None:
        documents, context = load_validation_input("001_ready")
        result = result_by_check(
            validate_consistency(documents, context), COMPANY_NAME_MATCH
        )

        self.assertIn(
            APPLICATION_CONTEXT_ID,
            [participant.document_id for participant in result.participants],
        )
        self.assertNotIn(APPLICATION_CONTEXT_ID, result.evidence_document_ids)

    def test_missing_representative_document_is_unknown_not_document_requirement_result(
        self,
    ) -> None:
        documents, context = load_validation_input("001_ready")
        documents_without_registry = [
            document
            for document in documents
            if document.document_id != "file_registry_document_001"
        ]
        result = result_by_check(
            validate_consistency(documents_without_registry, context),
            REPRESENTATIVE_NAME_MATCH,
        )

        self.assertEqual(result.status, RequirementStatus.UNKNOWN)
        self.assertEqual(result.reason_code, FIELD_UNKNOWN)
        self.assertNotIn("REQUIRED_DOCUMENT", result.reason_code)
        self.assertNotIn(
            "file_registry_document_001",
            [participant.document_id for participant in result.participants],
        )

    def test_identical_inputs_produce_identical_results(self) -> None:
        documents, context = load_validation_input("001_ready")

        first = validate_consistency(documents, context)
        second = validate_consistency(documents, context)

        self.assertEqual(
            [result.model_dump(mode="json") for result in first],
            [result.model_dump(mode="json") for result in second],
        )


if __name__ == "__main__":
    unittest.main()
