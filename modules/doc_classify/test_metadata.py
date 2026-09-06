from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.doc_classify.metadata import extract_document_metadata, extract_file_metadata


def _field(text: str, x: int, y: int, *, height: int = 10, line_break: bool = True) -> dict:
    return {
        "inferText": text,
        "inferConfidence": 0.98,
        "lineBreak": line_break,
        "boundingPoly": {
            "vertices": [
                {"x": x, "y": y},
                {"x": x + max(len(text), 1) * 10, "y": y},
                {"x": x + max(len(text), 1) * 10, "y": y + height},
                {"x": x, "y": y + height},
            ]
        },
    }


SIGNATURES = [
    {
        "doc_type": "employment_certificate",
        "label_ko": "재직증명서",
        "issuer": "주식회사 예시",
        "title_patterns": [r"재\s*직\s*증\s*명\s*서"],
        "required_anchors": ["성명", "입사일"],
        "negative_anchors": [],
        "issued_at_labels": ["발급일자", "발급일"],
    },
    {
        "doc_type": "resident_registration_copy",
        "label_ko": "주민등록표 등본",
        "issuer": "서울특별시 예시구청장",
        "title_patterns": [r"주민등록표\(?등본\)?"],
        "required_anchors": ["세대주", "주소"],
        "negative_anchors": ["초본"],
        "issued_at_labels": ["발급일자", "발급일"],
    },
]


class MetadataExtractionTest(unittest.TestCase):
    def test_labeled_fields_ignore_birth_and_hire_dates(self) -> None:
        fields = [
            _field("재 직 증 명 서", 100, 10, height=30),
            _field("성명", 10, 70, line_break=False),
            _field("김민준", 100, 70),
            _field("생년월일", 10, 100, line_break=False),
            _field("1990.01.02", 100, 100),
            _field("입사일", 10, 130, line_break=False),
            _field("2022-03-04", 100, 130),
            _field("발급일자", 10, 170, line_break=False),
            _field("2026년 9월 5일", 100, 170),
            _field("유효기간", 10, 200, line_break=False),
            _field("2026.09.05 ~ 2026.12.05", 100, 200),
            _field("주식회사 예시", 100, 240),
        ]
        result = extract_document_metadata(
            {"images": [{"fields": fields}]}, signatures=SIGNATURES, expected_owner_name="김민준"
        )

        self.assertEqual(result["document_type"]["value"], "employment_certificate")
        self.assertEqual(result["owner_name"]["value"], "김민준")
        self.assertEqual(result["owner_match"]["status"], "MATCH")
        self.assertEqual(result["issued_at"]["value"], "2026-09-05")
        self.assertEqual(result["issued_at"]["status"], "CONFIRMED")
        self.assertEqual(result["expires_at"]["value"], "2026-12-05")

    def test_bottom_certificate_date_is_inferred_not_birth_date(self) -> None:
        fields = [
            _field("주민등록표(등본)", 100, 10, height=30),
            _field("세대주 성명", 10, 70, line_break=False),
            _field("이서준", 120, 70),
            _field("생년월일", 10, 100, line_break=False),
            _field("1991.02.03", 120, 100),
            _field("주소 서울특별시 예시구", 10, 130),
            _field("위와 같이 증명합니다", 100, 190),
            _field("2026년 9월 6일", 130, 220),
            _field("서울특별시 예시구청장", 100, 250),
        ]
        result = extract_document_metadata({"images": [{"fields": fields}]}, signatures=SIGNATURES)

        self.assertEqual(result["issued_at"]["value"], "2026-09-06")
        self.assertEqual(result["issued_at"]["status"], "INFERRED")
        self.assertTrue(result["needs_review"])

    def test_unrelated_dates_do_not_become_issue_or_expiry(self) -> None:
        fields = [
            _field("확인서", 100, 10, height=30),
            _field("성명 김민준", 10, 70),
            _field("생년월일 1990.01.02", 10, 100),
            _field("납부기한 2026.09.30", 10, 130),
        ]
        result = extract_document_metadata({"images": [{"fields": fields}]}, signatures=[])

        self.assertIsNone(result["issued_at"]["value"])
        self.assertIsNone(result["expires_at"]["value"])
        self.assertNotEqual(result["issued_at"]["status"], "CONFIRMED")

    def test_corporate_owner_beats_representative_with_one_character_ocr_error(self) -> None:
        fields = [
            _field("사업자등록증", 100, 10, height=30),
            _field("법인영(단체명)", 10, 70, line_break=False),
            _field("(주)가상회사", 180, 70),
            _field("대표자", 10, 100, line_break=False),
            _field("김대표", 180, 100),
            _field("사업자등록번호", 10, 130),
        ]
        signature = {
            "doc_type": "business_registration_certificate",
            "label_ko": "사업자등록증",
            "issuer": "국세청",
            "title_patterns": [r"사업자\s*등록증"],
            "required_anchors": ["사업자등록번호", "대표자"],
            "negative_anchors": ["사업자등록증명"],
            "issued_at_labels": [],
        }
        result = extract_document_metadata({"images": [{"fields": fields}]}, signatures=[signature])

        self.assertEqual(result["owner_name"]["value"], "(주)가상회사")
        self.assertEqual(result["owner_name"]["role"], "CORPORATION")

    def test_text_pdf_uses_pypdf_without_creating_ocr_cache(self) -> None:
        from modules.doc_classify.extract import extract, is_cached, needs_ocr

        path = Path(__file__).resolve().parents[2] / "demo_docs" / "합성_재직증명서.pdf"
        before = is_cached(path)
        extracted = extract(path, use_ocr=False)
        result = extract_file_metadata(path)

        self.assertFalse(needs_ocr(extracted))
        self.assertTrue(all(page.method == "embedded" for page in extracted.pages))
        self.assertEqual(is_cached(path), before)
        self.assertEqual(result["document_type"]["value"], "employment_certificate")


if __name__ == "__main__":
    unittest.main()
