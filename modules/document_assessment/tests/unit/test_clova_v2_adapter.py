"""Unit tests for the CLOVA General OCR V2 provider boundary."""

from __future__ import annotations

from copy import deepcopy
import unittest

from hana_poc.ocr_adapters import (
    CLOVA_IMAGE_NOT_SUCCESS,
    DUPLICATE_CLOVA_PAGE_INDEX,
    INVALID_CLOVA_RESPONSE,
    INVALID_SOURCE_FILE_ID,
    ClovaOcrConversionError,
    convert_clova_v2_response,
)


def _vertices(left: float = 10, top: float = 20) -> list[dict[str, float]]:
    return [
        {"x": left, "y": top},
        {"x": left + 100, "y": top},
        {"x": left + 100, "y": top + 30},
        {"x": left, "y": top + 30},
    ]


def _field(
    text: str = "사업자등록증명",
    confidence: float = 0.9987,
    *,
    left: float = 10,
) -> dict:
    return {
        "valueType": "ALL",
        "boundingPoly": {"vertices": _vertices(left)},
        "inferText": text,
        "inferConfidence": confidence,
        "type": "NORMAL",
        "lineBreak": True,
    }


def _image(
    *,
    uid: str = "image-001",
    page_index: int = 0,
    fields: list[dict] | None = None,
    infer_result: str = "SUCCESS",
) -> dict:
    return {
        "uid": uid,
        "name": "synthetic-document",
        "inferResult": infer_result,
        "message": infer_result,
        "validationResult": {"result": "NO_REQUESTED"},
        "convertedImageInfo": {
            "width": 1280,
            "height": 1147,
            "pageIndex": page_index,
        },
        "fields": fields if fields is not None else [_field()],
    }


def _response(images: list[dict] | None = None) -> dict:
    return {
        "_comment": "synthetic fixture metadata is intentionally ignored",
        "version": "V2",
        "requestId": "synthetic-request-001",
        "timestamp": 1755400000000,
        "images": images if images is not None else [_image()],
    }


