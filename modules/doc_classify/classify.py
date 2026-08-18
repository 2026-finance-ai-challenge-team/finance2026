"""2~3, 5단계 · 신호 수집 → 시그니처 대조 → 업무 관련성.

원칙 두 가지 (`docs/DOC_CLASSIFY.md` §4, §6):
- **"모른다"와 "필요 없다"를 섞지 않는다.** 분류 실패는 `판단 불가`로 남긴다.
- **출력에 원문 텍스트를 담지 않는다.** 매칭한 패턴과 위치만 근거로 남긴다.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .extract import Extracted, apply_ocr, extract, needs_ocr

HERE = Path(__file__).resolve().parent
SIGNATURE_DIR = HERE / "signatures"
TASK_DIR = HERE / "tasks"

# 이 점수 미만이면 확정하지 않고 사용자에게 묻는다.
CONFIRM_THRESHOLD = 0.60
# 1등과 2등이 이 차이 안이면 헷갈린 것으로 보고 역시 묻는다. (등본/초본 같은 쌍)
AMBIGUOUS_GAP = 0.15
# 제목은 문서 상단에서만 인정한다. 본문 하단 안내문에 다른 서류 이름이 등장하는 일이
# 실제로 있다 — 정부24 발급 페이지 하단에서 '가족관계증명서'가 잡혀 오분류가 났었다.
# ponytail: 글자 수로 자르는 근사치. 좌표 기반 상단 영역이 정확하지만 OCR bbox가 필요하다.
TITLE_HEAD_CHARS = 500

_DATE = re.compile(r"(20\d{2})\s*[.\-년/]\s*(\d{1,2})\s*[.\-월/]\s*(\d{1,2})")


def load_signatures(directory: Path | None = None) -> list[dict[str, Any]]:
    directory = directory or SIGNATURE_DIR
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))]


def load_task(task_id: str, directory: Path | None = None) -> dict[str, Any]:
    directory = directory or TASK_DIR
    path = directory / f"{task_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"업무 정의가 없습니다: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _search(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        if re.search(pattern, text):
            return pattern
    return None


def _search_title(patterns: list[str], title_text: str) -> str | None:
    """제목은 공백을 지운 형태로도 대조한다.

    OCR은 자간이 넓은 큰 제목을 낱자로 쪼개 준다. 실측 예: '주 민 등 록 표 ( 초 본 )'.
    공백을 지우면 '주민등록표(초본)'이 되어 일반 패턴으로 잡힌다.
    """
    return _search(patterns, title_text) or _search(patterns, re.sub(r"\s+", "", title_text))


def score_signature(
    signature: dict[str, Any], text: str, title_text: str | None = None
) -> tuple[float, list[dict[str, Any]]]:
    """시그니처 하나와 문서를 대조해 (점수, 근거)를 낸다.

    `title_text`는 '크게 인쇄된 상단 글자'다(OCR 좌표로 뽑는다). 이게 있으면 제목 판정에
    그것만 쓴다. 본문 안내문에 다른 서류 이름이 나와도 제목으로 오인하지 않는다.

    negative_anchors가 하나라도 걸리면 즉시 0점이다. 등본/초본처럼 제목이 거의 같은
    쌍은 '없어야 할 단어'로만 갈린다.
    """
    evidence: list[dict[str, Any]] = []
    if title_text is None:
        title_text = text[:TITLE_HEAD_CHARS]

    for negative in signature.get("negative_anchors") or []:
        if re.search(negative, text):
            return 0.0, [{"kind": "negative_anchor", "value": negative}]

    score = 0.0

    patterns = signature.get("title_patterns") or []
    title = _search_title(patterns, title_text)
    if title:
        score += 0.60
        evidence.append({"kind": "title_match", "pattern": title})
    else:
        # 제목 영역 밖에서 나온 서류 이름은 제목이 아니라 언급일 뿐이다. 약한 신호로만 센다.
        mention = _search(patterns, text)
        if mention:
            score += 0.10
            evidence.append({"kind": "title_mention", "pattern": mention})

    issuers = [signature.get("issuer", "")] + list(signature.get("issuer_aliases") or [])
    issuer = _search([re.escape(i) for i in issuers if i], text)
    if issuer:
        score += 0.15
        evidence.append({"kind": "issuer_match", "pattern": issuer})

    anchors = signature.get("required_anchors") or []
    hit = [a for a in anchors if re.search(a, text)]
    if anchors:
        score += 0.20 * (len(hit) / len(anchors))
        evidence.append({"kind": "anchors", "matched": len(hit), "total": len(anchors)})

    label = signature.get("doc_number_label")
    if label and re.search(re.escape(label), text):
        score += 0.05
        evidence.append({"kind": "doc_number_label", "pattern": label})

    return min(score, 0.99), evidence


def _iso(match: re.Match[str]) -> str:
    y, m, d = match.groups()
    return f"{y}-{int(m):02d}-{int(d):02d}"


def _fields(signature: dict[str, Any], text: str) -> dict[str, Any]:
    """분류에 필요한 최소 필드만 뽑는다. 명의·주소·소득은 뽑지 않는다."""
    fields: dict[str, Any] = {}

    # 정식 명칭이 우선. 없으면 실제로 문서에 찍힌 별칭(정부24, KB 등)을 쓴다.
    for name in [signature.get("issuer", "")] + list(signature.get("issuer_aliases") or []):
        if name and name in text:
            fields["issuer"] = name
            break

    # 1순위: '발급일자' 같은 라벨 바로 뒤의 날짜. 이건 확실하다.
    for label in signature.get("issued_at_labels") or []:
        at = text.find(label)
        if at == -1:
            continue
        match = _DATE.search(text, at, at + 80)
        if match:
            fields["issued_at"] = _iso(match)
            fields["issued_at_confident"] = True
            break

    # 2순위: 라벨이 없으면 문서에서 가장 늦은 날짜를 발급일로 '추정'한다.
    # 실측: 주민등록등본은 발급일 라벨 없이 날짜만 인쇄된다. 생년월일이 같이 있는
    # 문서도 있는데 그건 보통 가장 이른 날짜라 '가장 늦은 날짜'가 비교적 안전하다.
    # 추정값으로는 '유효함'을 단정하지 않는다(expiry_of 참고).
    if "issued_at" not in fields:
        found = sorted(_iso(m) for m in _DATE.finditer(text))
        if found:
            fields["issued_at"] = found[-1]
            fields["issued_at_confident"] = False

    label = signature.get("doc_number_label")
    fields["doc_number_present"] = bool(label and label in text)
    return fields


def classify_one(extracted: Extracted, signatures: list[dict[str, Any]]) -> dict[str, Any]:
    text = extracted.full_text
    title_text = extracted.title_text
    scored = []
    for signature in signatures:
        score, evidence = score_signature(signature, text, title_text)
        if score > 0:
            scored.append((score, signature, evidence))
    scored.sort(key=lambda row: row[0], reverse=True)

    if not scored or scored[0][0] < CONFIRM_THRESHOLD:
        return {
            "doc_type": None,
            "label_ko": None,
            "confidence": round(scored[0][0], 2) if scored else 0.0,
            "decided_by": None,
            "evidence": scored[0][2] if scored else [],
            "alternatives": [],
            "fields": {},
            "needs_user_confirm": True,
            "confirm_reason": "일치하는 문서 서식을 찾지 못했습니다.",
        }

    best_score, best, evidence = scored[0]
    runner_up = scored[1] if len(scored) > 1 else None
    ambiguous = bool(runner_up and best_score - runner_up[0] < AMBIGUOUS_GAP)

    return {
        "doc_type": best["doc_type"],
        "label_ko": best.get("label_ko"),
        "confidence": round(best_score, 2),
        "decided_by": "anchor",
        "evidence": evidence,
        "alternatives": [
            {"doc_type": s[1]["doc_type"], "confidence": round(s[0], 2)} for s in scored[1:3]
        ],
        "fields": _fields(best, text),
        "needs_user_confirm": ambiguous,
        "confirm_reason": (
            f"{runner_up[1]['doc_type']}와 점수가 비슷합니다." if ambiguous else None
        ),
        "unverified_signature": not best.get("verified", False),
    }


def judge_relevance(doc_type: str | None, task: dict[str, Any]) -> dict[str, Any]:
    """분류 실패(`판단 불가`)와 업무 무관(`이번 업무에는 불필요`)을 절대 합치지 않는다."""
    if doc_type is None:
        return {"status": "판단 불가", "matched_rule": None}

    for bucket in ("required", "conditional", "alternatives"):
        if doc_type in (task.get(bucket) or []):
            return {"status": "관련", "matched_rule": bucket}
    return {"status": "이번 업무에는 불필요", "matched_rule": None}


def is_settled(classification: dict[str, Any]) -> bool:
    """확정됐나. 확정이면 OCR을 부르지 않는다."""
    return classification["doc_type"] is not None and not classification["needs_user_confirm"]


def expiry_of(
    classification: dict[str, Any], signatures: list[dict[str, Any]], today: date | None = None
) -> dict[str, Any]:
    """발급일 + 유효기간으로 만료일을 계산한다.

    상태 이름을 최종 확정하는 건 규칙 엔진의 몫이다. 여기서는 날짜 계산 결과만 넘긴다.
    """
    today = today or date.today()
    doc_type = classification.get("doc_type")
    issued = (classification.get("fields") or {}).get("issued_at")
    signature = next((s for s in signatures if s["doc_type"] == doc_type), None)
    days = signature.get("validity_days") if signature else None

    if not doc_type or days is None:
        return {"expires_at": None, "days_left": None, "note": "유효기간 규정 없음"}
    if not issued:
        return {"expires_at": None, "days_left": None, "note": "발급일을 읽지 못함"}

    try:
        expires = date.fromisoformat(issued) + timedelta(days=int(days))
    except ValueError:
        return {"expires_at": None, "days_left": None, "note": "발급일 형식 오류"}

    left = (expires - today).days
    confident = bool((classification.get("fields") or {}).get("issued_at_confident"))

    if left < 0:
        # 만료 쪽으로 틀리는 건 안전하다. 추정이어도 사용자에게 알린다.
        note = "기한 만료" if confident else "기한이 지났을 수 있음 — 발급일 확인 필요"
    else:
        # 유효 쪽으로 틀리면 거짓 준비 완료가 된다. 추정값으로는 단정하지 않는다.
        note = f"{left}일 남음" if confident else f"{left}일 남음(추정) — 발급일 확인 필요"

    return {
        "expires_at": expires.isoformat(),
        "days_left": left,
        "estimated": not confident,
        "note": note,
    }


def classify_files(
    paths: list[str | Path],
    task_id: str,
    *,
    use_ocr: bool = True,
    signatures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """모듈의 공개 API. 파일 목록과 업무 ID를 받아 분류 결과 JSON을 만든다.

    OCR은 **내장 텍스트만으로 확정되지 않은 파일에만** 호출한다(파일당 최대 1회).
    """
    signatures = signatures if signatures is not None else load_signatures()
    task = load_task(task_id)

    documents = []
    for i, path in enumerate(paths, start=1):
        # 1차: 내장 텍스트만. API 호출 0회.
        extracted = extract(path, use_ocr=False)
        classification = classify_one(extracted, signatures)

        # 2차: 1차에서 확정 못 했고 아직 읽을 페이지가 남았을 때만 OCR.
        if use_ocr and not is_settled(classification) and needs_ocr(extracted):
            apply_ocr(extracted)
            classification = classify_one(extracted, signatures)
        elif not use_ocr and needs_ocr(extracted):
            extracted.notes.append("텍스트 없는 페이지가 남았지만 OCR이 꺼져 있습니다(--no-ocr).")

        documents.append(
            {
                "file_id": f"f{i:02d}",
                "source_name": Path(path).name,
                "media": {
                    "kind": extracted.kind,
                    "pages": len(extracted.pages),
                    "detected_by": "magic",
                },
                "text_source": [
                    {"page": p.index, "method": p.method, "chars": p.chars}
                    for p in extracted.pages
                ],
                # 글자 크기로 잡은 제목. 문서 종류를 나타내는 문구라 개인정보가 아니다.
                "visual_title": " / ".join(p.title for p in extracted.pages if p.title),
                "classification": {
                    k: v for k, v in classification.items() if k not in {"fields", "needs_user_confirm", "confirm_reason"}
                },
                "fields": classification["fields"],
                "validity": expiry_of(classification, signatures),
                "relevance": judge_relevance(classification["doc_type"], task),
                "needs_user_confirm": classification["needs_user_confirm"],
                "confirm_reason": classification["confirm_reason"],
                "ocr_calls": extracted.ocr_calls,
                "notes": extracted.notes,
            }
        )

    found = {d["classification"]["doc_type"] for d in documents if d["classification"]["doc_type"]}
    missing = {
        bucket: [t for t in (task.get(bucket) or []) if t not in found]
        for bucket in ("required", "conditional", "alternatives")
    }

    return {
        "task_id": task_id,
        "task_label": task.get("label_ko", task_id),
        "task_verified": task.get("verified", False),
        "checked_at": date.today().isoformat(),
        "ocr_calls_total": sum(d["ocr_calls"] for d in documents),
        "missing": missing,
        "documents": documents,
    }
