"""Fixture-backed integration tests through the deterministic rule engine."""

from __future__ import annotations

from pathlib import Path
import unittest

from hana_poc.classification import (
    LlmClassification,
    MaskedDocumentCandidate,
    classify_ocr_file,
)
from hana_poc.extraction import extract_structured_document
from hana_poc.rule_engine import evaluate_requirements, load_rule_configuration
from hana_poc.validation import validate_consistency
from schemas import DocumentType, PocInput, RequirementStatus


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = (
    REPOSITORY_ROOT
    / "rules/HANA_BANK/CORPORATE_NON_FACE_TO_FACE_ACCOUNT_OPENING/poc-v1.yaml"
)


class CandidateClassificationAdapter:
    def classify(self, candidate: MaskedDocumentCandidate) -> LlmClassification:
        return LlmClassification(
            document_type=DocumentType.UNKNOWN,
            candidate_document_types=(DocumentType.CORPORATE_REGISTRY,),
        )


def evaluate_fixture(fixture_name: str, llm_adapter=None):
    poc_input = PocInput.model_validate_json(
        (REPOSITORY_ROOT / "fixtures" / fixture_name / "input.json").read_text()
    )
    documents = [
        extract_structured_document(classified)
        for ocr_file in poc_input.files
        for classified in classify_ocr_file(ocr_file, llm_adapter=llm_adapter)
    ]
    consistency_results = validate_consistency(documents, poc_input.application_context)
    requirements = evaluate_requirements(
        load_rule_configuration(RULES_PATH),
        documents,
        consistency_results,
        poc_input.application_context,
    )
    return {requirement.requirement_id: requirement for requirement in requirements}


class ClassificationExtractionValidationRuleEngineIntegrationTests(unittest.TestCase):
    def test_ready_fixture_satisfies_all_configured_requirements(self) -> None:
        requirements = evaluate_fixture("001_ready")

        self.assertEqual(len(requirements), 6)
        self.assertTrue(
            all(
                requirement.status is RequirementStatus.SATISFIED
                for requirement in requirements.values()
            )
        )

    def test_missing_registry_fixture_preserves_missing_document_result(self) -> None:
        result = evaluate_fixture("002_missing_registry")[
            "CORPORATE_REGISTRY_REQUIRED"
        ]

        self.assertEqual(result.status, RequirementStatus.UNSATISFIED)
        self.assertEqual(result.reason_code, "REQUIRED_DOCUMENT_MISSING")
        self.assertEqual(result.evidence, [])

    def test_missing_sales_fixture_preserves_missing_document_result(self) -> None:
        result = evaluate_fixture("003_missing_sales_evidence")[
            "SALES_EVIDENCE_REQUIRED"
        ]

        self.assertEqual(result.status, RequirementStatus.UNSATISFIED)
        self.assertEqual(result.reason_code, "REQUIRED_DOCUMENT_MISSING")
        self.assertEqual(result.evidence, [])

    def test_company_name_mismatch_propagates_consistency_conflict(self) -> None:
        result = evaluate_fixture("004_company_name_mismatch")[
            "CORPORATION_NAME_CONSISTENT"
        ]

        self.assertEqual(result.status, RequirementStatus.UNSATISFIED)
        self.assertEqual(result.reason_code, "KNOWN_VALUES_CONFLICT")
        self.assertIn("file_registry_document_001", result.evidence)

    def test_unknown_representative_propagates_unknown_consistency(self) -> None:
        result = evaluate_fixture("005_unknown_representative")[
            "REPRESENTATIVE_CONSISTENT"
        ]

        self.assertEqual(result.status, RequirementStatus.UNKNOWN)
        self.assertEqual(result.reason_code, "FIELD_UNKNOWN")

    def test_ambiguous_fixture_candidate_is_unknown_for_matching_requirement(self) -> None:
        result = evaluate_fixture(
            "006_ambiguous_document",
            llm_adapter=CandidateClassificationAdapter(),
        )["CORPORATE_REGISTRY_REQUIRED"]

        self.assertEqual(result.status, RequirementStatus.UNKNOWN)
        self.assertEqual(result.reason_code, "DOCUMENT_TYPE_UNRESOLVED")
        self.assertEqual(result.evidence, ["file_ambiguous_document_001"])

    def test_expired_fixture_uses_requirement_level_freshness(self) -> None:
        result = evaluate_fixture("008_expired_document")[
            "CORPORATE_REGISTRY_REQUIRED"
        ]

        self.assertEqual(result.status, RequirementStatus.UNSATISFIED)
        self.assertEqual(result.reason_code, "DOCUMENT_EXPIRED")
        self.assertEqual(result.evidence, ["file_registry_document_001"])


if __name__ == "__main__":
    unittest.main()
