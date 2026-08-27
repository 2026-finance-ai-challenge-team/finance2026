"""Models for normalized OCR input at the pipeline boundary."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


NonEmptyString = Annotated[str, StringConstraints(min_length=1)]


class OcrBlock(BaseModel):
    """A text block emitted by the upstream OCR service.

    ``text`` is intentionally not normalized here so the source OCR content is
    preserved exactly at the pipeline boundary.
    """

    model_config = ConfigDict(extra="forbid")

    block_id: NonEmptyString
    text: str
    bbox: list[float]
    confidence: float = Field(ge=0.0, le=1.0)


class OcrPage(BaseModel):
    """One 1-indexed page of a normalized OCR file."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    blocks: list[OcrBlock]


class OcrFile(BaseModel):
    """A physical uploaded file represented by its OCR pages."""

    model_config = ConfigDict(extra="forbid")

    file_id: NonEmptyString
    pages: list[OcrPage] = Field(min_length=1)


class ApplicationContext(BaseModel):
    """Structured application facts supplied separately from OCR."""

    model_config = ConfigDict(extra="forbid")

    corporation_name: Optional[NonEmptyString] = None
    business_registration_number: Optional[NonEmptyString] = None
    representative_name: Optional[NonEmptyString] = None
    application_date: Optional[date] = None


class PocInput(BaseModel):
    """Top-level schema for the CLI ``input.json`` contract."""

    model_config = ConfigDict(extra="forbid")

    application_context: ApplicationContext
    files: list[OcrFile] = Field(min_length=1)


# Kept as an acronym-preserving alias for callers that use the document name.
PoCInput = PocInput
