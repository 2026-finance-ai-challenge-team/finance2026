"""분류 결과를 사람이 읽는 한 장짜리 요약과 제출 묶음으로 만든다.

두 가지를 한다.

1. **리포트** — 파일을 열어보지 않아도 무슨 문서인지, 언제까지 쓸 수 있는지,
   무엇이 더 필요한지 한 화면에서 알 수 있게 한다.
2. **패킹** — 제각각인 파일명을 규칙에 맞게 바꾼 복사본을 만든다.
   **원본은 절대 수정하지 않는다.** 원본 그대로 한 벌, 이름만 바꾼 복사본 한 벌이다.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

# Windows·macOS에서 파일명에 못 쓰는 문자와 제어문자
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SPACES = re.compile(r"\s+")

STATUS_MARK = {"관련": "필요함", "이번 업무에는 불필요": "이번엔 불필요", "판단 불가": "확인 필요"}


def safe_component(text: str, *, limit: int = 40) -> str:
    """파일명 한 조각을 안전하게 만든다. 한글은 그대로 두고 금지문자만 없앤다."""
    cleaned = _SPACES.sub("", _FORBIDDEN.sub("", text or "")).strip("._")
    return cleaned[:limit] or "미상"


def submission_name(doc: dict[str, Any], index: int) -> str:
    """`발급일_문서종류_연번.확장자` 형태로 정규화한다.

    분류가 안 된 파일은 원본 이름을 살리되 앞에 `확인필요`를 붙여 눈에 띄게 한다.
    """
    suffix = Path(doc["source_name"]).suffix.lower() or ".bin"
    label = doc["classification"].get("label_ko")
    issued = (doc.get("fields") or {}).get("issued_at")

    if not label:
        stem = safe_component(Path(doc["source_name"]).stem)
        return f"확인필요_{stem}_{index:02d}{suffix}"

    return f"{safe_component(issued or '발급일미상')}_{safe_component(label)}_{index:02d}{suffix}"


def _label_of(doc_type: str, signatures: list[dict[str, Any]]) -> str:
    for signature in signatures:
        if signature["doc_type"] == doc_type:
            return signature.get("label_ko") or doc_type
    return doc_type


def _validity_cell(doc: dict[str, Any]) -> str:
    validity = doc.get("validity") or {}
    if validity.get("expires_at"):
        left = validity.get("days_left")
        if left is not None and left < 0:
            return f"**{validity['expires_at']} 만료됨**"
        return f"{validity['expires_at']}까지 ({validity['note']})"
    return validity.get("note") or "-"


def build_report(result: dict[str, Any], signatures: list[dict[str, Any]]) -> str:
    """한 장짜리 마크다운 요약을 만든다."""
    documents = result["documents"]
    lines = [
        "# 제출 준비 요약",
        "",
        f"- 업무: **{result.get('task_label', result['task_id'])}**",
        f"- 점검일: {result['checked_at']}",
        f"- 검토한 파일: {len(documents)}개 · OCR 호출: {result.get('ocr_calls_total', 0)}회",
        "",
    ]

    usable = [d for d in documents if d["classification"]["doc_type"]]
    unknown = [d for d in documents if not d["classification"]["doc_type"]]

    lines += ["## 1. 지금 가지고 있는 문서", ""]
    if usable:
        lines += [
            "| 제출용 이름 | 문서 종류 | 발급처 | 발급일 | 유효기간 | 이번 업무 | 원래 파일명 |",
            "|---|---|---|---|---|---|---|",
        ]
        for i, doc in enumerate(usable, start=1):
            fields = doc.get("fields") or {}
            lines.append(
                f"| `{submission_name(doc, i)}` "
                f"| {doc['classification']['label_ko']} "
                f"| {fields.get('issuer') or '-'} "
                f"| {fields.get('issued_at') or '-'} "
                f"| {_validity_cell(doc)} "
                f"| {STATUS_MARK.get(doc['relevance']['status'], doc['relevance']['status'])} "
                f"| {doc['source_name']} |"
            )
    else:
        lines.append("분류된 문서가 없습니다.")
    lines.append("")

    lines += ["## 2. 더 준비해야 하는 문서", ""]
    missing = result.get("missing") or {}
    bucket_label = {"required": "필수", "conditional": "조건부", "alternatives": "대체 가능"}
    rows = [
        f"- **{_label_of(t, signatures)}** ({bucket_label[bucket]}) — 발급처와 발급 방법은 확인 필요"
        for bucket in ("required", "conditional", "alternatives")
        for t in missing.get(bucket, [])
    ]
    expired = [
        d for d in usable if (d.get("validity") or {}).get("days_left") is not None
        and d["validity"]["days_left"] < 0
    ]
    for doc in expired:
        rows.append(
            f"- **{doc['classification']['label_ko']}** — 가지고 있지만 "
            f"{doc['validity']['expires_at']}에 기한이 지났습니다. 다시 발급받아야 합니다."
        )
    lines += rows or ["추가로 발급받을 문서가 없습니다."]
    lines.append("")

    if unknown:
        lines += ["## 3. 무슨 문서인지 확인이 필요한 파일", ""]
        for doc in unknown:
            reason = doc.get("confirm_reason") or "일치하는 서식을 찾지 못했습니다."
            lines.append(f"- `{doc['source_name']}` — {reason}")
        lines.append("")

    lines += [
        "---",
        "",
        "이 요약은 **공개된 기준으로 미리 점검한 결과**이며 승인을 보장하지 않습니다.",
    ]
    if not result.get("task_verified", False):
        lines.append("")
        lines.append(
            "> **주의**: 이번 업무의 제출 요건은 아직 공식 출처로 검증되지 않은 임시값입니다. "
            "이 결과만으로 준비가 끝났다고 판단하지 마세요."
        )
    return "\n".join(lines) + "\n"


def build_checklist(result: dict[str, Any], signatures: list[dict[str, Any]]) -> str:
    lines = ["# 제출 체크리스트", ""]
    for i, doc in enumerate([d for d in result["documents"] if d["classification"]["doc_type"]], 1):
        if doc["relevance"]["status"] != "관련":
            continue
        lines.append(f"- [ ] {submission_name(doc, i)} — {doc['classification']['label_ko']}")
    missing = result.get("missing") or {}
    for bucket in ("required", "conditional"):
        for doc_type in missing.get(bucket, []):
            lines.append(f"- [ ] (발급 필요) {_label_of(doc_type, signatures)}")
    if len(lines) == 2:
        lines.append("체크할 항목이 없습니다.")
    return "\n".join(lines) + "\n"


def pack(
    result: dict[str, Any],
    paths: list[Path],
    out_dir: Path,
    signatures: list[dict[str, Any]],
    *,
    make_zip: bool = True,
) -> dict[str, Any]:
    """제출 묶음을 만든다. 원본 한 벌 + 이름만 바꾼 복사본 한 벌 + 요약 + 체크리스트."""
    out_dir = Path(out_dir)
    originals = out_dir / "원본"
    renamed = out_dir / "제출용"
    for directory in (originals, renamed):
        directory.mkdir(parents=True, exist_ok=True)

    by_name = {p.name: p for p in map(Path, paths)}
    mapping = []
    for i, doc in enumerate(result["documents"], start=1):
        source = by_name.get(doc["source_name"])
        if not source or not source.is_file():
            continue
        # 원본은 손대지 않는다. 복사만 한다.
        shutil.copy2(source, originals / source.name)
        target = submission_name(doc, i)
        shutil.copy2(source, renamed / target)
        mapping.append({"원래 이름": source.name, "제출용 이름": target})

    (out_dir / "index.md").write_text(build_report(result, signatures), encoding="utf-8")
    (out_dir / "checklist.md").write_text(build_checklist(result, signatures), encoding="utf-8")

    archive = None
    if make_zip:
        archive = out_dir.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in sorted(out_dir.rglob("*")):
                if item.is_file():
                    zf.write(item, item.relative_to(out_dir))

    return {"out_dir": out_dir, "zip": archive, "mapping": mapping}
