"""Deterministic grouping of OCR pages into logical document units."""

from __future__ import annotations

from typing import Iterable, Sequence

from schemas import DocumentUnit, OcrBlock, OcrFile, OcrPage

from .rules import find_title_match


def segment_ocr_file(ocr_file: OcrFile) -> list[DocumentUnit]:
    """Split an OCR file whenever a page contains a known document-title signal.

    Pages without a known title are continuations of the current unit. If OCR
    content appears before the first known title, it is retained as an
    unresolved unit rather than assigned to a guessed document type.
    """

    pages = sorted(ocr_file.pages, key=lambda page: page.page)
    segments: list[tuple[list[OcrPage], list[OcrBlock]]] = []
    current_pages: list[OcrPage] = []
    current_blocks: list[OcrBlock] = []

    for page in pages:
        starts_known_document = find_title_match(page.blocks) is not None
        if starts_known_document and current_blocks:
            segments.append((current_pages, current_blocks))
            current_pages = []
            current_blocks = []

        current_pages.append(page)
        current_blocks.extend(page.blocks)

    if current_blocks:
        segments.append((current_pages, current_blocks))

    return [
        _build_document_unit(ocr_file.file_id, index, pages, blocks)
        for index, (pages, blocks) in enumerate(segments, start=1)
    ]


def _build_document_unit(
    source_file_id: str,
    index: int,
    pages: Sequence[OcrPage],
    blocks: Iterable[OcrBlock],
) -> DocumentUnit:
    """Build a deterministic unit identifier and preserve original OCR blocks."""

    return DocumentUnit(
        document_id=f"{source_file_id}_document_{index:03d}",
        source_file_id=source_file_id,
        page_start=pages[0].page,
        page_end=pages[-1].page,
        blocks=list(blocks),
    )
