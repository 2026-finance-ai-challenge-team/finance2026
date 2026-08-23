"""Fixture-backed pipeline integration through deterministic assessment."""

from __future__ import annotations

from pathlib import Path
import unittest

from hana_poc.assessment import assess
from hana_poc.classification import (
    LlmClassification,
    MaskedDocumentCandidate,
    classify_ocr_file,
)
from hana_poc.extraction import extract_structured_document
from hana_poc.rule_engine import evaluate_requirements, load_rule_configuration
from hana_poc.validation import validate_consistency
from schemas import DocumentType, OverallStatus, PocInput


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = (
    REPOSITORY_ROOT
    / "rules/HANA_BANK/CORPORATE_NON_FACE_TO_FACE_ACCOUNT_OPENING/poc-v1.yaml"
)


class CandidateClassificationAdapter:
    """Test-only adapter providing the explicit unresolved candidate contract."""

    def classify(self, candidate: MaskedDocumentCandidate) -> LlmClassification:
        return LlmClassification(
            document_type=DocumentType.UNKNOWN,
            candidate_document_types=(DocumentType.CORPORATE_REGISTRY,),
        )


def assess_fixture(fixture_name: str, llm_adapter=None):
    poc_input = PocInput.model_validate_json(
        (REPOSITORY_ROOT / "fixtures" / fixture_name / "input.json").read_text()
    )
    documents = [
        extract_structured_document(classified)
        for ocr_file in poc_input.files
        for classified in classify_ocr_file(ocr_file, llm_adapter=llm_adapter)
    ]
    consistency_checks = validate_consistency(documents, poc_input.application_context)
    requirements = evaluate_requirements(
        load_rule_configuration(RULES_PATH),
        documents,
        consistency_checks,
        poc_input.application_context,
    )
    return assess(requirements, consistency_checks)


class PipelineAssessmentIntegrationTests(unittest.TestCase):
    def test_fixture_assessments_match_declared_overall_statuses(self) -> None:
        expected_statuses = {
            "001_ready": OverallStatus.READY,
            "002_missing_registry": OverallStatus.ACTION_REQUIRED,
            "003_missing_sales_evidence": OverallStatus.ACTION_REQUIRED,
            "004_company_name_mismatch": OverallStatus.ACTION_REQUIRED,
            "005_unknown_representative": OverallStatus.REVIEW_REQUIRED,
            "006_ambiguous_document": OverallStatus.REVIEW_REQUIRED,
            "007_multi_document_pdf": OverallStatus.READY,
            "008_expired_document": OverallStatus.ACTION_REQUIRED,
        }

        for fixture_name, expected_status in expected_statuses.items():
            with self.subTest(fixture_name=fixture_name):
                llm_adapter = (
                    CandidateClassificationAdapter()
                    if fixture_name == "006_ambiguous_document"
                    else None
                )
                result = assess_fixture(fixture_name, llm_adapter=llm_adapter)

                self.assertEqual(result.overall_status, expected_status)


if __name__ == "__main__":
    unittest.main()
