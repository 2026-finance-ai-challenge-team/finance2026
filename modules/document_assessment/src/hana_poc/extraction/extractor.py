"""Rule-based conversion from ``ClassifiedDocument`` to ``StructuredDocument``."""

from __future__ import annotations

import re
from typing import Callable, Optional, Sequence

from schemas import (
    ClassifiedDocument,
    DocumentType,
    ExtractedField,
    ExtractionMethod,
    FieldStatus,
    OcrBlock,
    PageRange,
    StructuredDocument,
)

from .normalization import (
    canonicalize_shareholders,
    normalize_amount,
    normalize_business_registration_number,
    normalize_corporate_registration_number,
    normalize_corporation_name,
    normalize_date,
    normalize_ownership_ratio,
    normalize_text,
)


Normalizer = Callable[[str], Optional[str]]


def extract_structured_document(
    classified_document: ClassifiedDocument,
) -> StructuredDocument:
    """Extract only the fields explicitly supported for the classified document type."""

    extractor = _EXTRACTORS.get(classified_document.document_type)
    fields = extractor(classified_document) if extractor is not None else {}
    issue_date = fields.get("issue_date", _unknown_field("issue_date"))

    return StructuredDocument(
        document_id=classified_document.document_id,
        document_type=classified_document.document_type,
        classification=classified_document,
        fields=fields,
        issue_date=issue_date,
        source_file_id=classified_document.source_file_id,
        page_range=PageRange(
            page_start=classified_document.page_start,
            page_end=classified_document.page_end,
        ),
    )


def _extract_business_registration(
    document: ClassifiedDocument,
) -> dict[str, ExtractedField]:
    return {
        "corporation_name": _extract_labeled_field(
            document, "corporation_name", ("법인명:",), normalize_corporation_name
        ),
        "business_registration_number": _extract_labeled_field(
            document,
            "business_registration_number",
            ("사업자등록번호:",),
            normalize_business_registration_number,
        ),
        "representative_name": _extract_labeled_field(
            document, "representative_name", ("대표자:",), normalize_text
        ),
        "issue_date": _extract_labeled_field(
            document, "issue_date", ("발급일자:",), normalize_date
        ),
    }


def _extract_corporate_registry(
    document: ClassifiedDocument,
) -> dict[str, ExtractedField]:
    return {
        "corporation_name": _extract_labeled_field(
            document, "corporation_name", ("상호:",), normalize_corporation_name
        ),
        "corporate_registration_number": _extract_labeled_field(
            document,
            "corporate_registration_number",
            ("법인등록번호:",),
            normalize_corporate_registration_number,
        ),
        "representative_name": _extract_labeled_field(
            document, "representative_name", ("대표이사:",), normalize_text
        ),
        "head_office_address": _extract_labeled_field(
            document, "head_office_address", ("본점:",), normalize_text
        ),
        "issue_date": _extract_labeled_field(
            document, "issue_date", ("발급일자:",), normalize_date
        ),
    }


def _extract_shareholder_register(
    document: ClassifiedDocument,
) -> dict[str, ExtractedField]:
    return {
        "corporation_name": _extract_labeled_field(
            document, "corporation_name", ("법인명:",), normalize_corporation_name
        ),
        "shareholders": _extract_shareholders(document),
        "issue_date": _extract_labeled_field(
            document, "issue_date", ("작성일자:",), normalize_date
        ),
    }


def _extract_stock_change_statement(
    document: ClassifiedDocument,
) -> dict[str, ExtractedField]:
    return {
        "corporation_name": _extract_labeled_field(
            document,
            "corporation_name",
            ("법인명:", "상호:"),
            normalize_corporation_name,
        ),
        "shareholders": _extract_shareholders(document),
        "issue_date": _extract_labeled_field(
            document, "issue_date", ("작성일자:", "발급일자:"), normalize_date
        ),
    }


def _extract_vat_tax_base_certificate(
    document: ClassifiedDocument,
) -> dict[str, ExtractedField]:
    return _extract_sales_evidence(
        document,
        corporation_labels=("상호:",),
        sales_amount_labels=("과세표준액:",),
    )


def _extract_standard_financial_statement_certificate(
    document: ClassifiedDocument,
) -> dict[str, ExtractedField]:
    return _extract_sales_evidence(
        document,
        corporation_labels=("상호:", "법인명:"),
        sales_amount_labels=("매출액:",),
    )


