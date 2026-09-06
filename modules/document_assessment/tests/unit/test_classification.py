"""Unit tests for document segmentation and rule-first classification."""

from __future__ import annotations

from pathlib import Path
import unittest

from hana_poc.classification import (
    LlmClassification,
    MaskedDocumentCandidate,
    classify_document_unit,
    classify_ocr_file,
    segment_ocr_file,
)
from schemas import (
    ClassificationMethod,
    ClassificationStatus,
    DocumentType,
    DocumentUnit,
    OcrBlock,
    OcrFile,
    OcrPage,
    PocInput,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def make_file(title: str, block_id: str = "title_block") -> OcrFile:
    return OcrFile(
        file_id="file_001",
        pages=[
            OcrPage(
                page=1,
                blocks=[
                    OcrBlock(
                        block_id=block_id,
                        text=title,
                        bbox=[],
                        confidence=0.91,
                    )
                ],
            )
        ],
    )


class StaticLlmAdapter:
    def __init__(self, response: LlmClassification | None) -> None:
        self.response = response
        self.candidate: MaskedDocumentCandidate | None = None

    def classify(self, candidate: MaskedDocumentCandidate) -> LlmClassification | None:
        self.candidate = candidate
        return self.response


class RuleClassificationTests(unittest.TestCase):
    def test_known_titles_map_to_expected_document_types(self) -> None:
        expected_by_title = {
            "사업자등록증명": DocumentType.BUSINESS_REGISTRATION_CERTIFICATE,
            "등기사항전부증명서": DocumentType.CORPORATE_REGISTRY,
            "주주명부": DocumentType.SHAREHOLDER_REGISTER,
            "주식등변동상황명세서": DocumentType.STOCK_CHANGE_STATEMENT,
            "부가가치세과세표준증명": DocumentType.VAT_TAX_BASE_CERTIFICATE,
            "표준재무제표증명": DocumentType.STANDARD_FINANCIAL_STATEMENT_CERTIFICATE,
        }

        for title, expected_type in expected_by_title.items():
            with self.subTest(title=title):
                classified = classify_ocr_file(make_file(title))[0]
                self.assertEqual(classified.document_type, expected_type)
                self.assertEqual(
                    classified.classification_status, ClassificationStatus.CONFIDENT
                )
                self.assertEqual(
                    classified.classification_method, ClassificationMethod.RULE
                )
                self.assertEqual(classified.evidence_block_ids, ["title_block"])

    def test_rule_classification_does_not_require_an_llm_adapter(self) -> None:
        classified = classify_ocr_file(make_file("사업자등록증명"))[0]

        self.assertEqual(
            classified.document_type, DocumentType.BUSINESS_REGISTRATION_CERTIFICATE
        )
        self.assertEqual(classified.classification_method, ClassificationMethod.RULE)

    def test_unrecognized_document_is_final_unknown_without_an_adapter(self) -> None:
        classified = classify_ocr_file(make_file("법인 관련 증명서", "amb_1"))[0]

        self.assertEqual(classified.document_type, DocumentType.UNKNOWN)
        self.assertEqual(
            classified.classification_status, ClassificationStatus.UNKNOWN
        )
        self.assertEqual(classified.evidence_block_ids, ["amb_1"])


class LlmAdapterBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document_unit = DocumentUnit(
            document_id="doc_001",
            source_file_id="file_001",
            page_start=1,
            page_end=1,
            blocks=[
                OcrBlock(
                    block_id="amb_1",
                    text="법인 관련 증명서",
                    bbox=[],
                    confidence=0.76,
                )
            ],
        )

    def test_mock_llm_adapter_can_be_injected(self) -> None:
        adapter = StaticLlmAdapter(
            LlmClassification(
                document_type=DocumentType.CORPORATE_REGISTRY,
                confidence=0.8,
                evidence_block_ids=("amb_1",),
            )
        )

        classified = classify_document_unit(self.document_unit, llm_adapter=adapter)

        self.assertEqual(classified.document_type, DocumentType.CORPORATE_REGISTRY)
        self.assertEqual(
            classified.classification_status, ClassificationStatus.CONFIDENT
        )
        self.assertEqual(classified.classification_method, ClassificationMethod.LLM)
        self.assertEqual(classified.evidence_block_ids, ["amb_1"])
        self.assertIsNotNone(adapter.candidate)
        self.assertEqual(adapter.candidate.block_ids, ("amb_1",))
        self.assertFalse(hasattr(adapter.candidate, "blocks"))

    def test_llm_adapter_that_cannot_decide_returns_unknown(self) -> None:
        adapter = StaticLlmAdapter(None)

        classified = classify_document_unit(self.document_unit, llm_adapter=adapter)

        self.assertEqual(classified.document_type, DocumentType.UNKNOWN)
        self.assertEqual(classified.classification_status, ClassificationStatus.UNKNOWN)
        self.assertEqual(classified.classification_method, ClassificationMethod.LLM)

    def test_llm_adapter_explicit_unknown_returns_unknown(self) -> None:
        adapter = StaticLlmAdapter(
            LlmClassification(document_type=DocumentType.UNKNOWN)
        )

        classified = classify_document_unit(self.document_unit, llm_adapter=adapter)

        self.assertEqual(classified.document_type, DocumentType.UNKNOWN)
        self.assertEqual(classified.classification_status, ClassificationStatus.UNKNOWN)
        self.assertEqual(classified.classification_method, ClassificationMethod.LLM)

    def test_mock_adapter_can_return_candidates_for_an_unresolved_document(self) -> None:
        adapter = StaticLlmAdapter(
            LlmClassification(
                document_type=DocumentType.UNKNOWN,
                candidate_document_types=(DocumentType.CORPORATE_REGISTRY,),
            )
        )

        classified = classify_document_unit(self.document_unit, llm_adapter=adapter)

        self.assertEqual(classified.document_type, DocumentType.UNKNOWN)
        self.assertEqual(
            classified.candidate_document_types,
            [DocumentType.CORPORATE_REGISTRY],
        )


class SegmentationTests(unittest.TestCase):
    def test_ready_fixture_files_are_rule_classified_without_an_llm(self) -> None:
        poc_input = PocInput.model_validate_json(
            (REPOSITORY_ROOT / "fixtures/001_ready/input.json").read_text()
        )

        classified_documents = [
            document
            for ocr_file in poc_input.files
            for document in classify_ocr_file(ocr_file)
        ]

        self.assertEqual(
            [document.document_type for document in classified_documents],
            [
                DocumentType.BUSINESS_REGISTRATION_CERTIFICATE,
                DocumentType.CORPORATE_REGISTRY,
                DocumentType.SHAREHOLDER_REGISTER,
                DocumentType.VAT_TAX_BASE_CERTIFICATE,
            ],
        )
        self.assertTrue(
            all(
                document.classification_method is ClassificationMethod.RULE
                for document in classified_documents
            )
        )

    def test_combined_pdf_is_split_at_deterministic_title_signals(self) -> None:
        poc_input = PocInput.model_validate_json(
            (REPOSITORY_ROOT / "fixtures/007_multi_document_pdf/input.json").read_text()
        )

        units = segment_ocr_file(poc_input.files[0])

        self.assertEqual(
            [(unit.page_start, unit.page_end) for unit in units],
            [(1, 2), (3, 5), (6, 6), (7, 8)],
        )
        self.assertEqual([unit.source_file_id for unit in units], ["file_combined_pdf"] * 4)

    def test_combined_pdf_classifies_each_segment(self) -> None:
        poc_input = PocInput.model_validate_json(
            (REPOSITORY_ROOT / "fixtures/007_multi_document_pdf/input.json").read_text()
        )

        classified_documents = classify_ocr_file(poc_input.files[0])

        self.assertEqual(
            [document.document_type for document in classified_documents],
            [
                DocumentType.BUSINESS_REGISTRATION_CERTIFICATE,
                DocumentType.CORPORATE_REGISTRY,
                DocumentType.SHAREHOLDER_REGISTER,
                DocumentType.VAT_TAX_BASE_CERTIFICATE,
            ],
        )
        self.assertEqual(
            [(document.page_start, document.page_end) for document in classified_documents],
            [(1, 2), (3, 5), (6, 6), (7, 8)],
        )

    def test_ambiguous_fixture_remains_finally_unresolved_without_llm(self) -> None:
        poc_input = PocInput.model_validate_json(
            (REPOSITORY_ROOT / "fixtures/006_ambiguous_document/input.json").read_text()
        )

        classified_documents = classify_ocr_file(poc_input.files[1])

        self.assertEqual(len(classified_documents), 1)
        self.assertEqual(classified_documents[0].document_type, DocumentType.UNKNOWN)
        self.assertEqual(
            classified_documents[0].classification_status,
            ClassificationStatus.UNKNOWN,
        )
        self.assertEqual(
            classified_documents[0].evidence_block_ids,
            ["amb_1", "amb_2", "amb_3"],
        )
        self.assertEqual(classified_documents[0].candidate_document_types, [])


if __name__ == "__main__":
    unittest.main()
