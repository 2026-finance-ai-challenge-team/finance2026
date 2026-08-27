"""CLOVA V2 adapter integration through classification and extraction."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from hana_poc.classification import classify_ocr_file
from hana_poc.extraction import extract_structured_document
from hana_poc.ocr_adapters import convert_clova_v2_response
from schemas import DocumentType


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CLOVA_FIXTURE = (
    REPOSITORY_ROOT / "tests/fixtures/clova_v2_business_registration.json"
)


class ClovaV2ClassificationExtractionIntegrationTests(unittest.TestCase):
    def test_synthetic_response_classifies_extracts_and_preserves_evidence(self) -> None:
        response = json.loads(CLOVA_FIXTURE.read_text(encoding="utf-8"))
        ocr_file = convert_clova_v2_response(
            response,
            source_file_id="file_business_registration",
        )

        classified = classify_ocr_file(ocr_file)[0]
        structured = extract_structured_document(classified)

        self.assertEqual(
            classified.document_type,
            DocumentType.BUSINESS_REGISTRATION_CERTIFICATE,
        )
        self.assertEqual(
            classified.evidence_block_ids,
            ["clova:synthetic-business-registration-page-1:p0000:f0000"],
        )
        self.assertEqual(
            structured.fields["corporation_name"].normalized_value,
            "주식회사하나테크",
        )
        self.assertEqual(
            structured.fields["business_registration_number"].normalized_value,
            "1234567890",
        )
        self.assertEqual(
            structured.fields["representative_name"].normalized_value,
            "김하나",
        )
        self.assertEqual(
            structured.fields["corporation_name"].evidence_block_ids,
            ["clova:synthetic-business-registration-page-1:p0000:f0001"],
        )
        self.assertEqual(
            structured.fields["business_registration_number"].evidence_block_ids,
            ["clova:synthetic-business-registration-page-1:p0000:f0002"],
        )
        self.assertEqual(
            structured.fields["representative_name"].evidence_block_ids,
            ["clova:synthetic-business-registration-page-1:p0000:f0003"],
        )


if __name__ == "__main__":
    unittest.main()
