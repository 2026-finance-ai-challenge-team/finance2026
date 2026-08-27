"""Unit tests for rule-based field extraction and deterministic normalization."""

from __future__ import annotations

from pathlib import Path
import unittest

from hana_poc.classification import classify_ocr_file
from hana_poc.extraction import extract_structured_document
from hana_poc.extraction.normalization import (
    normalize_amount,
    normalize_business_registration_number,
    normalize_corporate_registration_number,
    normalize_corporation_name,
    normalize_date,
    normalize_ownership_ratio,
)
from schemas import (
    ClassificationMethod,
    ClassificationStatus,
    ClassifiedDocument,
    DocumentType,
    FieldStatus,
    OcrBlock,
    PocInput,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_classified_documents(fixture_name: str) -> list[ClassifiedDocument]:
    poc_input = PocInput.model_validate_json(
        (REPOSITORY_ROOT / "fixtures" / fixture_name / "input.json").read_text()
    )
    return [
        document
        for ocr_file in poc_input.files
        for document in classify_ocr_file(ocr_file)
    ]


def document_by_type(
    documents: list[ClassifiedDocument], document_type: DocumentType
) -> ClassifiedDocument:
    return next(document for document in documents if document.document_type is document_type)


class KnownDocumentExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = load_classified_documents("001_ready")

    def test_business_registration_fields_and_normalization(self) -> None:
        structured = extract_structured_document(
            document_by_type(
                self.documents, DocumentType.BUSINESS_REGISTRATION_CERTIFICATE
            )
        )

        self.assertEqual(structured.fields["corporation_name"].value, "주식회사 하나테크")
        self.assertEqual(
            structured.fields["corporation_name"].normalized_value,
            "주식회사하나테크",
        )
        self.assertEqual(
            structured.fields["business_registration_number"].value, "123-45-67890"
        )
        self.assertEqual(
            structured.fields["business_registration_number"].normalized_value,
            "1234567890",
        )
        self.assertEqual(structured.fields["representative_name"].value, "김하나")
        self.assertEqual(structured.issue_date.normalized_value, "2026-07-20")
        self.assertEqual(
            structured.fields["business_registration_number"].evidence_block_ids,
            ["br_3"],
        )

    def test_corporate_registry_fields(self) -> None:
        structured = extract_structured_document(
            document_by_type(self.documents, DocumentType.CORPORATE_REGISTRY)
        )

        self.assertEqual(
            structured.fields["corporate_registration_number"].normalized_value,
            "1101111234567",
        )
        self.assertEqual(
            structured.fields["head_office_address"].value,
            "서울특별시 중구 가상로 100",
        )
        self.assertEqual(
            structured.fields["head_office_address"].evidence_block_ids, ["reg_5"]
        )

    def test_shareholder_register_extracts_structured_shareholders(self) -> None:
        structured = extract_structured_document(
            document_by_type(self.documents, DocumentType.SHAREHOLDER_REGISTER)
        )

        self.assertEqual(
            structured.fields["shareholders"].value,
            [
                {"name": "이가상", "ownership_ratio": "60%"},
                {"name": "박가상", "ownership_ratio": "40%"},
            ],
        )
        self.assertEqual(
            structured.fields["shareholders"].evidence_block_ids, ["sh_3", "sh_4"]
        )
        self.assertEqual(structured.issue_date.normalized_value, "2026-07-20")

    def test_vat_certificate_extracts_sales_amount(self) -> None:
        structured = extract_structured_document(
            document_by_type(self.documents, DocumentType.VAT_TAX_BASE_CERTIFICATE)
        )

        self.assertEqual(structured.fields["sales_amount"].value, "500000000원")
        self.assertEqual(
            structured.fields["sales_amount"].normalized_value, "500000000"
        )
        self.assertEqual(structured.fields["sales_amount"].evidence_block_ids, ["sales_4"])

    def test_all_known_fields_preserve_source_evidence(self) -> None:
        for document in self.documents:
            structured = extract_structured_document(document)
            for field in structured.fields.values():
                if field.status is FieldStatus.KNOWN:
                    with self.subTest(document=document.document_id, field=field.name):
                        self.assertTrue(field.evidence_block_ids)


class UnknownAndMalformedValueTests(unittest.TestCase):
    def test_fixture_values_are_extracted_without_cross_document_or_freshness_rules(
        self,
    ) -> None:
        mismatched_documents = load_classified_documents("004_company_name_mismatch")
        mismatched_registry = extract_structured_document(
            document_by_type(mismatched_documents, DocumentType.CORPORATE_REGISTRY)
        )
        expired_documents = load_classified_documents("008_expired_document")
        expired_registry = extract_structured_document(
            document_by_type(expired_documents, DocumentType.CORPORATE_REGISTRY)
        )

        self.assertEqual(
            mismatched_registry.fields["corporation_name"].value, "주식회사 다른테크"
        )
        self.assertEqual(expired_registry.issue_date.normalized_value, "2026-03-01")

    def test_blank_registry_representative_is_unknown(self) -> None:
        documents = load_classified_documents("005_unknown_representative")
        structured = extract_structured_document(
            document_by_type(documents, DocumentType.CORPORATE_REGISTRY)
        )

        representative = structured.fields["representative_name"]
        self.assertEqual(representative.status, FieldStatus.UNKNOWN)
        self.assertIsNone(representative.value)
        self.assertIsNone(representative.normalized_value)
        self.assertEqual(representative.evidence_block_ids, ["reg_4"])

    def test_missing_registry_address_is_unknown_without_invented_evidence(self) -> None:
        documents = load_classified_documents("005_unknown_representative")
        structured = extract_structured_document(
            document_by_type(documents, DocumentType.CORPORATE_REGISTRY)
        )

        address = structured.fields["head_office_address"]
        self.assertEqual(address.status, FieldStatus.UNKNOWN)
        self.assertEqual(address.evidence_block_ids, [])

    def test_malformed_business_registration_number_becomes_unknown(self) -> None:
        document = _classified_business_registration(
            [
                _ocr_block("title", "사업자등록증명", 0.99),
                _ocr_block("number", "사업자등록번호: not-a-number", 0.99),
            ]
        )

        structured = extract_structured_document(document)

        number = structured.fields["business_registration_number"]
        self.assertEqual(number.status, FieldStatus.UNKNOWN)
        self.assertIsNone(number.value)
        self.assertEqual(number.evidence_block_ids, ["number"])

    def test_malformed_issue_date_becomes_unknown(self) -> None:
        document = _classified_business_registration(
            [
                _ocr_block("title", "사업자등록증명", 0.99),
                _ocr_block("date", "발급일자: 2026-02-30", 0.99),
            ]
        )

        structured = extract_structured_document(document)

        issue_date = structured.fields["issue_date"]
        self.assertEqual(issue_date.status, FieldStatus.UNKNOWN)
        self.assertIsNone(issue_date.value)
        self.assertEqual(issue_date.evidence_block_ids, ["date"])

    def test_unknown_document_does_not_apply_a_known_document_schema(self) -> None:
        document = ClassifiedDocument(
            document_id="unknown_document",
            document_type=DocumentType.UNKNOWN,
            classification_status=ClassificationStatus.UNKNOWN,
            classification_method=ClassificationMethod.RULE,
            confidence=None,
            evidence_block_ids=["unknown_block"],
            blocks=[_ocr_block("unknown_block", "알 수 없는 문서", 0.7)],
            source_file_id="unknown_file",
            page_start=1,
            page_end=1,
        )

        structured = extract_structured_document(document)

        self.assertEqual(structured.fields, {})
        self.assertEqual(structured.issue_date.status, FieldStatus.UNKNOWN)
        self.assertEqual(structured.issue_date.evidence_block_ids, [])


class NormalizationTests(unittest.TestCase):
    def test_normalizers_are_deterministic_and_reject_malformed_values(self) -> None:
        self.assertEqual(
            normalize_business_registration_number("123-45-67890"), "1234567890"
        )
        self.assertEqual(normalize_business_registration_number("12345"), None)
        self.assertEqual(
            normalize_corporate_registration_number("110111-1234567"), "1101111234567"
        )
        self.assertEqual(
            normalize_corporation_name("㈜ 하나테크"), "주식회사하나테크"
        )
        self.assertEqual(normalize_date("2026-07-20"), "2026-07-20")
        self.assertEqual(normalize_date("2026-02-30"), None)
        self.assertEqual(normalize_amount("500000000원"), "500000000")
        self.assertEqual(normalize_ownership_ratio("60%"), "60")
        self.assertEqual(
            normalize_business_registration_number("123-45-67890"),
            normalize_business_registration_number("123-45-67890"),
        )


def _classified_business_registration(blocks: list[OcrBlock]) -> ClassifiedDocument:
    return ClassifiedDocument(
        document_id="business_registration_document",
        document_type=DocumentType.BUSINESS_REGISTRATION_CERTIFICATE,
        classification_status=ClassificationStatus.CONFIDENT,
        classification_method=ClassificationMethod.RULE,
        confidence=0.99,
        evidence_block_ids=["title"],
        blocks=blocks,
        source_file_id="business_registration_file",
        page_start=1,
        page_end=1,
    )


def _ocr_block(block_id: str, text: str, confidence: float) -> OcrBlock:
    return OcrBlock(
        block_id=block_id,
        text=text,
        bbox=[],
        confidence=confidence,
    )


if __name__ == "__main__":
    unittest.main()
