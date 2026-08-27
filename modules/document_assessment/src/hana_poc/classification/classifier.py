"""Rule-first classification of segmented OCR document units."""

from __future__ import annotations

from typing import Optional

from schemas import (
    ClassificationMethod,
    ClassificationStatus,
    ClassifiedDocument,
    DocumentType,
    DocumentUnit,
    OcrFile,
)

from .adapters import (
    LlmClassification,
    LlmClassificationAdapter,
    MaskedDocumentCandidate,
)
from .rules import RuleMatch, find_title_match
from .segmentation import segment_ocr_file


def classify_ocr_file(
    ocr_file: OcrFile,
    llm_adapter: Optional[LlmClassificationAdapter] = None,
) -> list[ClassifiedDocument]:
    """Segment one OCR file, then classify each unit using deterministic rules first."""

    return [
        classify_document_unit(unit, llm_adapter=llm_adapter)
        for unit in segment_ocr_file(ocr_file)
    ]


def classify_document_unit(
    document_unit: DocumentUnit,
    llm_adapter: Optional[LlmClassificationAdapter] = None,
) -> ClassifiedDocument:
    """Classify one unit without invoking an adapter when a title rule matches."""

    rule_match = find_title_match(document_unit.blocks)
    if rule_match is not None:
        return _classified_from_rule(document_unit, rule_match)

    if llm_adapter is None:
        return _unresolved_classification(
            document_unit,
            status=ClassificationStatus.UNKNOWN,
            method=ClassificationMethod.RULE,
        )

    candidate = _to_masked_candidate(document_unit)
    decision = llm_adapter.classify(candidate)
    if decision is None:
        return _unresolved_classification(
            document_unit,
            status=ClassificationStatus.UNKNOWN,
            method=ClassificationMethod.LLM,
        )

    if decision.document_type is DocumentType.UNKNOWN:
        return _unresolved_classification(
            document_unit,
            status=ClassificationStatus.UNKNOWN,
            method=ClassificationMethod.LLM,
            candidate_document_types=decision.candidate_document_types,
        )

    return _classified_from_llm(document_unit, decision)


def _classified_from_rule(
    document_unit: DocumentUnit, rule_match: RuleMatch
) -> ClassifiedDocument:
    """Convert a rule title match into the public classified-document contract."""

    return ClassifiedDocument(
        document_id=document_unit.document_id,
        document_type=rule_match.document_type,
        classification_status=ClassificationStatus.CONFIDENT,
        classification_method=ClassificationMethod.RULE,
        confidence=rule_match.confidence,
        evidence_block_ids=[rule_match.evidence_block_id],
        blocks=document_unit.blocks,
        source_file_id=document_unit.source_file_id,
        page_start=document_unit.page_start,
        page_end=document_unit.page_end,
    )


def _classified_from_llm(
    document_unit: DocumentUnit, decision: LlmClassification
) -> ClassifiedDocument:
    """Validate adapter provenance before exposing a confident LLM result."""

    if decision.candidate_document_types:
        raise ValueError(
            "confident LLM classification cannot include candidate document types"
        )
    evidence_block_ids = _validate_adapter_evidence(document_unit, decision)
    return ClassifiedDocument(
        document_id=document_unit.document_id,
        document_type=decision.document_type,
        classification_status=ClassificationStatus.CONFIDENT,
        classification_method=ClassificationMethod.LLM,
        confidence=decision.confidence,
        evidence_block_ids=evidence_block_ids,
        blocks=document_unit.blocks,
        source_file_id=document_unit.source_file_id,
        page_start=document_unit.page_start,
        page_end=document_unit.page_end,
    )


def _unresolved_classification(
    document_unit: DocumentUnit,
    *,
    status: ClassificationStatus,
    method: ClassificationMethod,
    candidate_document_types: tuple[DocumentType, ...] = (),
) -> ClassifiedDocument:
    """Represent insufficient classification evidence without guessing a type."""

    return ClassifiedDocument(
        document_id=document_unit.document_id,
        document_type=DocumentType.UNKNOWN,
        classification_status=status,
        classification_method=method,
        confidence=None,
        evidence_block_ids=[block.block_id for block in document_unit.blocks],
        candidate_document_types=list(candidate_document_types),
        blocks=document_unit.blocks,
        source_file_id=document_unit.source_file_id,
        page_start=document_unit.page_start,
        page_end=document_unit.page_end,
    )


def _to_masked_candidate(document_unit: DocumentUnit) -> MaskedDocumentCandidate:
    """Create the explicit no-raw-text boundary used by optional LLM adapters."""

    return MaskedDocumentCandidate(
        document_id=document_unit.document_id,
        source_file_id=document_unit.source_file_id,
        page_start=document_unit.page_start,
        page_end=document_unit.page_end,
        block_ids=tuple(block.block_id for block in document_unit.blocks),
    )


def _validate_adapter_evidence(
    document_unit: DocumentUnit, decision: LlmClassification
) -> list[str]:
    """Require the adapter to point to actual source blocks for known results."""

    evidence_block_ids = list(decision.evidence_block_ids)
    if not evidence_block_ids:
        raise ValueError("LLM classification requires at least one evidence block ID")

    available_block_ids = {block.block_id for block in document_unit.blocks}
    unknown_block_ids = set(evidence_block_ids) - available_block_ids
    if unknown_block_ids:
        raise ValueError("LLM classification evidence must reference unit blocks")
    return evidence_block_ids
