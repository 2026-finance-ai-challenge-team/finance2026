"""Document-unit segmentation and rule-first classification APIs."""

from .adapters import (
    ClassificationFallbackConfigurationError,
    FileBackedClassificationAdapter,
    LlmClassification,
    LlmClassificationAdapter,
    MaskedDocumentCandidate,
)
from .classifier import classify_document_unit, classify_ocr_file
from .segmentation import segment_ocr_file

__all__ = [
    "ClassificationFallbackConfigurationError",
    "FileBackedClassificationAdapter",
    "LlmClassification",
    "LlmClassificationAdapter",
    "MaskedDocumentCandidate",
    "classify_document_unit",
    "classify_ocr_file",
    "segment_ocr_file",
]
