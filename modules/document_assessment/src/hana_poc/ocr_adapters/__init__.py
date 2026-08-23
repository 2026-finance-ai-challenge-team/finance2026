"""Adapters from external OCR provider responses to the canonical OCR schema."""

from .clova_v2 import (
    CLOVA_IMAGE_NOT_SUCCESS,
    DUPLICATE_CLOVA_PAGE_INDEX,
    INVALID_CLOVA_RESPONSE,
    INVALID_SOURCE_FILE_ID,
    ClovaOcrConversionError,
    convert_clova_v2_response,
)

__all__ = [
    "CLOVA_IMAGE_NOT_SUCCESS",
    "DUPLICATE_CLOVA_PAGE_INDEX",
    "INVALID_CLOVA_RESPONSE",
    "INVALID_SOURCE_FILE_ID",
    "ClovaOcrConversionError",
    "convert_clova_v2_response",
]