def _extract_sales_evidence(
    document: ClassifiedDocument,
    *,
    corporation_labels: Sequence[str],
    sales_amount_labels: Sequence[str],
) -> dict[str, ExtractedField]:
    return {
        "corporation_name": _extract_labeled_field(
            document,
            "corporation_name",
            corporation_labels,
            normalize_corporation_name,
        ),
        "business_registration_number": _extract_labeled_field(
            document,
            "business_registration_number",
            ("사업자등록번호:",),
            normalize_business_registration_number,
        ),
        "sales_amount": _extract_labeled_field(
            document, "sales_amount", sales_amount_labels, normalize_amount
        ),
        "issue_date": _extract_labeled_field(
            document, "issue_date", ("발급일자:",), normalize_date
        ),
    }


def _extract_labeled_field(
    document: ClassifiedDocument,
    name: str,
    labels: Sequence[str],
    normalizer: Normalizer,
) -> ExtractedField:
    match = _find_labeled_block(document.blocks, labels)
    if match is None:
        return _unknown_field(name)

    block, raw_value = match
    normalized_value = normalizer(raw_value)
    if normalized_value is None:
        return _unknown_field(name, evidence_block_ids=[block.block_id])

    return _known_field(
        name=name,
        value=raw_value,
        normalized_value=normalized_value,
        confidence=block.confidence,
        evidence_block_ids=[block.block_id],
    )


def _extract_shareholders(document: ClassifiedDocument) -> ExtractedField:
    shareholders: list[dict[str, str]] = []
    normalized_shareholders: list[dict[str, str]] = []
    evidence_block_ids: list[str] = []
    confidences: list[float] = []
    candidate_block_ids: list[str] = []

    for block in document.blocks:
        parsed = _parse_shareholder(block)
        if block.text.startswith("주주:"):
            candidate_block_ids.append(block.block_id)
        if parsed is None:
            continue

        name, raw_ratio, normalized_ratio = parsed
        shareholders.append({"name": name, "ownership_ratio": raw_ratio})
        normalized_shareholders.append(
            {"name": normalize_text(name) or name, "ownership_ratio": normalized_ratio}
        )
        evidence_block_ids.append(block.block_id)
        confidences.append(block.confidence)

    if not shareholders:
        return _unknown_field("shareholders", evidence_block_ids=candidate_block_ids)

    return _known_field(
        name="shareholders",
        value=shareholders,
        normalized_value=canonicalize_shareholders(normalized_shareholders),
        confidence=min(confidences),
        evidence_block_ids=evidence_block_ids,
    )


def _parse_shareholder(block: OcrBlock) -> Optional[tuple[str, str, str]]:
    match = re.fullmatch(
        r"주주:\s*(?P<name>.+?)\s*/\s*지분율:\s*(?P<ratio>\d{1,3}\s*%)\s*",
        block.text,
    )
    if match is None:
        return None

    name = normalize_text(match.group("name"))
    raw_ratio = match.group("ratio").replace(" ", "")
    normalized_ratio = normalize_ownership_ratio(raw_ratio)
    if name is None or normalized_ratio is None:
        return None
    return name, raw_ratio, normalized_ratio


def _find_labeled_block(
    blocks: Sequence[OcrBlock], labels: Sequence[str]
) -> Optional[tuple[OcrBlock, str]]:
    for block in blocks:
        for label in labels:
            if block.text.startswith(label):
                return block, block.text[len(label) :].strip()
    return None


def _known_field(
    *,
    name: str,
    value: object,
    normalized_value: str,
    confidence: float,
    evidence_block_ids: list[str],
) -> ExtractedField:
    return ExtractedField(
        name=name,
        value=value,
        normalized_value=normalized_value,
        status=FieldStatus.KNOWN,
        confidence=confidence,
        extraction_method=ExtractionMethod.RULE,
        evidence_block_ids=evidence_block_ids,
    )


def _unknown_field(
    name: str, evidence_block_ids: Optional[list[str]] = None
) -> ExtractedField:
    return ExtractedField(
        name=name,
        value=None,
        normalized_value=None,
        status=FieldStatus.UNKNOWN,
        confidence=None,
        extraction_method=ExtractionMethod.RULE,
        evidence_block_ids=evidence_block_ids or [],
    )


_EXTRACTORS: dict[
    DocumentType, Callable[[ClassifiedDocument], dict[str, ExtractedField]]
] = {
    DocumentType.BUSINESS_REGISTRATION_CERTIFICATE: _extract_business_registration,
    DocumentType.CORPORATE_REGISTRY: _extract_corporate_registry,
    DocumentType.SHAREHOLDER_REGISTER: _extract_shareholder_register,
    DocumentType.STOCK_CHANGE_STATEMENT: _extract_stock_change_statement,
    DocumentType.VAT_TAX_BASE_CERTIFICATE: _extract_vat_tax_base_certificate,
    DocumentType.STANDARD_FINANCIAL_STATEMENT_CERTIFICATE: (
        _extract_standard_financial_statement_certificate
    ),
}
