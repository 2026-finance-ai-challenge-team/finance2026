"""Convert NAVER CLOVA General OCR V2 responses to canonical OCR files.

This module is a provider boundary only. It validates the external response and
maps provider fields to ``OcrFile``/``OcrPage``/``OcrBlock`` without performing
document classification, business-field extraction, or business normalization.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Mapping, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

from schemas import OcrBlock, OcrFile, OcrPage


INVALID_CLOVA_RESPONSE = "INVALID_CLOVA_RESPONSE"
CLOVA_IMAGE_NOT_SUCCESS = "CLOVA_IMAGE_NOT_SUCCESS"
DUPLICATE_CLOVA_PAGE_INDEX = "DUPLICATE_CLOVA_PAGE_INDEX"
INVALID_SOURCE_FILE_ID = "INVALID_SOURCE_FILE_ID"

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]


class ClovaOcrConversionError(ValueError):
    """A typed adapter-boundary failure that must not become a business status."""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


class _ClovaInputModel(BaseModel):
    """Base for provider input models that ignore unused CLOVA metadata."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class ClovaVertex(_ClovaInputModel):
    """One vertex from a CLOVA field bounding polygon."""

    x: float
    y: float


class ClovaBoundingPoly(_ClovaInputModel):
    """The four ordered vertices of a CLOVA field polygon."""

    vertices: list[ClovaVertex] = Field(min_length=4, max_length=4)


class ClovaField(_ClovaInputModel):
    """The CLOVA field values needed by the canonical OCR contract."""

    bounding_poly: ClovaBoundingPoly = Field(alias="boundingPoly")
    infer_text: str = Field(alias="inferText")
    infer_confidence: float = Field(alias="inferConfidence", ge=0.0, le=1.0)
    value_type: Optional[str] = Field(default=None, alias="valueType")
    field_type: Optional[str] = Field(default=None, alias="type")
    line_break: Optional[bool] = Field(default=None, alias="lineBreak")


class ClovaConvertedImageInfo(_ClovaInputModel):
    """Page identity and optional dimensions reported by CLOVA."""

    page_index: int = Field(alias="pageIndex", ge=0)
    width: Optional[int] = Field(default=None, ge=1)
    height: Optional[int] = Field(default=None, ge=1)


class ClovaImage(_ClovaInputModel):
    """One CLOVA image result, corresponding to one source-file page."""

    uid: NonEmptyString
    name: Optional[str] = None
    infer_result: NonEmptyString = Field(alias="inferResult")
    message: Optional[str] = None
    converted_image_info: ClovaConvertedImageInfo = Field(alias="convertedImageInfo")
    fields: list[ClovaField]

    @field_validator("uid", "infer_result")
    @classmethod
    def rejects_blank_identifiers(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class ClovaV2Response(_ClovaInputModel):
    """Validated external contract for a CLOVA General OCR V2 response."""

    version: Literal["V2"]
    request_id: NonEmptyString = Field(alias="requestId")
    timestamp: int = Field(ge=0)
    images: list[ClovaImage] = Field(min_length=1)

    @field_validator("request_id")
    @classmethod
    def rejects_blank_request_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


def convert_clova_v2_response(
    response: Mapping[str, Any], *, source_file_id: str
) -> OcrFile:
    """Map one physical file's CLOVA V2 response to a canonical ``OcrFile``.

    ``source_file_id`` is caller-provided because a CLOVA response identifies
    OCR images/pages, not the stable physical upload identity required by the
    canonical contract.
    """

    if not isinstance(source_file_id, str) or not source_file_id.strip():
        raise ClovaOcrConversionError(
            INVALID_SOURCE_FILE_ID,
            "source_file_id must be a non-blank string",
        )

    try:
        parsed = ClovaV2Response.model_validate(response)
    except ValidationError as error:
        raise ClovaOcrConversionError(
            INVALID_CLOVA_RESPONSE,
            "CLOVA V2 response does not match the supported input contract",
        ) from error

    _validate_image_results(parsed.images)
    _validate_unique_page_indexes(parsed.images)

    pages = [
        _convert_image(image)
        for image in sorted(
            parsed.images,
            key=lambda item: item.converted_image_info.page_index,
        )
    ]
    return OcrFile(file_id=source_file_id, pages=pages)


def _validate_image_results(images: list[ClovaImage]) -> None:
    for image_index, image in enumerate(images):
        if image.infer_result != "SUCCESS":
            raise ClovaOcrConversionError(
                CLOVA_IMAGE_NOT_SUCCESS,
                f"CLOVA image at index {image_index} did not report SUCCESS",
            )


def _validate_unique_page_indexes(images: list[ClovaImage]) -> None:
    page_indexes = [image.converted_image_info.page_index for image in images]
    if len(page_indexes) != len(set(page_indexes)):
        raise ClovaOcrConversionError(
            DUPLICATE_CLOVA_PAGE_INDEX,
            "CLOVA response contains duplicate pageIndex values",
        )


def _convert_image(image: ClovaImage) -> OcrPage:
    page_index = image.converted_image_info.page_index
    blocks = [
        OcrBlock(
            block_id=_block_id(image.uid, page_index, field_index),
            text=field.infer_text,
            bbox=_flatten_vertices(field.bounding_poly.vertices),
            confidence=field.infer_confidence,
        )
        for field_index, field in enumerate(image.fields)
    ]
    return OcrPage(page=page_index + 1, blocks=blocks)


def _block_id(image_uid: str, page_index: int, field_index: int) -> str:
    """Build a stable ID without including OCR text, time, or randomness."""

    return f"clova:{image_uid}:p{page_index:04d}:f{field_index:04d}"


def _flatten_vertices(vertices: list[ClovaVertex]) -> list[float]:
    """Preserve the four CLOVA vertices in their provider-reported order."""

    return [coordinate for vertex in vertices for coordinate in (vertex.x, vertex.y)]
