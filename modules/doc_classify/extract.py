"""0~1단계 · 파일 형식 판별과 페이지별 텍스트 확보.

확장자는 믿지 않는다(magic bytes로 판별). PDF는 내장 텍스트를 먼저 쓰고,
텍스트가 없는 페이지만 OCR로 넘긴다. 실측 근거는 `docs/DOC_CLASSIFY.md` §3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 페이지가 이 글자 수 미만이면 텍스트 레이어가 없다고 보고 OCR로 넘긴다.
# ponytail: 실제 발급 문서 표본으로 조정할 값. 정부24 등본은 0자, 홈택스 신고서는 1583자라
#           그 사이 어디든 되지만, 머리글만 있는 스캔본을 걸러내려면 0보다 커야 한다.
MIN_CHARS_PER_PAGE = 30

_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "pdf"),
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
)

IMAGE_KINDS = {"jpg", "png", "tiff"}


@dataclass
class Page:
    index: int          # 1부터
    text: str
    method: str         # embedded | ocr | none
    chars: int = 0

    def __post_init__(self) -> None:
        self.chars = len(self.text.strip())


@dataclass
class Extracted:
    path: Path
    kind: str                      # pdf | jpg | png | tiff | unknown
    pages: list[Page] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)


def detect_kind(path: Path) -> str:
    """확장자가 아니라 파일 앞부분 바이트로 실제 형식을 정한다."""
    head = path.read_bytes()[:16]
    for magic, kind in _MAGIC:
        if head.startswith(magic):
            return kind
    return "unknown"


def _embedded_pages(path: Path) -> list[Page]:
    from pypdf import PdfReader

    pages = []
    for i, page in enumerate(PdfReader(path).pages, start=1):
        text = (page.extract_text() or "").strip()
        pages.append(Page(index=i, text=text, method="embedded" if text else "none"))
    return pages


def _ocr_whole_file(path: Path, timeout: float) -> dict[int, str]:
    """파일 하나를 OCR에 한 번만 보내고 페이지별 텍스트를 돌려준다.

    CLOVA General은 PDF를 통째로 받아 images[]에 페이지별 결과를 준다.
    페이지마다 따로 호출하지 않으므로 호출 수는 파일당 1회다.
    """
    from ocr_test import clova_ocr

    for candidate in (Path(__file__).resolve().parents[2] / ".env", Path("ocr_test/.env")):
        clova_ocr.load_dotenv(candidate)

    config = clova_ocr.OcrConfig.from_env(timeout=timeout)
    response, _elapsed = clova_ocr.call_general_ocr(path, config)

    out: dict[int, str] = {}
    for i, image in enumerate(response.get("images") or [], start=1):
        lines = clova_ocr.fields_to_lines(image.get("fields") or [])
        out[i] = "\n".join(lines)
    return out


def extract(path: str | Path, *, use_ocr: bool = True, timeout: float = 30.0) -> Extracted:
    """파일 하나에서 페이지별 텍스트를 확보한다."""
    path = Path(path).expanduser()
    kind = detect_kind(path)
    result = Extracted(path=path, kind=kind)

    if kind == "unknown":
        result.notes.append("지원하지 않는 형식입니다(PDF/JPG/PNG/TIFF만 처리).")
        return result

    if kind == "pdf":
        try:
            result.pages = _embedded_pages(path)
        except Exception as exc:  # 암호화·손상 PDF
            result.notes.append(f"PDF 텍스트 추출 실패: {type(exc).__name__}")
            result.pages = [Page(index=1, text="", method="none")]
    else:
        result.pages = [Page(index=1, text="", method="none")]

    need_ocr = [p for p in result.pages if p.chars < MIN_CHARS_PER_PAGE]
    if not need_ocr:
        return result

    if not use_ocr:
        result.notes.append(f"텍스트 없는 페이지 {len(need_ocr)}개 — OCR 꺼져 있음(--no-ocr)")
        return result

    try:
        ocr_pages = _ocr_whole_file(path, timeout)
    except Exception as exc:
        result.notes.append(f"OCR 실패: {exc}")
        return result

    for page in need_ocr:
        text = (ocr_pages.get(page.index) or "").strip()
        if text:
            page.text, page.method = text, "ocr"
            page.chars = len(text)
    return result
