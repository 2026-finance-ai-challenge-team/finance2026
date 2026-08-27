"""Unit tests for the shared schema contracts."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest

from pydantic import ValidationError

from schemas import (
    Assessment,
    ClassificationMethod,
    ClassificationStatus,
    ClassifiedDocument,
    ConsistencyParticipant,
    ConsistencyResult,
    DocumentType,
    DocumentUnit,
    ExtractedField,
    ExtractionMethod,
    FieldStatus,
    OcrBlock,
    OverallStatus,
    PageRange,
    PocInput,
    RequirementResult,
    RequirementStatus,
    StructuredDocument,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def make_block() -> OcrBlock:
    return OcrBlock(
        block_id="block_001",
        text="사업자등록증명",
        bbox=[],
        confidence=0.99,
    )


class PocInputSchemaTests(unittest.TestCase):
    def test_all_fixture_inputs_validate(self) -> None:
        fixture_paths = sorted(REPOSITORY_ROOT.glob("fixtures/*/input.json"))

        self.assertEqual(len(fixture_paths), 8)
        for fixture_path in fixture_paths:
            with self.subTest(fixture=fixture_path.parent.name):
                parsed = PocInput.model_validate_json(fixture_path.read_text())
                self.assertEqual(parsed.application_context.application_date, date(2026, 8, 1))
                self.assertGreaterEqual(len(parsed.files), 1)

    def test_input_rejects_out_of_range_ocr_confidence(self) -> None:
        with self.assertRaises(ValidationError):
            OcrBlock(block_id="b1", text="text", bbox=[], confidence=1.01)

    def test_input_rejects_unknown_top_level_fields(self) -> None:
        with self.assertRaises(ValidationError):
            PocInput.model_validate(
                {
                    "application_context": {},
                    "files": [
                        {
                            "file_id": "file_001",
                            "pages": [
                                {
                                    "page": 1,
                                    "blocks": [
                                        {
                                            "block_id": "b1",
                                            "text": "text",
                                            "bbox": [],
                                            "confidence": 0.9,
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                    "unexpected": True,
                }
            )


class DownstreamContractTests(unittest.TestCase):
    def test_unknown_extracted_field_requires_null_values(self) -> None:
        field = ExtractedField(
            name="representative_name",
            value=None,
            normalized_value=None,
            status=FieldStatus.UNKNOWN,
            extraction_method=ExtractionMethod.RULE,
        )
        self.assertIsNone(field.value)

        with self.assertRaises(ValidationError):
            ExtractedField(
                name="representative_name",
                value="",
                normalized_value="",
                status=FieldStatus.UNKNOWN,
                extraction_method=ExtractionMethod.RULE,
            )

    def test_known_extracted_field_requires_value_and_evidence(self) -> None:
        with self.assertRaises(ValidationError):
            ExtractedField(
                name="corporation_name",
                value=None,
                normalized_value=None,
                status=FieldStatus.KNOWN,
                extraction_method=ExtractionMethod.RULE,
            )

        with self.assertRaises(ValidationError):
            ExtractedField(
                name="corporation_name",
                value="주식회사 하나테크",
                normalized_value="주식회사하나테크",
                status=FieldStatus.KNOWN,
                extraction_method=ExtractionMethod.RULE,
            )

    def test_document_unit_rejects_reversed_page_range(self) -> None:
        with self.assertRaises(ValidationError):
            DocumentUnit(
                document_id="doc_001",
                source_file_id="file_001",
                page_start=2,
                page_end=1,
                blocks=[make_block()],
            )

    def test_unresolved_classification_allows_known_candidates_only(self) -> None:
        block = make_block()
        classification = ClassifiedDocument(
            document_id="unknown_doc_001",
            document_type=DocumentType.UNKNOWN,
            classification_status=ClassificationStatus.UNKNOWN,
            classification_method=ClassificationMethod.LLM,
            confidence=None,
            evidence_block_ids=[block.block_id],
            candidate_document_types=[DocumentType.CORPORATE_REGISTRY],
            blocks=[block],
            source_file_id="file_unknown",
            page_start=1,
            page_end=1,
        )

        self.assertEqual(
            classification.candidate_document_types,
            [DocumentType.CORPORATE_REGISTRY],
        )

        with self.assertRaises(ValidationError):
            ClassifiedDocument(
                document_id="unknown_doc_002",
                document_type=DocumentType.UNKNOWN,
                classification_status=ClassificationStatus.UNKNOWN,
                classification_method=ClassificationMethod.RULE,
                confidence=None,
                evidence_block_ids=[block.block_id],
                candidate_document_types=[DocumentType.UNKNOWN],
                blocks=[block],
                source_file_id="file_unknown",
                page_start=1,
                page_end=1,
            )

    def test_output_contracts_can_be_composed(self) -> None:
        block = make_block()
        classification = ClassifiedDocument(
            document_id="doc_001",
            document_type=DocumentType.BUSINESS_REGISTRATION_CERTIFICATE,
            classification_status=ClassificationStatus.CONFIDENT,
            classification_method=ClassificationMethod.RULE,
            confidence=0.99,
            evidence_block_ids=[block.block_id],
            blocks=[block],
            source_file_id="file_001",
            page_start=1,
            page_end=1,
        )
        corporation_name = ExtractedField(
            name="corporation_name",
            value="주식회사 하나테크",
            normalized_value="주식회사하나테크",
            status=FieldStatus.KNOWN,
            confidence=0.99,
            extraction_method=ExtractionMethod.RULE,
            evidence_block_ids=[block.block_id],
        )
        issue_date = ExtractedField(
            name="issue_date",
            value="2026-07-20",
            normalized_value="2026-07-20",
            status=FieldStatus.KNOWN,
            confidence=0.99,
            extraction_method=ExtractionMethod.RULE,
            evidence_block_ids=[block.block_id],
        )
        structured_document = StructuredDocument(
            document_id="doc_001",
            document_type=DocumentType.BUSINESS_REGISTRATION_CERTIFICATE,
            classification=classification,
            fields={"corporation_name": corporation_name, "issue_date": issue_date},
            issue_date=issue_date,
            source_file_id="file_001",
            page_range=PageRange(page_start=1, page_end=1),
        )
        consistency = ConsistencyResult(
            check_id="COMPANY_NAME_MATCH",
            status=RequirementStatus.SATISFIED,
            participants=[
                ConsistencyParticipant(
                    document_id=structured_document.document_id,
                    field="corporation_name",
                    value="주식회사 하나테크",
                )
            ],
            reason_code="VALUES_MATCH",
            evidence_document_ids=[structured_document.document_id],
        )
        requirement = RequirementResult(
            requirement_id="BUSINESS_REGISTRATION_REQUIRED",
            status=RequirementStatus.SATISFIED,
            blocking=True,
            reason_code="REQUIRED_DOCUMENT_PRESENT",
            evidence=[structured_document.document_id],
        )
        assessment = Assessment(
            overall_status=OverallStatus.READY,
            requirements=[requirement],
            consistency_checks=[consistency],
        )

        self.assertEqual(assessment.overall_status, OverallStatus.READY)
        self.assertEqual(assessment.requirements[0].status, RequirementStatus.SATISFIED)


if __name__ == "__main__":
    unittest.main()
