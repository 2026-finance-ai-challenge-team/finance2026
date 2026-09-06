"""Public HTTP contracts for the first ProofBridge API version."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
TaskQueryString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=300),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthStatus(str, Enum):
    OK = "ok"


class OverallStatus(str, Enum):
    READY = "READY"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class DocumentStatus(str, Enum):
    READY = "READY"
    MISSING = "MISSING"
    EXPIRED = "EXPIRED"
    MISMATCH = "MISMATCH"
    UNNECESSARY = "UNNECESSARY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class HealthResponse(StrictModel):
    status: HealthStatus = HealthStatus.OK
    service: Literal["ProofBridge API"] = "ProofBridge API"
    version: str
    environment: str
    ocr_configured: bool
    llm_configured: bool


class TaskSummary(StrictModel):
    task_id: NonEmptyString
    label_ko: NonEmptyString
    bank_code: NonEmptyString
    bank_name_ko: str | None = None
    policy_key: NonEmptyString
    operation_code: str | None = None
    channel: NonEmptyString
    visitor_type: NonEmptyString
    purpose_code: str | None = None
    verified: bool
    source_url: str | None = None
    as_of: date | None = None
    last_checked: date | None = None
    demo_available: bool = False


class TaskResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    UNSUPPORTED = "UNSUPPORTED"


class TaskResolutionRequest(StrictModel):
    query: TaskQueryString


class TaskResolutionCandidate(StrictModel):
    task_id: NonEmptyString
    label_ko: NonEmptyString
    bank_code: NonEmptyString
    bank_name_ko: str | None = None
    policy_key: str | None = None
    operation_code: str | None = None
    support_status: Literal["SUPPORTED", "GUIDE_ONLY", "PLANNED"]
    confidence: float = Field(ge=0.0, le=1.0)
    lexical_score: float = Field(ge=0.0, le=1.0)
    vector_score: float = Field(ge=0.0, le=1.0)
    matched_aliases: list[NonEmptyString] = Field(default_factory=list)


class TaskKnowledgeEvidence(StrictModel):
    chunk_id: NonEmptyString
    title: NonEmptyString
    excerpt: NonEmptyString
    source_url: NonEmptyString
    verified: bool
    last_checked: date
    score: float = Field(ge=0.0, le=1.0)


class TaskResolutionResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    query: TaskQueryString
    normalized_query: NonEmptyString
    resolution: TaskResolutionStatus
    selected_task: TaskResolutionCandidate | None = None
    candidates: list[TaskResolutionCandidate] = Field(default_factory=list)
    clarification_question: str | None = None
    reason: NonEmptyString
    evidence: list[TaskKnowledgeEvidence] = Field(default_factory=list)
    retrieval_methods: list[Literal["llm", "deterministic"]]
    embedding_model: NonEmptyString


class SourceReference(StrictModel):
    title: str | None = None
    url: str | None = None
    as_of: date | None = None
    last_checked: date | None = None
    verified: bool = False


class MetadataStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"


class OwnerMatchStatus(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    UNKNOWN = "UNKNOWN"
    NOT_CHECKED = "NOT_CHECKED"


class DocumentTypeCandidate(StrictModel):
    value: NonEmptyString
    name: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class OwnerCandidate(StrictModel):
    value: NonEmptyString
    role: Literal["PERSON", "CORPORATION", "REPRESENTATIVE"]
    source_label: str | None = None


class DocumentTypeMetadata(StrictModel):
    value: str | None = None
    status: MetadataStatus
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    candidates: list[DocumentTypeCandidate] = Field(default_factory=list)
    evidence_block_ids: list[NonEmptyString] = Field(default_factory=list)


class DocumentNameMetadata(StrictModel):
    value: str | None = None
    status: MetadataStatus
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_block_ids: list[NonEmptyString] = Field(default_factory=list)


class OwnerNameMetadata(StrictModel):
    value: str | None = None
    role: Literal["PERSON", "CORPORATION", "REPRESENTATIVE"] | None = None
    status: MetadataStatus
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_label: str | None = None
    candidates: list[OwnerCandidate] = Field(default_factory=list)
    evidence_block_ids: list[NonEmptyString] = Field(default_factory=list)


class DateMetadata(StrictModel):
    value: date | None = None
    status: MetadataStatus
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_label: str | None = None
    candidates: list[date] = Field(default_factory=list)
    evidence_block_ids: list[NonEmptyString] = Field(default_factory=list)


class OwnerMatchMetadata(StrictModel):
    status: OwnerMatchStatus


class DocumentMetadata(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    document_type: DocumentTypeMetadata
    document_name: DocumentNameMetadata
    owner_name: OwnerNameMetadata
    owner_match: OwnerMatchMetadata
    issued_at: DateMetadata
    expires_at: DateMetadata
    needs_review: bool
    warnings: list[NonEmptyString] = Field(default_factory=list)


class DocumentResult(StrictModel):
    document_id: NonEmptyString
    source_name: NonEmptyString
    doc_type: str | None = None
    label_ko: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    status: DocumentStatus
    reason_code: NonEmptyString
    needs_user_confirm: bool
    classification_method: NonEmptyString = "unknown"
    metadata: DocumentMetadata | None = None


class DocumentClassificationUpdate(StrictModel):
    doc_type: NonEmptyString


class RequirementBundleResult(StrictModel):
    bundle_code: NonEmptyString
    label_ko: NonEmptyString
    status: DocumentStatus
    document_types: list[NonEmptyString]
    missing_document_types: list[NonEmptyString] = Field(default_factory=list)
    evidence_document_ids: list[NonEmptyString] = Field(default_factory=list)


class RequirementResult(StrictModel):
    requirement_id: NonEmptyString
    label_ko: NonEmptyString
    status: DocumentStatus
    blocking: bool
    reason_code: NonEmptyString
    evidence_document_ids: list[NonEmptyString] = Field(default_factory=list)
    matched_bundle_code: str | None = None
    bundles: list[RequirementBundleResult] = Field(default_factory=list)
    source: SourceReference


class AcquisitionGuide(StrictModel):
    title: NonEmptyString
    channel: NonEmptyString
    description: NonEmptyString
    steps: list[NonEmptyString] = Field(default_factory=list)
    url: str | None = None
    action_label: str | None = None
    source: SourceReference


class CompletionDocumentGuide(StrictModel):
    doc_type: NonEmptyString
    label_ko: NonEmptyString
    status: DocumentStatus
    reason: NonEmptyString
    acquisition: AcquisitionGuide
    submission_method: NonEmptyString
    submission_label: NonEmptyString
    checklist: list[NonEmptyString] = Field(default_factory=list)


class PreparationGuide(StrictModel):
    code: NonEmptyString
    label_ko: NonEmptyString
    notes: str | None = None


class TaskRequirementDocument(StrictModel):
    requirement_code: NonEmptyString
    requirement_level: NonEmptyString
    choice_group: str | None = None
    bundle_code: str | None = None
    doc_type: NonEmptyString
    label_ko: NonEmptyString
    original_required: bool | None = None
    issued_within_days: int | None = Field(default=None, ge=0)
    submission_method: NonEmptyString
    submission_label: NonEmptyString
    notes: str | None = None
    acquisition: AcquisitionGuide
    source: SourceReference


class TaskRequirementsResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    task: TaskSummary
    documents: list[TaskRequirementDocument]
    preparations: list[PreparationGuide] = Field(default_factory=list)
    warnings: list[NonEmptyString] = Field(default_factory=list)


class SubmissionGuide(StrictModel):
    title: NonEmptyString
    description: NonEmptyString
    steps: list[NonEmptyString] = Field(default_factory=list)
    url: str | None = None
    action_label: str | None = None
    expected_review: str | None = None
    source: SourceReference


class CompletionPlan(StrictModel):
    bundle_code: NonEmptyString
    bundle_label: NonEmptyString
    status: DocumentStatus
    documents: list[CompletionDocumentGuide] = Field(default_factory=list)
    preparations: list[PreparationGuide] = Field(default_factory=list)
    submission: SubmissionGuide


class AnalysisResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    session_id: UUID
    task: TaskSummary
    overall_status: OverallStatus
    checked_at: datetime
    documents: list[DocumentResult]
    requirements: list[RequirementResult]
    completion_plan: CompletionPlan | None = None
    warnings: list[NonEmptyString] = Field(default_factory=list)

    @classmethod
    def checked_now(cls) -> datetime:
        return datetime.now(timezone.utc)


class DeleteSessionResponse(StrictModel):
    session_id: UUID
    deleted: bool


class ErrorDetail(StrictModel):
    code: NonEmptyString
    message: NonEmptyString
    recovery: str | None = None


class ErrorResponse(StrictModel):
    error: ErrorDetail
