"""Fixture-backed integration from OCR classification through prompt projection."""

from __future__ import annotations

from pathlib import Path
import unittest

from hana_poc.assessment import assess
from hana_poc.classification import (
    LlmClassification,
    MaskedDocumentCandidate,
    classify_ocr_file,
)
from hana_poc.explanation import build_explanation_prompt
from hana_poc.extraction import extract_structured_document
from hana_poc.rule_engine import evaluate_requirements, load_rule_configuration
from hana_poc.validation import validate_consistency
from schemas import DocumentType, PocInput


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = (
    REPOSITORY_ROOT
    / "rules/HANA_BANK/CORPORATE_NON_FACE_TO_FACE_ACCOUNT_OPENING/poc-v1.yaml"
)


class CandidateClassificationAdapter:
    """Test-only provider of the explicit unresolved candidate contract."""

    def classify(self, candidate: MaskedDocumentCandidate) -> LlmClassification:
        return LlmClassification(
            document_type=DocumentType.UNKNOWN,
            candidate_document_types=(DocumentType.CORPORATE_REGISTRY,),
        )


def build_fixture_prompt(fixture_name: str, llm_adapter=None):
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
    return build_explanation_prompt(assess(requirements, consistency_checks))


def prompt_requirement(payload, requirement_id: str):
    return next(
        requirement
        for requirement in payload["assessment"]["requirements"]
        if requirement["requirement_id"] == requirement_id
    )


class PipelineExplanationIntegrationTests(unittest.TestCase):
    def test_ready_fixture_preserves_ready_assessment_status(self) -> None:
        payload = build_fixture_prompt("001_ready")

        self.assertEqual(payload["assessment"]["overall_status"], "READY")

    def test_missing_registry_fixture_preserves_unsatisfied_requirement(self) -> None:
        payload = build_fixture_prompt("002_missing_registry")
        requirement = prompt_requirement(payload, "CORPORATE_REGISTRY_REQUIRED")

        self.assertEqual(payload["assessment"]["overall_status"], "ACTION_REQUIRED")
        self.assertEqual(requirement["status"], "UNSATISFIED")
        self.assertEqual(requirement["reason_code"], "REQUIRED_DOCUMENT_MISSING")

    def test_unknown_representative_fixture_preserves_unknown_requirement(self) -> None:
        payload = build_fixture_prompt("005_unknown_representative")
        requirement = prompt_requirement(payload, "REPRESENTATIVE_CONSISTENT")

        self.assertEqual(payload["assessment"]["overall_status"], "REVIEW_REQUIRED")
        self.assertEqual(requirement["status"], "UNKNOWN")
        self.assertEqual(requirement["reason_code"], "FIELD_UNKNOWN")

    def test_ambiguous_fixture_preserves_unresolved_document_requirement(self) -> None:
        payload = build_fixture_prompt(
            "006_ambiguous_document",
            llm_adapter=CandidateClassificationAdapter(),
        )
        requirement = prompt_requirement(payload, "CORPORATE_REGISTRY_REQUIRED")

        self.assertEqual(payload["assessment"]["overall_status"], "REVIEW_REQUIRED")
        self.assertEqual(requirement["status"], "UNKNOWN")
        self.assertEqual(requirement["reason_code"], "DOCUMENT_TYPE_UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
