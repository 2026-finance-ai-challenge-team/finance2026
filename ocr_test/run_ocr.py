#!/usr/bin/env python3
"""CLOVA OCR General API 호출 데모.

사용 예 (Windows PowerShell):
    python run_ocr.py "E:\\OneDrive\\바탕 화면\\뉴연뉴의 개인문서\\국민은행 통장사본.jpg"
    python run_ocr.py 통장사본.jpg --save --mask
    python run_ocr.py --from-json out/통장사본.20260817-101500.json   # API 호출 없이 재파싱
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import clova_ocr
from bankbook import extract_bankbook_fields
from clova_ocr import ClovaOcrError, OcrConfig

HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = HERE / "out"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="네이버 CLOVA OCR General API로 문서 텍스트를 추출한다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("image", nargs="?", help="이미지/PDF 경로 (jpg, jpeg, png, pdf, tiff)")
    parser.add_argument(
        "--from-json",
        metavar="PATH",
        help="저장해 둔 응답 JSON을 그대로 파싱한다(API 호출 없음).",
    )
    parser.add_argument("--lang", default="ko", help="인식 언어 (기본: ko)")
    parser.add_argument("--table", action="store_true", help="표 인식(enableTableDetection) 활성화")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP 타임아웃 초 (기본: 30)")
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.8,
        help="이 값보다 낮은 신뢰도 필드를 따로 보여준다 (기본: 0.8)",
    )
    parser.add_argument("--save", action="store_true", help=f"응답 JSON과 텍스트를 {DEFAULT_OUT_DIR}에 저장")
    parser.add_argument(
        "--mask",
        action="store_true",
        help="화면·저장 텍스트에서 계좌번호·주민번호로 보이는 숫자를 가린다.",
    )
    parser.add_argument("--raw", action="store_true", help="응답 JSON 전체를 그대로 출력")
    args = parser.parse_args(argv)

    if not args.image and not args.from_json:
        parser.error("image 경로 또는 --from-json 중 하나는 필요합니다.")
    return args


def display_width(text: str) -> int:
    """한글·전각 문자를 2칸으로 계산해 터미널 열을 맞춘다."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def pad(text: str, width: int) -> str:
    return text + " " * max(0, width - display_width(text))


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * max(display_width(title), 40))


def main(argv: list[str] | None = None) -> int:
    # Windows 콘솔 기본 인코딩(cp949)은 신고서의 ☑ 같은 문자를 못 찍고 죽는다.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)

    # .env는 이 스크립트 폴더 → 저장소 루트 순으로 찾는다.
    for candidate in (HERE / ".env", HERE.parent / ".env"):
        clova_ocr.load_dotenv(candidate)

    if args.from_json:
        source = Path(args.from_json).expanduser()
        try:
            response = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"[실패] 응답 JSON을 읽을 수 없습니다: {exc}", file=sys.stderr)
            return 1
        elapsed = None
        label = str(source)
    else:
        try:
            # 파일 문제를 환경변수 문제보다 먼저 알려준다.
            clova_ocr.image_format_of(Path(args.image).expanduser())
            if not Path(args.image).expanduser().is_file():
                raise ClovaOcrError(f"파일을 찾을 수 없습니다: {args.image}")
            config = OcrConfig.from_env(timeout=args.timeout)
            print(f"요청 대상: {config.invoke_url}")
            print(f"입력 파일: {args.image}")
            response, elapsed = clova_ocr.call_general_ocr(
                args.image,
                config,
                lang=args.lang,
                enable_table_detection=args.table,
            )
        except ClovaOcrError as exc:
            print(f"[실패] {exc}", file=sys.stderr)
            return 1
        label = str(args.image)

    fields = clova_ocr.iter_fields(response)
    lines = clova_ocr.fields_to_lines(fields)
    display_lines = clova_ocr.mask_lines(lines) if args.mask else list(lines)

    section("인식 결과")
    print(f"requestId : {response.get('requestId')}")
    print(f"필드 수    : {len(fields)}개 / 줄 수: {len(lines)}줄")
    if elapsed is not None:
        print(f"소요 시간  : {elapsed:.2f}초")

    section("줄 단위 텍스트")
    if display_lines:
        for index, line in enumerate(display_lines, start=1):
            print(f"{index:3d} | {line}")
    else:
        print("(추출된 텍스트가 없습니다)")

    low = clova_ocr.low_confidence_fields(response, threshold=args.min_confidence)
    section(f"낮은 신뢰도 필드 (< {args.min_confidence})")
    if low:
        for text, confidence in low:
            shown = clova_ocr.mask_pii(text) if args.mask else text
            print(f"  {confidence:.3f}  {shown}")
        print("\n→ 이 필드들은 사용자에게 짧은 확인을 요청할 후보입니다.")
    else:
        print("없음")

    extracted = extract_bankbook_fields(lines)
    section("통장사본 추정 필드 (정규식 휴리스틱 · 판정 아님)")
    rows = extracted.as_rows()
    if rows:
        width = max(display_width(label) for label, _ in rows)
        for field_label, value in rows:
            shown = clova_ocr.mask_pii(value) if args.mask else value
            print(f"  {pad(field_label, width)} : {shown}")
    else:
        print("  추정 가능한 필드가 없습니다.")
    for note in extracted.notes:
        print(f"  ! {note}")

    if args.raw:
        section("응답 JSON")
        print(json.dumps(response, ensure_ascii=False, indent=2))

    if args.save:
        DEFAULT_OUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        stem = Path(label).stem or "response"
        json_path = DEFAULT_OUT_DIR / f"{stem}.{stamp}.json"
        text_path = DEFAULT_OUT_DIR / f"{stem}.{stamp}.txt"
        json_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
        text_path.write_text("\n".join(display_lines) + "\n", encoding="utf-8")
        section("저장")
        print(f"  {json_path}")
        print(f"  {text_path}")
        print("  ! out/ 은 .gitignore 대상입니다. 실제 개인정보가 들어 있으니 커밋·공유하지 마세요.")
        if not args.mask:
            print("  ! --mask 없이 저장했으므로 계좌번호가 원문 그대로 남습니다.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
