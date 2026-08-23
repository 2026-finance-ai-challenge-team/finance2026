"""Safe abstraction boundary for optional LLM-assisted classification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, Tuple

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from schemas import DocumentType


@dataclass(frozen=True)
class MaskedDocumentCandidate:
    """Metadata made available to an optional LLM adapter.

    Raw OCR text is intentionally omitted. Any future adapter that needs text
    must introduce an explicit, reviewed masking transformation before this
    boundary rather than receiving ``DocumentUnit.blocks`` directly.
    """

    document_id: str
    source_file_id: str
    page_start: int
    page_end: int
    block_ids: Tuple[str, ...]


@dataclass(frozen=True)
class LlmClassification:
    """A bounded classification outcome returned by an injected adapter."""

    document_type: DocumentType
    confidence: Optional[float] = None
    evidence_block_ids: Tuple[str, ...] = ()
    candidate_document_types: Tuple[DocumentType, ...] = ()


class LlmClassificationAdapter(Protocol):
    """Protocol only; this package provides no LLM client or network call."""

    def classify(
        self, candidate: MaskedDocumentCandidate
    ) -> Optional[LlmClassification]:
        """Return a supported document type, or ``None`` when unresolved."""

        ...


class ClassificationFallbackConfigurationError(ValueError):
    """Raised when deterministic classification fallback data is unusable."""


@dataclass(frozen=True)
class _FallbackKey:
    """Stable identity for one segmented source-file page range."""

    source_file_id: str
    page_start: int
    page_end: int


class _FallbackResponse(BaseModel):
    """One file-backed decision exposed through the existing adapter protocol."""

    model_config = ConfigDict(extra="forbid")

    source_file_id: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    document_type: DocumentType
    evidence_block_ids: tuple[str, ...] = ()
    candidate_document_types: tuple[DocumentType, ...] = ()

    @field_validator("source_file_id")
    @classmethod
    def requires_source_file_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_file_id must not be empty")
        return value

    @field_validator("evidence_block_ids")
    @classmethod
    def requires_non_empty_evidence_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not block_id.strip() for block_id in value):
            raise ValueError("evidence_block_ids must not contain empty values")
        return value

    @field_validator("candidate_document_types")
    @classmethod
    def rejects_unknown_candidate_type(
        cls, value: tuple[DocumentType, ...]
    ) -> tuple[DocumentType, ...]:
        if DocumentType.UNKNOWN in value:
            raise ValueError("candidate_document_types cannot include UNKNOWN")
        return value

    @model_validator(mode="after")
    def validates_response_semantics(self) -> "_FallbackResponse":
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        if (
            self.document_type is not DocumentType.UNKNOWN
            and self.candidate_document_types
        ):
            raise ValueError(
                "candidate_document_types are only valid for UNKNOWN document_type"
            )
        if self.document_type is not DocumentType.UNKNOWN and not self.evidence_block_ids:
            raise ValueError("known document_type requires evidence_block_ids")
        return self

    @property
    def key(self) -> _FallbackKey:
        return _FallbackKey(
            source_file_id=self.source_file_id,
            page_start=self.page_start,
            page_end=self.page_end,
        )

    def to_classification(self) -> LlmClassification:
        return LlmClassification(
            document_type=self.document_type,
            evidence_block_ids=self.evidence_block_ids,
            candidate_document_types=self.candidate_document_types,
        )


class _FallbackConfiguration(BaseModel):
    """Validated JSON file shape for deterministic fallback decisions."""

    model_config = ConfigDict(extra="forbid")

    responses: list[_FallbackResponse] = Field(min_length=1)

    @model_validator(mode="after")
    def requires_unique_response_keys(self) -> "_FallbackConfiguration":
        keys = [response.key for response in self.responses]
        if len(keys) != len(set(keys)):
            raise ValueError("fallback responses must use unique source-file page ranges")
        return self


class FileBackedClassificationAdapter:
    """Deterministic fake fallback adapter loaded from a local JSON file.

    It uses only source-file identity and segmented page range to select a
    response. Raw OCR text is neither loaded nor inspected by this adapter.
    """

    def __init__(self, responses: tuple[_FallbackResponse, ...]) -> None:
        self._responses = {
            response.key: response.to_classification() for response in responses
        }
        self._used_keys: set[_FallbackKey] = set()

    @classmethod
    def from_json_file(cls, fallback_path: Path) -> "FileBackedClassificationAdapter":
        """Load a strictly validated deterministic fallback configuration."""

        try:
            content = fallback_path.read_text(encoding="utf-8")
        except OSError as error:
            raise ClassificationFallbackConfigurationError(
                f"unable to read classification fallback {fallback_path}: {error}"
            ) from error

        try:
            configuration = _FallbackConfiguration.model_validate_json(content)
        except ValidationError as error:
            raise ClassificationFallbackConfigurationError(
                f"invalid classification fallback {fallback_path}: {error}"
            ) from error
        return cls(tuple(configuration.responses))

    def classify(self, candidate: MaskedDocumentCandidate) -> LlmClassification:
        """Return the configured decision or fail when the stable key does not match."""

        key = _FallbackKey(
            source_file_id=candidate.source_file_id,
            page_start=candidate.page_start,
            page_end=candidate.page_end,
        )
        try:
            response = self._responses[key]
        except KeyError as error:
            raise ClassificationFallbackConfigurationError(
                "no classification fallback response matches "
                f"source_file_id={key.source_file_id!r}, "
                f"page_start={key.page_start}, page_end={key.page_end}"
            ) from error
        unknown_evidence_ids = set(response.evidence_block_ids) - set(candidate.block_ids)
        if unknown_evidence_ids:
            raise ClassificationFallbackConfigurationError(
                "classification fallback evidence must reference candidate blocks: "
                f"{sorted(unknown_evidence_ids)}"
            )
        self._used_keys.add(key)
        return response

    def ensure_all_responses_used(self) -> None:
        """Reject configuration entries that cannot match an unresolved document."""

        unused_keys = sorted(
            set(self._responses) - self._used_keys,
            key=lambda key: (key.source_file_id, key.page_start, key.page_end),
        )
        if unused_keys:
            rendered_keys = ", ".join(
                f"{key.source_file_id}:{key.page_start}-{key.page_end}"
                for key in unused_keys
            )
            raise ClassificationFallbackConfigurationError(
                "classification fallback responses did not match an unresolved "
                f"document: {rendered_keys}"
            )
