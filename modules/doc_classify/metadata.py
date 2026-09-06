"""CLOVA OCR 결과에서 문서 식별용 최소 메타데이터를 뽑는다.

원문은 반환하지 않는다. 값마다 근거 block id를 남기고, 라벨 없는 날짜는
확정하지 않아 생년월일을 발급일로 오인하는 일을 막는다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .classify import AMBIGUOUS_GAP, CONFIRM_THRESHOLD, load_signatures, score_signature
from .extract import visual_title

SCHEMA_VERSION = "1.0"

ISSUE_LABELS = (
    "발급일자",
    "발급일",
    "발행일자",
    "발행일",
    "교부일자",
    "교부일",
    "증명일자",
    "증명일",
    "작성일자",
    "작성일",
)
EXPIRY_LABELS = (
    "유효기간",
    "유효기한",
    "만료일자",
    "만료일",
    "효력종료일",
    "사용기한",
)
NOISE_DATE_LABELS = (
    "생년월일",
    "출생일",
    "입사일",
    "퇴사일",
    "재직기간",
    "근무기간",
    "계약기간",
    "사용기간",
    "과세기간",
    "귀속연도",
    "개업연월일",
    "사업개시일",
    "기준일",
    "조회일",
    "신고일",
    "접수일",
    "납부기한",
    "납부일",
    "자격취득일",
    "자격상실일",
)
_CLOSING = re.compile(r"위와\s*같이|이를\s*증명|사실을\s*확인|증명합니다|발급합니다")
_AUTHORITY = re.compile(r"세무서장|구청장|시장|군수|법원|등기소|국세청|정부24")
_NOT_PERSON_NAMES = {
    "주소",
    "관계",
    "성명",
    "이름",
    "본인",
    "대표자",
    "생년월일",
    "주민등록번호",
    "발급일",
    "발급일자",
    "입사일",
    "직위",
    "부서",
    "가입자",
    "대리인",
    "위임인",
    "수임인",
    "과의",
    "과세",
}
_FIELD_WORDS = (
    "사업자등록번호",
    "주민등록번호",
    "법인등록번호",
    "업태",
    "종목",
    "주소",
    "사업장소재지",
    "개업일",
    "사업자등록일",
    "생년월일",
    "연락처",
    "본인",
    "대리인",
    "위임인",
    "수임인",
)

_DATE_PATTERNS = (
    re.compile(
        r"(?<!\d)((?:19|20)\d{2})\s*(?:[.\-/]|년)\s*(\d{1,2})"
        r"\s*(?:[.\-/]|월)\s*(\d{1,2})(?:\s*일)?(?!\d)"
    ),
    re.compile(r"(?<!\d)((?:19|20)\d{2})(\d{2})(\d{2})(?!\d)"),
)

# 구체적인 명의 라벨을 일반적인 '성명'보다 우선한다.
_NAME_LABELS = (
    ("가입자 성명", "PERSON", 100),
    ("납세자 성명", "PERSON", 100),
    ("신청인 성명", "PERSON", 100),
    ("세대주 성명", "PERSON", 95),
    ("예금주명", "PERSON", 100),
    ("예금주", "PERSON", 100),
    ("계약자명", "PERSON", 100),
    ("계약자", "PERSON", 100),
    ("고객명", "PERSON", 100),
    ("본인", "PERSON", 100),
    ("대표자 성명", "REPRESENTATIVE", 90),
    ("대표자", "REPRESENTATIVE", 90),
    ("성명(업체명)", "CORPORATION", 100),
    ("상호(법인명)", "CORPORATION", 100),
    ("법인명(상호)", "CORPORATION", 100),
    ("법인명(단체명)", "CORPORATION", 100),
    ("법인영(단체명)", "CORPORATION", 100),
    ("법인명", "CORPORATION", 95),
    ("회사명", "CORPORATION", 95),
    ("업체명", "CORPORATION", 95),
    ("상호명", "CORPORATION", 95),
    ("상호", "CORPORATION", 95),
    ("성명", "PERSON", 70),
    ("이름", "PERSON", 65),
)


@dataclass(frozen=True)
class Line:
    page: int
    text: str
    block_ids: tuple[str, ...]
    confidence: float
    top: float
    bottom: float


@dataclass(frozen=True)
class DateHit:
    value: str
    start: int
    end: int


def _bbox(field: dict[str, Any]) -> tuple[float, float, float, float]:
    vertices = ((field.get("boundingPoly") or {}).get("vertices")) or []
    xs = [float(vertex.get("x", 0.0)) for vertex in vertices]
    ys = [float(vertex.get("y", 0.0)) for vertex in vertices]
    return (min(xs), min(ys), max(xs), max(ys)) if xs and ys else (0.0, 0.0, 0.0, 0.0)


def _make_line(page: int, fields: list[tuple[str, dict[str, Any]]]) -> Line:
    fields = sorted(fields, key=lambda item: _bbox(item[1])[0])
    text = " ".join((field.get("inferText") or "").strip() for _, field in fields).strip()
    boxes = [_bbox(field) for _, field in fields]
    confidences = [float(field.get("inferConfidence", 1.0)) for _, field in fields]
    return Line(
        page=page,
        text=text,
        block_ids=tuple(block_id for block_id, _ in fields),
        confidence=sum(confidences) / len(confidences),
        top=min(box[1] for box in boxes),
        bottom=max(box[3] for box in boxes),
    )


def _page_lines(page: int, fields: list[dict[str, Any]]) -> list[Line]:
    tagged = [(f"p{page}:f{i}", field) for i, field in enumerate(fields, start=1)]
    if not tagged:
        return []

    rows: list[list[tuple[str, dict[str, Any]]]] = []
    if any("lineBreak" in field for _, field in tagged):
        current: list[tuple[str, dict[str, Any]]] = []
        for item in tagged:
            current.append(item)
            if item[1].get("lineBreak"):
                rows.append(current)
                current = []
        if current:
            rows.append(current)
    else:
        heights = [box[3] - box[1] for _, field in tagged if (box := _bbox(field))[3] > box[1]]
        tolerance = (sum(heights) / len(heights) * 0.6) if heights else 10.0
        for item in sorted(tagged, key=lambda pair: sum(_bbox(pair[1])[1::2]) / 2):
            center = sum(_bbox(item[1])[1::2]) / 2
            previous = sum(_bbox(rows[-1][-1][1])[1::2]) / 2 if rows else None
            if previous is not None and abs(center - previous) <= tolerance:
                rows[-1].append(item)
            else:
                rows.append([item])
    return [_make_line(page, row) for row in rows if any((field.get("inferText") or "").strip() for _, field in row)]


def _all_lines(response: dict[str, Any]) -> list[Line]:
    return [
        line
        for page, image in enumerate(response.get("images") or [], start=1)
        for line in _page_lines(page, image.get("fields") or [])
    ]


def _block_map(response: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        f"p{page}:f{index}": field
        for page, image in enumerate(response.get("images") or [], start=1)
        for index, field in enumerate(image.get("fields") or [], start=1)
    }


def _dates(text: str) -> list[DateHit]:
    found: dict[tuple[int, int], DateHit] = {}
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            try:
                value = date(*(int(part) for part in match.groups())).isoformat()
            except ValueError:
                continue
            found[(match.start(), match.end())] = DateHit(value, match.start(), match.end())
    return sorted(found.values(), key=lambda hit: hit.start)


def _label_pattern(label: str) -> re.Pattern[str]:
    return re.compile(r"\s*".join(re.escape(character) for character in label if not character.isspace()))


def _has_label(text: str, labels: tuple[str, ...]) -> bool:
    return any(_label_pattern(label).search(text) for label in labels)


def _field(value: str | None, status: str, confidence: float | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "value": value,
        "status": status,
        "confidence": round(confidence, 2) if confidence is not None else None,
        **extra,
    }


def _labeled_date(lines: list[Line], labels: tuple[str, ...], *, last: bool) -> dict[str, Any]:
    candidates: list[tuple[int, DateHit, Line, str]] = []
    for index, line in enumerate(lines):
        for priority, label in enumerate(labels):
            label_match = _label_pattern(label).search(line.text)
            if not label_match:
                continue
            suffix = line.text[label_match.end() :].lstrip()
            if suffix.startswith(("로부터", "현재", "기준", "이후", "전")):
                continue
            hits = _dates(line.text)
            after = [hit for hit in hits if hit.start >= label_match.end()]
            if after:
                hit = after[-1] if last else after[0]
                candidates.append((1000 - priority, hit, line, label))
                continue
            if index + 1 < len(lines) and lines[index + 1].page == line.page:
                next_hits = _dates(lines[index + 1].text)
                if next_hits:
                    hit = next_hits[-1] if last else next_hits[0]
                    candidates.append((900 - priority, hit, lines[index + 1], label))

    if not candidates:
        return _field(None, "NOT_FOUND", evidence_block_ids=[])
    candidates.sort(key=lambda item: item[0], reverse=True)
    best = candidates[0]
    ties = sorted({item[1].value for item in candidates if item[0] == best[0]})
    if len(ties) > 1:
        return _field(
            None,
            "AMBIGUOUS",
            candidates=ties,
            source_label=best[3],
            evidence_block_ids=list(best[2].block_ids),
        )
    return _field(
        best[1].value,
        "CONFIRMED",
        best[2].confidence,
        source_label=best[3],
        evidence_block_ids=list(best[2].block_ids),
    )


def _infer_issue_date(lines: list[Line], signature: dict[str, Any] | None) -> dict[str, Any]:
    issuers = [] if not signature else [signature.get("issuer", ""), *(signature.get("issuer_aliases") or [])]
    candidates: list[tuple[int, DateHit, Line]] = []
    page_bounds = {
        page: (min(line.top for line in lines if line.page == page), max(line.bottom for line in lines if line.page == page))
        for page in {line.page for line in lines}
    }
    for index, line in enumerate(lines):
        if _has_label(line.text, NOISE_DATE_LABELS) or _has_label(line.text, EXPIRY_LABELS):
            continue
        top, bottom = page_bounds[line.page]
        page_height = max(bottom - top, 1.0)
        relative_top = (line.top - top) / max(bottom - top, 1.0)
        center = (line.top + line.bottom) / 2
        page_lines = [item for item in lines if item.page == line.page]
        authority_gap = min(
            (abs((item.top + item.bottom) / 2 - center) for item in page_lines if _AUTHORITY.search(item.text)),
            default=page_height,
        )
        closing_gap = min(
            (abs((item.top + item.bottom) / 2 - center) for item in page_lines if _CLOSING.search(item.text)),
            default=page_height,
        )
        score = (
            (6 if relative_top <= 0.06 else 0)
            + (4 if relative_top >= 0.65 else 2 if relative_top >= 0.55 else 0)
            + (4 if authority_gap <= page_height * 0.05 else 0)
            + (2 if closing_gap <= page_height * 0.15 else 0)
        )
        if any(
            issuer
            and any(
                issuer in item.text
                and abs((item.top + item.bottom) / 2 - center) <= page_height * 0.05
                for item in page_lines
            )
            for issuer in issuers
        ):
            score += 2
        for hit in _dates(line.text):
            if score >= 4:
                candidates.append((score, hit, line))

    if not candidates:
        return _field(None, "NOT_FOUND", evidence_block_ids=[])
    candidates.sort(key=lambda item: (item[0], item[1].value), reverse=True)
    best_score = candidates[0][0]
    ties = sorted({item[1].value for item in candidates if item[0] == best_score})
    if len(ties) > 1:
        return _field(None, "AMBIGUOUS", candidates=ties, evidence_block_ids=list(candidates[0][2].block_ids))
    return _field(
        candidates[0][1].value,
        "INFERRED",
        min(candidates[0][2].confidence, 0.75),
        source_label=None,
        evidence_block_ids=list(candidates[0][2].block_ids),
    )


def _name_value(text: str, role: str) -> str | None:
    text = re.sub(r"^[\s:：|]+", "", text)
    text = re.sub(
        r"^(?:Name\s+of\s+(?:company|representative)|Resident/Corporation\s+representative)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"^\s*\(\s*(?:법인명|단체명|상호|업체명)\s*\)\s*", "", text)
    date_hit = _dates(text)
    if date_hit:
        text = text[: date_hit[0].start]
    text = re.split(
        r"\s(?:생년월일|주소|주민(?:법인)?등록번호|사업자등록번호|발급일|직위|부서|연락처)\s*[:：]?",
        text,
        maxsplit=1,
    )[0]
    text = text.strip(" \t:：|,;")
    if not text:
        return None
    if role == "PERSON":
        text = re.sub(r"^(?:가입자|본인|세대주|대표자)\s*", "", text)
        hangul = re.match(r"(?:[가-힣]\s*){2,12}(?![가-힣])", text)
        if hangul:
            value = re.sub(r"\s+", "", hangul.group()).strip()
            field_words = tuple(_compact(word) for word in _FIELD_WORDS)
            return None if value in _NOT_PERSON_NAMES or _compact(value).startswith(field_words) else value
        english = re.match(r"[A-Za-z][A-Za-z .'-]{1,49}", text)
        return re.sub(r"\s+", " ", english.group()).strip() if english else None
    value = re.sub(r"\s+", " ", text)[:60].strip()
    compact = re.sub(r"[^0-9A-Za-z가-힣]", "", value).casefold()
    field_words = tuple(_compact(word) for word in _FIELD_WORDS)
    rejected = (
        not compact
        or compact.startswith(("nameofcompany", *field_words))
        or any(word in value for word in ("인/서명", "자필기재", "직원작성란", "선택", "해당사항이 없습니다"))
    )
    return value if len(value) >= 2 and not value.isdigit() and not rejected else None


def _spatial_name(
    line: Line,
    match: re.Match[str],
    role: str,
    blocks: dict[str, dict[str, Any]],
) -> tuple[str, float, tuple[str, ...]] | None:
    pieces = []
    cursor = 0
    for block_id in line.block_ids:
        text = (blocks[block_id].get("inferText") or "").strip()
        start = cursor + (1 if pieces else 0)
        end = start + len(text)
        pieces.append((block_id, start, end))
        cursor = end
    anchor_ids = [block_id for block_id, start, end in pieces if start < match.end() and end > match.start()]
    if not anchor_ids:
        return None
    anchor_boxes = [_bbox(blocks[block_id]) for block_id in anchor_ids]
    left = min(box[0] for box in anchor_boxes)
    top = min(box[1] for box in anchor_boxes)
    right = max(box[2] for box in anchor_boxes)
    bottom = max(box[3] for box in anchor_boxes)
    height = max(bottom - top, 10.0)
    options = []
    for block_id, field in blocks.items():
        if not block_id.startswith(f"p{line.page}:") or block_id in anchor_ids:
            continue
        box = _bbox(field)
        same_row = min(bottom, box[3]) - max(top, box[1]) >= min(height, max(box[3] - box[1], 1.0)) * 0.4
        below = 0 <= box[1] - bottom <= height * 4 and left - height <= box[0] <= right + height * 8
        if not ((same_row and box[0] >= right - height) or (role == "PERSON" and below)):
            continue
        value = _name_value(field.get("inferText") or "", role)
        if not value:
            continue
        distance = (0 if same_row else 10000) + abs(box[1] - top) * 10 + abs(box[0] - right)
        options.append((distance, value, float(field.get("inferConfidence", 1.0)), block_id))
    if not options:
        return None
    _, value, confidence, value_id = min(options)
    return value, confidence, tuple([*anchor_ids, value_id])


def _owner(
    lines: list[Line],
    blocks: dict[str, dict[str, Any]],
    preferred_role: str | None,
) -> dict[str, Any]:
    candidates: dict[str, tuple[int, str, float, tuple[str, ...], str]] = {}
    for line in lines:
        for label, role, score in _NAME_LABELS:
            pattern = _label_pattern(label)
            if label == "본인":
                pattern = re.compile(r"^\s*" + pattern.pattern + r"(?=\s|[:：])")
            else:
                pattern = re.compile(pattern.pattern + r"(?=\s|[:：(\[]|$)")
            match = pattern.search(line.text)
            if not match:
                continue
            value_role = "PERSON" if role == "REPRESENTATIVE" else role
            spatial = _spatial_name(line, match, value_role, blocks)
            if spatial:
                value, confidence, evidence_ids = spatial
            else:
                value = _name_value(line.text[match.end() :], value_role)
                confidence, evidence_ids = line.confidence, line.block_ids
            if value and (value not in candidates or score > candidates[value][0]):
                candidates[value] = (score, role, confidence, evidence_ids, label)

    if not candidates:
        return _field(None, "NOT_FOUND", role=None, candidates=[], evidence_block_ids=[])
    ranked = sorted(
        (
            (score, value, role, confidence, evidence_ids, label)
            for value, (score, role, confidence, evidence_ids, label) in candidates.items()
        ),
        reverse=True,
    )
    if preferred_role:
        preferred = [item for item in ranked if item[2] == preferred_role]
        if not preferred:
            public_candidates = [
                {"value": item[1], "role": item[2], "source_label": item[5]}
                for item in ranked[:5]
            ]
            return _field(
                None,
                "NOT_FOUND",
                role=preferred_role,
                candidates=public_candidates,
                evidence_block_ids=[],
            )
        ranked = preferred
    top_score = ranked[0][0]
    top = [item for item in ranked if item[0] == top_score]
    public_candidates = [{"value": item[1], "role": item[2], "source_label": item[5]} for item in ranked[:5]]
    if len(top) > 1:
        return _field(None, "AMBIGUOUS", role=None, candidates=public_candidates, evidence_block_ids=list(top[0][4]))
    best = top[0]
    return _field(
        best[1],
        "CONFIRMED",
        min(best[3], best[0] / 100),
        role=best[2],
        source_label=best[5],
        candidates=public_candidates,
        evidence_block_ids=list(best[4]),
    )


def _normalized_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).casefold()


def _owner_match(owner: dict[str, Any], expected_owner_name: str | None) -> dict[str, Any]:
    if not expected_owner_name:
        return {"status": "NOT_CHECKED"}
    expected = _normalized_name(expected_owner_name)
    if owner["status"] == "CONFIRMED":
        return {"status": "MATCH" if _normalized_name(owner["value"]) == expected else "MISMATCH"}
    candidate_names = {_normalized_name(item["value"]) for item in owner.get("candidates") or []}
    return {"status": "POSSIBLE_MATCH" if expected in candidate_names else "UNKNOWN"}


def _matching_ids(lines: list[Line], patterns: list[str]) -> list[str]:
    for line in lines:
        compact = re.sub(r"\s+", "", line.text)
        if any(re.search(pattern, line.text) or re.search(pattern, compact) for pattern in patterns):
            return list(line.block_ids)
    return []


def _compact(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).casefold()


def _fuzzy_contains(needle: str, haystack: str) -> float:
    needle, haystack = _compact(needle), _compact(haystack)
    if not needle or not haystack:
        return 0.0
    if len(haystack) <= len(needle):
        return SequenceMatcher(None, needle, haystack).ratio()
    return max(
        SequenceMatcher(None, needle, haystack[start : start + len(needle)]).ratio()
        for start in range(len(haystack) - len(needle) + 1)
    )


def _document_identity(
    response: dict[str, Any], lines: list[Line], signatures: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    text = "\n".join(line.text for line in lines)
    titles = [visual_title(image.get("fields") or []) for image in response.get("images") or []]
    title_text = "\n".join(title for title in titles if title)
    title_source = title_text or text[:500]
    raw = []
    for signature in signatures:
        score, evidence = score_signature(signature, text, title_text or None)
        fuzzy = _fuzzy_contains(signature.get("label_ko", ""), title_source)
        raw.append([score, signature, evidence, fuzzy])

    for item in raw:
        score, signature, evidence, fuzzy = item
        label = _compact(signature.get("label_ko", ""))
        shadowed = any(
            label
            and label != other_label
            and label in other_label
            and other_label in _compact(title_source)
            for _, other, _, _ in raw
            if (other_label := _compact(other.get("label_ko", "")))
        )
        if shadowed and any(hit.get("kind") == "title_match" for hit in evidence):
            score = max(0.0, score - 0.60)
        has_exact_title = any(
            any(hit.get("kind") == "title_match" for hit in other_evidence)
            for _, _, other_evidence, _ in raw
        )
        if (
            not has_exact_title
            and fuzzy >= 0.78
            and score >= 0.20
            and not any(hit.get("kind") == "title_match" for hit in evidence)
        ):
            score = min(0.99, score + 0.60)
        item[0] = score

    scored = sorted(((item[0], item[1]) for item in raw), key=lambda item: item[0], reverse=True)
    candidates = [
        {"value": signature["doc_type"], "name": signature.get("label_ko"), "confidence": round(score, 2)}
        for score, signature in scored[:3]
        if score > 0
    ]
    if not scored or scored[0][0] < CONFIRM_THRESHOLD:
        printed = next((title.strip() for title in titles if title.strip()), None)
        return (
            _field(None, "NOT_FOUND", candidates=candidates, evidence_block_ids=[]),
            _field(printed, "INFERRED" if printed else "NOT_FOUND", 0.5 if printed else None, evidence_block_ids=[]),
            None,
        )

    best_score, best = scored[0]
    ambiguous = len(scored) > 1 and best_score - scored[1][0] < AMBIGUOUS_GAP
    evidence_ids = _matching_ids(lines, best.get("title_patterns") or [])
    if ambiguous:
        printed = next((title.strip() for title in titles if title.strip()), None)
        return (
            _field(None, "AMBIGUOUS", best_score, candidates=candidates, evidence_block_ids=evidence_ids),
            _field(printed, "INFERRED" if printed else "AMBIGUOUS", min(best_score, 0.75), evidence_block_ids=evidence_ids),
            None,
        )
    return (
        _field(best["doc_type"], "CONFIRMED", best_score, candidates=candidates, evidence_block_ids=evidence_ids),
        _field(best.get("label_ko"), "CONFIRMED", best_score, evidence_block_ids=evidence_ids),
        best,
    )


def _default_signatures() -> list[dict[str, Any]]:
    signatures = load_signatures()
    seed = Path(__file__).resolve().parents[2] / "data" / "seeds" / "hana_corporate_account.json"
    if seed.is_file():
        signatures.extend(json.loads(seed.read_text(encoding="utf-8")).get("documents") or [])
    return list({signature["doc_type"]: signature for signature in signatures}.values())


def _preferred_owner_role(signature: dict[str, Any] | None) -> str | None:
    if not signature:
        return None
    if signature.get("doc_type") in {
        "business_registration_certificate",
        "business_registration_verification",
        "corporate_registry_certificate",
        "corporate_seal_certificate",
        "shareholder_registry",
        "share_change_statement",
        "articles_of_incorporation",
        "vat_tax_base_certificate",
        "standard_financial_statement_certificate",
    }:
        return "CORPORATION"
    if signature.get("doc_type") == "power_of_attorney":
        return None
    return "PERSON"


def _embedded_response(texts: list[str]) -> dict[str, Any]:
    images = []
    for text in texts:
        fields = []
        for row, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            top = row * 20
            fields.append(
                {
                    "inferText": line,
                    "inferConfidence": 1.0,
                    "lineBreak": True,
                    "boundingPoly": {
                        "vertices": [
                            {"x": 0, "y": top},
                            {"x": len(line) * 10, "y": top},
                            {"x": len(line) * 10, "y": top + 10},
                            {"x": 0, "y": top + 10},
                        ]
                    },
                }
            )
        images.append({"fields": fields})
    return {"images": images}


def extract_file_metadata(
    path: str | Path,
    *,
    signatures: list[dict[str, Any]] | None = None,
    expected_owner_name: str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """텍스트 PDF는 pypdf, 이미지 PDF는 CLOVA를 거쳐 같은 JSON을 반환한다."""
    from .extract import _cache_path, apply_ocr, extract, needs_ocr

    path = Path(path).expanduser()
    extracted = extract(path, use_ocr=False)
    if needs_ocr(extracted):
        apply_ocr(extracted, timeout=timeout)
        cached = _cache_path(path)
        response = json.loads(cached.read_text(encoding="utf-8")) if cached.is_file() else _embedded_response([page.text for page in extracted.pages])
    else:
        response = _embedded_response([page.text for page in extracted.pages])
    result = extract_document_metadata(
        response,
        signatures=signatures,
        expected_owner_name=expected_owner_name,
    )
    result["warnings"].extend(extracted.notes)
    return result


def extract_document_metadata(
    response: dict[str, Any],
    *,
    signatures: list[dict[str, Any]] | None = None,
    expected_owner_name: str | None = None,
) -> dict[str, Any]:
    """CLOVA General OCR JSON을 문서 식별용 JSON으로 정규화한다."""
    lines = _all_lines(response)
    blocks = _block_map(response)
    signatures = _default_signatures() if signatures is None else signatures
    document_type, document_name, signature = _document_identity(response, lines, signatures)
    owner = _owner(lines, blocks, _preferred_owner_role(signature))
    issue_labels = tuple(
        dict.fromkeys([*((signature or {}).get("issued_at_labels") or []), *ISSUE_LABELS])
    )
    issued_at = _labeled_date(lines, issue_labels, last=False)
    if issued_at["status"] == "NOT_FOUND":
        issued_at = _infer_issue_date(lines, signature)
    expires_at = _labeled_date(lines, EXPIRY_LABELS, last=True)
    owner_match = _owner_match(owner, expected_owner_name)

    warnings = []
    if document_type["status"] != "CONFIRMED":
        warnings.append("문서 종류를 확정하지 못했습니다.")
    if owner["status"] != "CONFIRMED":
        warnings.append("명의자 이름을 하나로 확정하지 못했습니다.")
    if issued_at["status"] != "CONFIRMED":
        warnings.append("발급일이 명시 라벨로 확인되지 않았습니다.")
    if expires_at["status"] == "NOT_FOUND":
        warnings.append("문서에 명시된 유효기간 날짜가 없습니다.")
    if owner_match["status"] in {"MISMATCH", "UNKNOWN", "POSSIBLE_MATCH"}:
        warnings.append("입력한 본인 이름과 문서 명의자를 확정적으로 일치시키지 못했습니다.")

    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": document_type,
        "document_name": document_name,
        "owner_name": owner,
        "owner_match": owner_match,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "needs_review": any(
            field["status"] != "CONFIRMED" for field in (document_type, owner, issued_at)
        )
        or owner_match["status"] in {"MISMATCH", "UNKNOWN", "POSSIBLE_MATCH"}
        or expires_at["status"] == "AMBIGUOUS",
        "warnings": warnings,
    }
