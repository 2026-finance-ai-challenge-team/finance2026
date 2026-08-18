"""문서 분류 모듈 실행 진입점.

    python -m modules.doc_classify.cli <파일 또는 폴더...> --task <업무ID>
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

from .classify import TASK_DIR, classify_files, load_signatures

SUPPORTED_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}

STATUS_MARK = {"관련": "O", "이번 업무에는 불필요": "-", "판단 불가": "?"}


def width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def pad(text: str, target: int) -> str:
    return text + " " * max(0, target - width(text))


def collect(inputs: list[str]) -> list[Path]:
    paths: list[Path] = []
    for item in inputs:
        path = Path(item).expanduser()
        if path.is_dir():
            paths += sorted(p for p in path.iterdir() if p.suffix.lower() in SUPPORTED_SUFFIXES)
        elif path.is_file():
            paths.append(path)
        else:
            print(f"[건너뜀] 파일을 찾을 수 없습니다: {item}", file=sys.stderr)
    return paths


def describe_evidence(evidence: list[dict]) -> str:
    parts = []
    for item in evidence:
        if item["kind"] == "anchors":
            parts.append(f"앵커 {item['matched']}/{item['total']}")
        else:
            shown = item.get("pattern") or item.get("value")
            parts.append(f"{item['kind']}={shown}")
    return " · ".join(parts)


def main(argv: list[str] | None = None) -> int:
    # Windows 콘솔 기본 인코딩(cp949)은 한글 일부와 기호를 못 찍고 죽는다.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    tasks = sorted(p.stem for p in TASK_DIR.glob("*.json"))
    parser = argparse.ArgumentParser(
        description="올린 문서가 무엇인지 분류하고 선택한 업무와의 관련성을 표시한다."
    )
    parser.add_argument("inputs", nargs="+", help="파일 또는 폴더 경로")
    parser.add_argument(
        "--task",
        default=tasks[0] if tasks else None,
        help=f"업무 ID (가능: {', '.join(tasks)})",
    )
    parser.add_argument("--no-ocr", action="store_true", help="OCR을 호출하지 않는다 (API 사용량 0)")
    parser.add_argument("--json", metavar="PATH", help="결과 JSON을 파일로 저장")
    parser.add_argument("--quiet", action="store_true", help="헤더 없이 결과만 출력")
    args = parser.parse_args(argv)

    paths = collect(args.inputs)
    if not paths:
        print("처리할 파일이 없습니다.", file=sys.stderr)
        return 1

    signatures = load_signatures()
    unverified = sum(1 for s in signatures if not s.get("verified"))
    if not args.quiet:
        print(f"업무      : {args.task}")
        print(f"시그니처  : {len(signatures)}종 (미검증 {unverified}종)")
        print(f"대상 파일 : {len(paths)}개" + ("  [OCR 끔]" if args.no_ocr else ""))
        print()

    result = classify_files(paths, args.task, use_ocr=not args.no_ocr, signatures=signatures)

    name_width = max(width(d["source_name"]) for d in result["documents"])
    for doc in result["documents"]:
        cls = doc["classification"]
        label = cls["label_ko"] or "(분류 실패)"
        status = doc["relevance"]["status"]
        methods = "+".join(sorted({p["method"] for p in doc["text_source"]}))
        chars = sum(p["chars"] for p in doc["text_source"])

        print(f"[{STATUS_MARK.get(status, ' ')}] {pad(doc['source_name'], name_width)}  {status}")
        print(f"     {doc['media']['kind']} {doc['media']['pages']}쪽 · 텍스트 {chars}자 ({methods})")
        if doc.get("visual_title"):
            print(f"     제목(글자 크기 기준): {doc['visual_title']}")
        print(f"     분류: {label}  신뢰도 {cls['confidence']}")
        if cls["evidence"]:
            print(f"     근거: {describe_evidence(cls['evidence'])}")
        if doc["fields"]:
            print(f"     필드: {json.dumps(doc['fields'], ensure_ascii=False)}")
        if doc["needs_user_confirm"]:
            print(f"     ! 사용자 확인 필요 — {doc['confirm_reason']}")
        if cls.get("unverified_signature"):
            print("     ! 미검증 시그니처로 분류됨 (찬형 DB 연동 전 임시값)")
        for note in doc["notes"]:
            print(f"     ! {note}")
        print()

    counts: dict[str, int] = {}
    for doc in result["documents"]:
        status = doc["relevance"]["status"]
        counts[status] = counts.get(status, 0) + 1
    print("요약: " + " · ".join(f"{k} {v}건" for k, v in counts.items()))
    if not result["task_verified"]:
        print("주의: 업무 요건이 미검증 임시값입니다. 이 결과로 준비 완료를 판단하면 안 됩니다.")

    if args.json:
        Path(args.json).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nJSON 저장: {args.json}")
        print("! 결과에 원문 텍스트는 없지만 파일명은 들어갑니다. 공유 전 확인하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
