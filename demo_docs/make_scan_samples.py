"""합성 PDF를 휴대폰으로 촬영한 것처럼 보이는 JPEG 회귀 샘플로 변환한다."""

from __future__ import annotations

import argparse
import random
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageEnhance, ImageFilter


HERE = Path(__file__).resolve().parent
OUT = HERE / "scans"
PDF_NAMES = (
    "합성_전기요금청구서.pdf",
    "합성_관리비고지서.pdf",
    "합성_주민등록표등본.pdf",
    "합성_세금고지서.pdf",
    "합성_건강보험자격득실확인서.pdf",
    "합성_근로계약서.pdf",
    "합성_사업자등록증.pdf",
    "합성_휴대폰요금납부확인서.pdf",
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdftoppm", default=shutil.which("pdftoppm"))
    return parser.parse_args()


def _camera_effect(source: Path, target: Path, seed: int) -> None:
    rng = random.Random(seed)
    with Image.open(source) as opened:
        page = opened.convert("RGB")

    # 저가형 스캐너/휴대폰 사진처럼 약간 흐리고 대비가 균일하지 않은 종이를 만든다.
    page = ImageEnhance.Contrast(page).enhance(0.92)
    page = ImageEnhance.Color(page).enhance(0.78)
    page = page.filter(ImageFilter.GaussianBlur(radius=0.35))
    angle = rng.choice((-0.9, -0.6, 0.5, 0.8))
    page = page.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(224, 225, 222))

    border = 34
    canvas = Image.new("RGB", (page.width + border * 2, page.height + border * 2), (205, 207, 204))
    shadow = Image.new("RGB", page.size, (183, 184, 181)).filter(ImageFilter.GaussianBlur(7))
    canvas.paste(shadow, (border + 7, border + 9))
    canvas.paste(page, (border, border))

    # 매우 약한 센서 노이즈. 글자 자체를 훼손하지 않아 OCR 기준 샘플로 쓸 수 있다.
    pixels = canvas.load()
    for _ in range(canvas.width * canvas.height // 110):
        x = rng.randrange(canvas.width)
        y = rng.randrange(canvas.height)
        r, g, b = pixels[x, y]
        delta = rng.choice((-5, -3, 3, 5))
        pixels[x, y] = tuple(max(0, min(255, value + delta)) for value in (r, g, b))

    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, "JPEG", quality=84, optimize=True, progressive=True, dpi=(150, 150))


def main() -> int:
    args = _args()
    if not args.pdftoppm:
        raise SystemExit("pdftoppm을 찾지 못했습니다. --pdftoppm 경로를 지정하세요.")

    with TemporaryDirectory(prefix="proofbridge-scan-render-") as temporary:
        scratch = Path(temporary)
        for index, pdf_name in enumerate(PDF_NAMES, start=1):
            pdf_path = HERE / pdf_name
            rendered_prefix = scratch / pdf_path.stem
            subprocess.run(
                [args.pdftoppm, "-png", "-singlefile", "-r", "150", str(pdf_path), str(rendered_prefix)],
                check=True,
                capture_output=True,
            )
            target = OUT / f"{pdf_path.stem}_스캔.jpg"
            _camera_effect(rendered_prefix.with_suffix(".png"), target, seed=260829 + index)
            print(f"  {target.relative_to(HERE)}  ({target.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
