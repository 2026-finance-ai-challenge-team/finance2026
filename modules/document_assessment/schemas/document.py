"""Typed contracts for document segmentation, classification, and extraction."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .ocr import OcrBlock


NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
FieldValue = Union[str, int, float, bool, list[Any], dict[str, Any]]


class DocumentType(str, Enum):
    BUSINESS_REGISTRATION_CERTIFICATE = "BUSINESS_REGISTRATION_CERTIFICATE"
    CORPORATE_REGISTRY = "CORPORATE_REGISTRY"
    SHAREHOLDER_REGISTER = "SHAREHOLDER_REGISTER"
    STOCK_CHANGE_STATEMENT = "STOCK_CHANGE_STATEMENT"
    VAT_TAX_BASE_CERTIFICATE = "VAT_TAX_BASE_CERTIFICATE"
    STANDARD_FINANCIAL_STATEMENT_CERTIFICATE = (
        "STANDARD_FINANCIAL_STATEMENT_CERTIFICATE"
    )
    UNKNOWN = "UNKNOWN"


class ClassificationStatus(str, Enum):
    CONFIDENT = "CONFIDENT"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


class ClassificationMethod(str, Enum):
    RULE = "RULE"
    LLM = "LLM"
    USER = "USER"


class FieldStatus(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


class ExtractionMethod(str, Enum):
    """Method used to obtain a field, kept distinct from document classification."""

    RULE = "RULE"
    LLM = "LLM"
    USER = "USER"


class PageRange(BaseModel):
    """An inclusive, 1-indexed page range in a source OCR file."""

    model_config = ConfigDict(extra="forbid")

    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    @model_validator(mode="after")
    def has_valid_order(self) -> "PageRange":
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class DocumentUnit(BaseModel):
    """One logical document segmented from an OCR file."""

    model_config = ConfigDict(extra="forbid")

    document_id: NonEmptyString
    source_file_id: NonEmptyString
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    blocks: list[OcrBlock] = Field(min_length=1)

    @model_validator(mode="after")
    def has_valid_page_range(self) -> "DocumentUnit":
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class ClassifiedDocument(BaseModel):
    """A document unit with a bounded document-type classification result.

    Source and page provenance are carried forward from ``DocumentUnit`` so an
    extractor can construct a ``StructuredDocument`` without depending on the
    classifier's implementation details.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: NonEmptyString
    document_type: DocumentType
    classification_status: ClassificationStatus
    classification_method: ClassificationMethod
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence_block_ids: list[NonEmptyString] = Field(min_length=1)
    candidate_document_types: list[DocumentType] = Field(default_factory=list)
    blocks: list[OcrBlock] = Field(min_length=1)
    source_file_id: NonEmptyString
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    @model_validator(mode="after")
    def has_valid_page_range(self) -> "ClassifiedDocument":
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        if DocumentType.UNKNOWN in self.candidate_document_types:
            raise ValueError("candidate_document_types cannot include UNKNOWN")
        if (
            self.candidate_document_types
            and self.document_type is not DocumentType.UNKNOWN
        ):
            raise ValueError(
                "candidate_document_types are only valid for unresolved documents"
            )
        return self


class ExtractedField(BaseModel):
    """A normalized field value and the OCR evidence supporting it."""

    model_config = ConfigDict(extra="forbid")

    name: NonEmptyString
    value: Optional[FieldValue]
    normalized_value: Optional[str]
    status: FieldStatus
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    extraction_method: ExtractionMethod
    evidence_block_ids: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforces_known_unknown_semantics(self) -> "ExtractedField":
        if self.status is FieldStatus.UNKNOWN:
            if self.value is not None or self.normalized_value is not None:
                raise ValueError(
                    "UNKNOWN fields must use null for value and normalized_value"
                )
            return self

        if self.value is None:
            raise ValueError("KNOWN fields must provide a value")
        if isinstance(self.value, str) and not self.value.strip():
            raise ValueError("KNOWN string values must not be empty")
        if not self.evidence_block_ids:
            raise ValueError("KNOWN fields must include evidence_block_ids")
        return self


class StructuredDocument(BaseModel):
    """The extraction output consumed by consistency validation and rules."""

    model_config = ConfigDict(extra="forbid")

    document_id: NonEmptyString
    document_type: DocumentType
    classification: ClassifiedDocument
    fields: dict[str, ExtractedField]
    issue_date: ExtractedField
    source_file_id: NonEmptyString
    page_range: PageRange

    @model_validator(mode="after")
    def preserves_classification_identity(self) -> "StructuredDocument":
        if self.document_id != self.classification.document_id:
            raise ValueError("document_id must match classification.document_id")
        if self.document_type is not self.classification.document_type:
            raise ValueError("document_type must match classification.document_type")
        if self.source_file_id != self.classification.source_file_id:
            raise ValueError("source_file_id must match classification.source_file_id")
        if (
            self.page_range.page_start != self.classification.page_start
            or self.page_range.page_end != self.classification.page_end
        ):
            raise ValueError("page_range must match classification page range")
        if self.issue_date.name != "issue_date":
            raise ValueError("issue_date must be an ExtractedField named issue_date")
        return self
