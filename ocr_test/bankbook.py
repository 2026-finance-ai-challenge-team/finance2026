"""통장사본 필드 추출 — 정규식 휴리스틱(임시).

본선 파이프라인에서는 이 자리를 LLM 추출이 맡고, 판정은 규칙 엔진이 한다.
여기서는 "OCR 텍스트가 실제로 쓸 만하게 나오는지"를 눈으로 확인하려고
사람이 읽을 수 있는 요약만 만든다. 이 결과로 준비 상태를 결정하지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dataclass_field
from typing import Sequence

# 통장사본 상단 로고/문구에서 자주 보이는 은행 표기
KNOWN_BANKS: tuple[tuple[str, str], ...] = (
    ("국민은행", "KB국민은행"),
    ("KB", "KB국민은행"),
    ("신한은행", "신한은행"),
    ("우리은행", "우리은행"),
    ("하나은행", "하나은행"),
    ("농협", "NH농협은행"),
    ("기업은행", "IBK기업은행"),
    ("카카오뱅크", "카카오뱅크"),
    ("케이뱅크", "케이뱅크"),
    ("토스뱅크", "토스뱅크"),
    ("새마을금고", "새마을금고"),
    ("우체국", "우체국"),
    ("SC제일", "SC제일은행"),
    ("씨티", "한국씨티은행"),
    ("수협", "Sh수협은행"),
    ("부산은행", "부산은행"),
    ("대구은행", "대구은행" ),
    ("iM뱅크", "iM뱅크"),
    ("경남은행", "경남은행"),
    ("광주은행", "광주은행"),
    ("전북은행", "전북은행"),
    ("제주은행", "제주은행"),
)

# 계좌번호: 하이픈으로 끊긴 숫자 묶음, 합계 10자리 이상
_ACCOUNT_RE = re.compile(r"(?<![\d-])\d{2,6}(?:-\d{2,6}){1,3}(?![\d-])")
# 전화번호로 오인하기 쉬운 형태
_PHONE_RE = re.compile(r"(?<![\d-])(?:0\d{1,2}|1\d{3})-\d{3,4}-\d{4}(?![\d-])")
_DATE_RE = re.compile(r"(?<!\d)(\d{4})[.\-/\s]?(\d{1,2})[.\-/\s]?(\d{1,2})(?!\d)")
_SWIFT_RE = re.compile(r"\b[A-Z]{4}KR[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b")
_HOLDER_HONORIFIC_RE = re.compile(r"([가-힣]{2,6})\s*(?:님|귀하)")
_HOLDER_LABEL_RE = re.compile(r"(?:예금주|성명|명의|계좌주)\s*[:：]?\s*([가-힣]{2,6}|[A-Z][A-Za-z\s]{2,30})")

_ACCOUNT_LABELS = ("계좌번호", "계좌 번호", "구좌번호", "Account")
_OPEN_DATE_LABELS = ("신규가입일", "개설일", "신규일", "가입일")


@dataclass
class BankbookFields:
    bank: str | None = None
    account_number: str | None = None
    holder: str | None = None
    product_name: str | None = None
    opened_at: str | None = None
    branch: str | None = None
    swift_code: str | None = None
    notes: list[str] = dataclass_field(default_factory=list)

    def as_rows(self) -> list[tuple[str, str]]:
        labels = (
            ("은행", self.bank),
            ("상품명", self.product_name),
            ("예금주", self.holder),
            ("계좌번호", self.account_number),
            ("신규가입일", self.opened_at),
            ("계좌관리점", self.branch),
            ("SWIFT", self.swift_code),
        )
        return [(label, value) for label, value in labels if value]

    def missing(self) -> list[str]:
        """교차 확인에 꼭 필요한 필드 중 비어 있는 것."""
        required = (("은행", self.bank), ("예금주", self.holder), ("계좌번호", self.account_number))
        return [label for label, value in required if not value]


def _value_after_label(lines: Sequence[str], labels: Sequence[str]) -> str | None:
    """`라벨 값` 한 줄, 또는 라벨만 있는 줄 다음 줄의 값을 집는다."""
    for index, line in enumerate(lines):
        for label in labels:
            if label not in line:
                continue
            tail = line.split(label, 1)[1].strip(" :：\t")
            if tail:
                return tail
            if index + 1 < len(lines):
                nxt = lines[index + 1].strip()
                if nxt:
                    return nxt
    return None


def _normalize_date(text: str) -> str | None:
    match = _DATE_RE.search(text)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def extract_bankbook_fields(lines: Sequence[str]) -> BankbookFields:
    """OCR 줄 목록에서 통장사본 주요 필드를 추정한다."""
    result = BankbookFields()
    joined = "\n".join(lines)

    for needle, canonical in KNOWN_BANKS:
        if needle in joined:
            result.bank = canonical
            break

    # 계좌번호: 라벨 옆의 값을 먼저 보고, 없으면 전화번호를 뺀 후보 중 가장 긴 것
    labelled = _value_after_label(lines, _ACCOUNT_LABELS)
    if labelled:
        match = _ACCOUNT_RE.search(labelled)
        if match:
            result.account_number = match.group(0)
    if not result.account_number:
        phones = set(_PHONE_RE.findall(joined))
        candidates = [
            candidate
            for candidate in _ACCOUNT_RE.findall(joined)
            if candidate not in phones
            and not _PHONE_RE.fullmatch(candidate)
            and len(re.sub(r"\D", "", candidate)) >= 10
        ]
        if candidates:
            result.account_number = max(candidates, key=lambda c: len(re.sub(r"\D", "", c)))

    holder = _HOLDER_LABEL_RE.search(joined)
    if holder:
        result.holder = holder.group(1).strip()
    else:
        honorific = _HOLDER_HONORIFIC_RE.search(joined)
        if honorific:
            result.holder = honorific.group(1)

    # 상품명: '통장'/'예금'/'적금'으로 끝나는 첫 줄
    for line in lines:
        stripped = line.strip()
        if len(stripped) <= 40 and re.search(r"(통장|예금|적금|계좌)$", stripped):
            result.product_name = stripped
            break

    open_date_raw = _value_after_label(lines, _OPEN_DATE_LABELS)
    if open_date_raw:
        result.opened_at = _normalize_date(open_date_raw)

    branch = _value_after_label(lines, ("계좌관리점", "관리점", "개설점", "취급점"))
    if branch:
        result.branch = branch.split()[0]

    swift = _SWIFT_RE.search(joined)
    if swift:
        result.swift_code = swift.group(0)

    if result.account_number and _PHONE_RE.fullmatch(result.account_number):
        result.notes.append("계좌번호 후보가 전화번호 형식과 겹칩니다. 사용자 확인이 필요합니다.")
    for label in result.missing():
        result.notes.append(f"{label}를 찾지 못했습니다. 사용자 입력으로 보완해야 합니다.")

    return result
