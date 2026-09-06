"""합성 PDF를 스캔·사진처럼 열화시켜 이미지 버전 생성.

합성 PDF는 텍스트 레이어가 있어 파이프라인이 pypdf에서 종료 → CLOVA 경로 미실행.
실제 사용자는 사진을 업로드하므로 이미지 버전 필수.

PDF는 맞히는데 이미지는 틀리면 그게 찾던 문제.

pdftoppm·ImageMagick·qpdf 대신 PyMuPDF·Pillow만 사용. 팀원 환경별 CLI 설치 차이로
재현이 깨지는 것 방지. 결과는 동일.

    python tools/degrade.py
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageEnhance, ImageFilter

BASE_DIR = Path(__file__).resolve().parents[1]
SAMPLE_DIR = BASE_DIR / "data" / "samples"
LABELS_CSV = BASE_DIR / "data" / "labels.csv"
RENDER_DPI = 150


def _tilt(img: Image.Image) -> Image.Image:
    return img.rotate(-7, expand=True, fillcolor="white", resample=Image.BICUBIC)


def _dark(img: Image.Image) -> Image.Image:
    return ImageEnhance.Contrast(ImageEnhance.Brightness(img).enhance(0.70)).enhance(0.85)


def _blur(img: Image.Image) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(radius=1.6))


# (원본, 접미사, 변형). 원본이 다르면 같은 결함도 다르게 발현 → 문서 혼합
VARIANTS: tuple[tuple[str, str, object], ...] = (
    ("사업자등록증.pdf", "스캔", None),
    ("사업자등록증.pdf", "기울어짐", _tilt),
    ("법인등기부.pdf", "스캔", None),
    ("법인등기부.pdf", "어두움", _dark),
    ("주주명부.pdf", "스캔", None),
    ("주주명부.pdf", "흐림", _blur),
)

# 8쪽 중 1쪽만 스캔본인 파일이 실물에 존재. 텍스트 페이지와 이미지 페이지가
# 한 파일에 섞였을 때 페이지 단위로 갈라 처리하는지 확인
MIXED_SOURCE = "정관.pdf"
MIXED_OUTPUT = "정관_1쪽스캔.pdf"


def page_to_image(pdf_path: Path, page_no: int = 0) -> Image.Image:
    with pymupdf.open(pdf_path) as doc:
        pix = doc[page_no].get_pixmap(dpi=RENDER_DPI)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def make_variants() -> list[tuple[str, str]]:
    """이미지 버전 생성. (파일명, 원본 파일명) 목록 반환."""
    made: list[tuple[str, str]] = []
    for source, suffix, transform in VARIANTS:
        src_path = SAMPLE_DIR / source
        if not src_path.is_file():
            print(f"  건너뜀 — {source} 없음")
            continue

        img = page_to_image(src_path)
        if transform is not None:
            img = transform(img)
        out_name = f"{src_path.stem}_{suffix}.png"
        img.save(SAMPLE_DIR / out_name)
        made.append((out_name, source))
        print(f"  {out_name}")
    return made


def make_mixed() -> tuple[str, str] | None:
    """1쪽만 이미지로 교체. 나머지 쪽은 텍스트 레이어 유지."""
    src_path = SAMPLE_DIR / MIXED_SOURCE
    if not src_path.is_file():
        print(f"  건너뜀 — {MIXED_SOURCE} 없음")
        return None

    buffer = io.BytesIO()
    page_to_image(src_path).save(buffer, format="JPEG", quality=80)  # 실제 스캔본도 JPEG

    with pymupdf.open(src_path) as src, pymupdf.open() as out:
        first = src[0]
        page = out.new_page(width=first.rect.width, height=first.rect.height)
        page.insert_image(page.rect, stream=buffer.getvalue())
        if src.page_count > 1:
            out.insert_pdf(src, from_page=1)
        out.save(SAMPLE_DIR / MIXED_OUTPUT)

    print(f"  {MIXED_OUTPUT}")
    return MIXED_OUTPUT, MIXED_SOURCE


def update_labels(rows: list[tuple[str, str]]) -> None:
    """원본과 같은 expected_doc_type으로 추가. 재실행해도 중복 없음."""
    with LABELS_CSV.open(encoding="utf-8") as fp:
        reader = csv.reader(fp)
        header = next(reader)
        table = [row for row in reader if row]

    by_file = {row[0]: row for row in table}
    added = {name for name, _ in rows}
    kept = [row for row in table if row[0] not in added]

    for name, source in rows:
        origin = by_file.get(source)
        if origin is None:
            print(f"  labels.csv에 원본 {source} 없음 — {name} 제외")
            continue
        kept.append([name, origin[1], origin[2]])

    with LABELS_CSV.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(header)
        writer.writerows(kept)
    print(f"labels.csv {len(kept)}행")


def main() -> int:
    parser = argparse.ArgumentParser(description="합성 문서 품질 변형")
    parser.add_argument("--skip-labels", action="store_true", help="labels.csv 갱신 생략")
    args = parser.parse_args()

    if not SAMPLE_DIR.is_dir():
        print("data/samples/ 없음 — generate.py 먼저 실행", file=sys.stderr)
        return 1

    print("이미지 버전")
    rows = make_variants()

    print("페이지 혼합")
    mixed = make_mixed()
    if mixed:
        rows.append(mixed)

    if not rows:
        print("생성 결과 없음", file=sys.stderr)
        return 1
    if not args.skip_labels:
        update_labels(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
