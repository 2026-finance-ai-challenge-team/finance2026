"""0~1단계 · 파일 형식 판별과 페이지별 텍스트 확보.

확장자는 믿지 않는다(magic bytes로 판별). PDF는 내장 텍스트를 먼저 쓰고,
텍스트가 없는 페이지만 OCR로 넘긴다. 실측 근거는 `docs/DOC_CLASSIFY.md` §3.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# OCR 응답 캐시. 문서 원문이 들어가므로 .gitignore 대상이다.
CACHE_DIR = Path(__file__).resolve().parents[2] / ".ocr_cache"

# 페이지가 이 글자 수 미만이면 텍스트 레이어가 없다고 보고 OCR로 넘긴다.
# ponytail: 실제 발급 문서 표본으로 조정할 값. 정부24 등본은 0자, 홈택스 신고서는 1583자라
#           그 사이 어디든 되지만, 머리글만 있는 스캔본을 걸러내려면 0보다 커야 한다.
MIN_CHARS_PER_PAGE = 30

# --- 시각적 제목 검출 -------------------------------------------------------
# 문서 제목은 본문보다 크게 인쇄된다. OCR이 주는 글자 높이로 이걸 직접 잡는다.
# 실측(정부24 등본): 중앙값 21px, 제목 33~40px(1.6~1.9배), 상단 8~12% 위치.
# 크기만으로는 부족하다 — 하단 발급기관 직인도 39px로 크다. 그래서 상단 조건을 같이 건다.
TITLE_MIN_RATIO = 1.5    # 글자 높이가 페이지 중앙값의 이 배율 이상
TITLE_TOP_RATIO = 0.30   # 그리고 페이지 위에서 이 비율 안에 있을 것

# 텍스트 PDF는 글자 크기 정보가 없다. 그때만 상단 N자로 근사한다.
# ponytail: pypdf의 visitor_text로 폰트 크기를 받을 수 있다. 텍스트 PDF 오분류가
#           실제로 나오면 그때 넣는다. 지금은 사진·스캔본이 우선이다.
TITLE_FALLBACK_CHARS = 500

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
    title: str = ""     # 시각적으로 두드러진 제목 (OCR 페이지만 채워진다)

    def __post_init__(self) -> None:
        self.chars = len(self.text.strip())


def _vertical_span(field: dict[str, Any]) -> tuple[float, float]:
    """필드의 (윗변 y, 글자 높이)."""
    vertices = ((field.get("boundingPoly") or {}).get("vertices")) or []
    ys = [float(v.get("y", 0.0)) for v in vertices]
    return (min(ys), max(ys) - min(ys)) if ys else (0.0, 0.0)


def visual_title(fields: list[dict[str, Any]]) -> str:
    """페이지에서 '크게 인쇄된 상단 글자'만 골라 읽기 순서로 이어 붙인다.

    CLOVA는 자간이 넓은 제목을 낱자로 쪼개 주기 때문에(주/민/등/록/표),
    좌표로 다시 줄을 세워야 문자열이 된다.
    """
    spans = [(f, *_vertical_span(f)) for f in fields]
    heights = sorted(h for _, _, h in spans if h > 0)
    if not heights:
        return ""

    # ponytail: 필드가 적은 문서(신분증, 짧은 영수증)는 제목 글자가 중앙값을 지배해
    #           아무것도 안 잡힌다. 그때는 아래 fallback(상단 N자)으로 넘어간다.
    median = heights[len(heights) // 2]

    # '상단'은 이미지 좌표가 아니라 **글자가 실제로 있는 영역** 기준으로 잰다.
    # 사진은 문서 위아래에 여백·배경이 들어가서 이미지 좌표를 쓰면 기준이 밀린다.
    text_top = min(top for _, top, _ in spans)
    text_bottom = max(top + height for _, top, height in spans)
    text_height = text_bottom - text_top
    if text_height <= 0:
        return ""

    picked = [
        f
        for f, top, height in spans
        if height >= median * TITLE_MIN_RATIO
        and (top - text_top) <= text_height * TITLE_TOP_RATIO
    ]
    if not picked:
        return ""

    from ocr_test import clova_ocr

    return " ".join(clova_ocr.fields_to_lines(picked))


@dataclass
class Extracted:
    path: Path
    kind: str                      # pdf | jpg | png | tiff | unknown
    pages: list[Page] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    ocr_calls: int = 0              # 이 파일에 쓴 OCR API 호출 수 (무료 한도 추적용)

    @property
    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)

    @property
    def title_text(self) -> str:
        """제목으로 볼 영역. OCR 페이지는 글자 크기로 잡은 제목, 그 외는 상단 텍스트."""
        visual = "\n".join(p.title for p in self.pages if p.title)
        if visual:
            return visual
        return self.full_text[:TITLE_FALLBACK_CHARS]


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


def _cache_path(path: Path, cache_dir: Path | None = None) -> Path:
    """파일 내용 해시로 캐시 위치를 정한다. 이름이 달라도 같은 파일이면 같은 캐시다."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:32]
    return (cache_dir or CACHE_DIR) / f"{digest}.json"


