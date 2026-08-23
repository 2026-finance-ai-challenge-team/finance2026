"""Deterministic document-title rules used by segmentation and classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from schemas import DocumentType, OcrBlock


TITLE_RULES: Tuple[Tuple[str, DocumentType], ...] = (
    ("사업자등록증명", DocumentType.BUSINESS_REGISTRATION_CERTIFICATE),
    ("등기사항전부증명서", DocumentType.CORPORATE_REGISTRY),
    ("주주명부", DocumentType.SHAREHOLDER_REGISTER),
    ("주식등변동상황명세서", DocumentType.STOCK_CHANGE_STATEMENT),
    ("부가가치세과세표준증명", DocumentType.VAT_TAX_BASE_CERTIFICATE),
    (
        "표준재무제표증명",
        DocumentType.STANDARD_FINANCIAL_STATEMENT_CERTIFICATE,
    ),
)


@dataclass(frozen=True)
class RuleMatch:
    """A deterministic title match and the OCR block that proves it."""

    document_type: DocumentType
    evidence_block_id: str
    confidence: float


def find_title_match(blocks: Sequence[OcrBlock]) -> Optional[RuleMatch]:
    """Return the first literal known-title match in OCR reading order.

    This intentionally uses only deterministic literal containment. It does not
    normalize, infer, or apply semantic similarity to OCR text.
    """

    for block in blocks:
        for title, document_type in TITLE_RULES:
            if title in block.text:
                return RuleMatch(
                    document_type=document_type,
                    evidence_block_id=block.block_id,
                    confidence=block.confidence,
                )
    return None