class ClovaV2AdapterTests(unittest.TestCase):
    def test_minimal_valid_response_maps_text_confidence_bbox_and_page(self) -> None:
        result = convert_clova_v2_response(
            _response(), source_file_id="file_business_registration"
        )

        self.assertEqual(result.file_id, "file_business_registration")
        self.assertEqual(result.pages[0].page, 1)
        block = result.pages[0].blocks[0]
        self.assertEqual(block.text, "사업자등록증명")
        self.assertEqual(block.confidence, 0.9987)
        self.assertEqual(
            block.bbox,
            [10.0, 20.0, 110.0, 20.0, 110.0, 50.0, 10.0, 50.0],
        )

    def test_page_index_is_converted_from_zero_based_to_one_based(self) -> None:
        result = convert_clova_v2_response(
            _response([_image(page_index=4)]), source_file_id="file_001"
        )

        self.assertEqual(result.pages[0].page, 5)

    def test_block_ids_are_deterministic_and_do_not_contain_ocr_text(self) -> None:
        response = _response()

        first = convert_clova_v2_response(response, source_file_id="file_001")
        second = convert_clova_v2_response(response, source_file_id="file_001")

        self.assertEqual(
            first.model_dump(mode="json"), second.model_dump(mode="json")
        )
        self.assertEqual(
            first.pages[0].blocks[0].block_id,
            "clova:image-001:p0000:f0000",
        )
        self.assertNotIn("사업자등록증명", first.pages[0].blocks[0].block_id)

    def test_multiple_fields_preserve_provider_order(self) -> None:
        fields = [
            _field("첫 번째", left=10),
            _field("두 번째", left=120),
            _field("세 번째", left=230),
        ]

        result = convert_clova_v2_response(
            _response([_image(fields=fields)]), source_file_id="file_001"
        )

        self.assertEqual(
            [block.text for block in result.pages[0].blocks],
            ["첫 번째", "두 번째", "세 번째"],
        )
        self.assertEqual(
            [block.block_id for block in result.pages[0].blocks],
            [
                "clova:image-001:p0000:f0000",
                "clova:image-001:p0000:f0001",
                "clova:image-001:p0000:f0002",
            ],
        )

    def test_multiple_pages_are_sorted_by_page_index(self) -> None:
        response = _response(
            [
                _image(uid="page-3", page_index=2, fields=[_field("3쪽")]),
                _image(uid="page-1", page_index=0, fields=[_field("1쪽")]),
                _image(uid="page-2", page_index=1, fields=[_field("2쪽")]),
            ]
        )

        result = convert_clova_v2_response(response, source_file_id="file_001")

        self.assertEqual([page.page for page in result.pages], [1, 2, 3])
        self.assertEqual(
            [page.blocks[0].text for page in result.pages],
            ["1쪽", "2쪽", "3쪽"],
        )

    def test_non_success_image_is_rejected_as_conversion_error(self) -> None:
        with self.assertRaises(ClovaOcrConversionError) as raised:
            convert_clova_v2_response(
                _response([_image(infer_result="FAILURE")]),
                source_file_id="file_001",
            )

        self.assertEqual(raised.exception.reason_code, CLOVA_IMAGE_NOT_SUCCESS)

    def test_missing_required_field_is_rejected(self) -> None:
        malformed = _response()
        del malformed["images"][0]["fields"][0]["inferText"]

        with self.assertRaises(ClovaOcrConversionError) as raised:
            convert_clova_v2_response(malformed, source_file_id="file_001")

        self.assertEqual(raised.exception.reason_code, INVALID_CLOVA_RESPONSE)

    def test_polygon_must_have_exactly_four_vertices(self) -> None:
        for vertices in (_vertices()[:3], _vertices() + [{"x": 0, "y": 0}]):
            malformed = _response()
            malformed["images"][0]["fields"][0]["boundingPoly"][
                "vertices"
            ] = vertices

            with self.subTest(vertex_count=len(vertices)):
                with self.assertRaises(ClovaOcrConversionError) as raised:
                    convert_clova_v2_response(
                        malformed, source_file_id="file_001"
                    )
                self.assertEqual(
                    raised.exception.reason_code, INVALID_CLOVA_RESPONSE
                )

    def test_invalid_confidence_is_rejected_instead_of_clamped(self) -> None:
        for confidence in (-0.01, 1.01):
            malformed = _response()
            malformed["images"][0]["fields"][0][
                "inferConfidence"
            ] = confidence

            with self.subTest(confidence=confidence):
                with self.assertRaises(ClovaOcrConversionError) as raised:
                    convert_clova_v2_response(
                        malformed, source_file_id="file_001"
                    )
                self.assertEqual(
                    raised.exception.reason_code, INVALID_CLOVA_RESPONSE
                )

    def test_duplicate_page_index_is_rejected(self) -> None:
        response = _response(
            [
                _image(uid="image-001", page_index=0),
                _image(uid="image-002", page_index=0),
            ]
        )

        with self.assertRaises(ClovaOcrConversionError) as raised:
            convert_clova_v2_response(response, source_file_id="file_001")

        self.assertEqual(
            raised.exception.reason_code, DUPLICATE_CLOVA_PAGE_INDEX
        )

    def test_missing_uid_is_rejected_without_fallback_identity(self) -> None:
        malformed = _response()
        del malformed["images"][0]["uid"]

        with self.assertRaises(ClovaOcrConversionError) as raised:
            convert_clova_v2_response(malformed, source_file_id="file_001")

        self.assertEqual(raised.exception.reason_code, INVALID_CLOVA_RESPONSE)

    def test_blank_source_file_id_is_rejected(self) -> None:
        for source_file_id in ("", "   "):
            with self.subTest(source_file_id=source_file_id):
                with self.assertRaises(ClovaOcrConversionError) as raised:
                    convert_clova_v2_response(
                        deepcopy(_response()), source_file_id=source_file_id
                    )
                self.assertEqual(
                    raised.exception.reason_code, INVALID_SOURCE_FILE_ID
                )


if __name__ == "__main__":
    unittest.main()
