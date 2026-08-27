"""Fixture-backed integration test for classification followed by extraction."""

from pathlib import Path
import unittest

from hana_poc.classification import classify_ocr_file
from hana_poc.extraction import extract_structured_document
from schemas import DocumentType, PocInput


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class ClassificationExtractionIntegrationTests(unittest.TestCase):
    def test_combined_pdf_segments_classifies_and_extracts_each_document(self) -> None:
        poc_input = PocInput.model_validate_json(
            (REPOSITORY_ROOT / "fixtures/007_multi_document_pdf/input.json").read_text()
        )

        structured_documents = [
            extract_structured_document(classified)
            for classified in classify_ocr_file(poc_input.files[0])
        ]

        self.assertEqual(
            [document.document_type for document in structured_documents],
            [
                DocumentType.BUSINESS_REGISTRATION_CERTIFICATE,
                DocumentType.CORPORATE_REGISTRY,
                DocumentType.SHAREHOLDER_REGISTER,
                DocumentType.VAT_TAX_BASE_CERTIFICATE,
            ],
        )
        self.assertEqual(
            [document.fields["issue_date"].normalized_value for document in structured_documents],
            ["2026-07-20", "2026-07-20", None, "2026-07-20"],
        )
        self.assertEqual(
            structured_documents[0].fields["business_registration_number"].normalized_value,
            "1234567890",
        )
        self.assertEqual(
            structured_documents[1].fields["corporate_registration_number"].normalized_value,
            "1101111234567",
        )
        self.assertEqual(
            structured_documents[3].fields["sales_amount"].normalized_value,
            "500000000",
        )


if __name__ == "__main__":
    unittest.main()