def _ocr_whole_file(
    path: Path,
    timeout: float,
    cache_dir: Path | None = None,
) -> dict[int, tuple[str, str]]:
    """파일 하나를 OCR에 한 번만 보내고 페이지별 (전체 텍스트, 시각적 제목)을 돌려준다.

    CLOVA General은 PDF를 통째로 받아 images[]에 페이지별 결과를 준다.
    페이지마다 따로 호출하지 않으므로 호출 수는 파일당 1회다.

    응답은 파일 해시로 캐시한다. 무료 한도가 월 100건이라 같은 파일을 다시 돌릴 때
    한도를 또 쓰면 안 된다. 캐시에는 문서 원문이 들어가므로 `.gitignore` 대상이다.
    """
    from ocr_test import clova_ocr

    resolved_cache_dir = cache_dir or CACHE_DIR
    cached = _cache_path(path, resolved_cache_dir)
    if cached.is_file():
        response = json.loads(cached.read_text(encoding="utf-8"))
    else:
        for candidate in (Path(__file__).resolve().parents[2] / ".env", Path("ocr_test/.env")):
            clova_ocr.load_dotenv(candidate)
        config = clova_ocr.OcrConfig.from_env(timeout=timeout)
        response, _elapsed = clova_ocr.call_general_ocr(path, config)
        resolved_cache_dir.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")

    out: dict[int, tuple[str, str]] = {}
    for i, image in enumerate(response.get("images") or [], start=1):
        fields = image.get("fields") or []
        out[i] = ("\n".join(clova_ocr.fields_to_lines(fields)), visual_title(fields))
    return out


def is_cached(path: str | Path, *, cache_dir: Path | None = None) -> bool:
    """이 파일의 OCR 응답이 이미 캐시에 있나(= 호출이 필요 없나)."""
    path = Path(path).expanduser()
    return path.is_file() and _cache_path(path, cache_dir).is_file()


def extract(
    path: str | Path,
    *,
    use_ocr: bool = True,
    timeout: float = 30.0,
    cache_dir: Path | None = None,
) -> Extracted:
    """1차 추출. 내장 텍스트만 읽는다. `use_ocr=True`면 부족한 페이지를 OCR로 채운다.

    OCR 호출을 아끼려면 `use_ocr=False`로 먼저 부르고, 분류가 확정되지 않을 때만
    `apply_ocr()`를 호출한다. `classify_files()`가 그렇게 동작한다.
    """
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

    if use_ocr and needs_ocr(result):
        apply_ocr(result, timeout=timeout, cache_dir=cache_dir)
    return result


def needs_ocr(extracted: Extracted) -> bool:
    """텍스트가 부족한 페이지가 남아 있나."""
    if extracted.kind == "unknown":
        return False
    return any(p.chars < MIN_CHARS_PER_PAGE for p in extracted.pages)


def apply_ocr(
    extracted: Extracted,
    *,
    timeout: float = 30.0,
    cache_dir: Path | None = None,
) -> Extracted:
    """텍스트가 없는 페이지만 OCR로 채운다. **여기서만 API를 호출한다** (파일당 1회)."""
    targets = [p for p in extracted.pages if p.chars < MIN_CHARS_PER_PAGE]
    if not targets:
        return extracted

    # 캐시에 있으면 API를 안 쓴다. 호출 수 집계에도 넣지 않는다.
    from_cache = is_cached(extracted.path, cache_dir=cache_dir)
    try:
        ocr_pages = _ocr_whole_file(extracted.path, timeout, cache_dir=cache_dir)
    except Exception as exc:
        extracted.notes.append(f"OCR 실패: {exc}")
        return extracted

    if from_cache:
        extracted.notes.append("OCR 캐시 사용 (API 호출 없음)")
    else:
        extracted.ocr_calls += 1
    for page in targets:
        text, title = ocr_pages.get(page.index) or ("", "")
        text = text.strip()
        if text:
            page.text, page.method = text, "ocr"
            page.chars = len(text)
            page.title = title
    return extracted
