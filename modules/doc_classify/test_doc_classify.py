"""합성 텍스트로 분류 로직을 검증한다. API 호출도, 실제 개인문서도 쓰지 않는다.

    finance/Scripts/python.exe modules/doc_classify/test_doc_classify.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.doc_classify.classify import (  # noqa: E402
    CONFIRM_THRESHOLD,
    classify_one,
    judge_relevance,
    load_signatures,
    load_task,
    score_signature,
)
from modules.doc_classify.extract import Extracted, Page  # noqa: E402

SIGNATURES = load_signatures()
TASK = load_task("kakaobank.limit_release.living_expense")

# --- 합성 문서 (실제 개인정보 없음) ---------------------------------------

DEUNGBON = """주민등록표 (등본)
행정안전부 정부24
세대주 성명 홍길동    세대주와의 관계 본인
세대원 김영희 배우자
발급일자 2026-08-11
문서확인번호 1234-5678-9012-3456"""

CHOBON = """주민등록표 (초본)
행정안전부 정부24
성명 홍길동
주소 변동 사항
변동일 2024-03-02  변동사유 전입
발급일자 2026-08-11
문서확인번호 9999-8888-7777-6666"""

TAX_RETURN = """(2025년 귀속) 종합소득세 · 농어촌특별세
과세표준확정신고 및 납부계산서
관리번호
기본사항  성명  주민등록번호
기장 의무  신고 유형
과세표준  산출세액
신고인 홍길동"""

LOCAL_TAX = """(2025년 귀속)종합소득에 대한 개인지방소득세
지방세법 시행규칙[별지 제40호의2서식]
과세표준확정신고 및 납부계산서
관리번호
납세지 서울특별시
과세표준  산출세액"""

TAX_RECEIPT = """종합소득세 신고서 접수증
접수번호 113-2026-2-000000000000  접수일시 2026-05-03 15:43:25
제출내역
신고서종류 종합소득세 정기확정신고서
국세청홈택스에 위와 같이 접수되었습니다."""

UNRELATED = """취업 후기
1학년 때부터 준비했던 내용을 정리합니다.
면접에서 받은 질문과 답변"""


def build(text: str) -> Extracted:
    return Extracted(path=Path("합성.pdf"), kind="pdf", pages=[Page(1, text, "embedded")])


# --- 검증 ------------------------------------------------------------------


def test_등본과_초본을_섞지_않는다():
    """제목이 거의 같은 쌍이 갈리는가. 이게 틀리면 규칙 엔진이 엉뚱한 판정을 낸다."""
    a = classify_one(build(DEUNGBON), SIGNATURES)
    b = classify_one(build(CHOBON), SIGNATURES)
    assert a["doc_type"] == "resident_registration_copy", a["doc_type"]
    assert b["doc_type"] == "resident_registration_abstract", b["doc_type"]
    assert not a["needs_user_confirm"], "등본이 애매하다고 나오면 안 된다"
    assert not b["needs_user_confirm"], "초본이 애매하다고 나오면 안 된다"


def test_negative_anchor는_즉시_탈락시킨다():
    signature = next(s for s in SIGNATURES if s["doc_type"] == "resident_registration_abstract")
    score, evidence = score_signature(signature, DEUNGBON)
    assert score == 0.0, f"등본이 초본 시그니처에서 {score}점을 받았다"
    assert evidence[0]["kind"] == "negative_anchor"


def test_실제_신고서_문구가_분류된다():
    result = classify_one(build(TAX_RETURN), SIGNATURES)
    assert result["doc_type"] == "income_tax_return", result["doc_type"]
    assert result["confidence"] >= CONFIRM_THRESHOLD


def test_세금문서_3종이_서로_안_섞인다():
    """셋 다 '과세표준확정신고 및 납부계산서'를 제목에 갖는다. 실제 오분류가 났던 자리다."""
    got = {
        name: classify_one(build(text), SIGNATURES)["doc_type"]
        for name, text in (
            ("신고서", TAX_RETURN),
            ("지방소득세", LOCAL_TAX),
            ("접수증", TAX_RECEIPT),
        )
    }
    assert got["신고서"] == "income_tax_return", got
    assert got["지방소득세"] == "local_income_tax_return", got
    assert got["접수증"] == "tax_return_receipt", got


def test_하단_안내문의_서류이름을_제목으로_보지_않는다():
    """정부24 문서 하단 안내문의 '가족관계증명서'가 제목으로 잡혀 오분류가 났던 자리다."""
    text = DEUNGBON + "\n" * 3 + "가" * 600 + """
[안내] 가족관계증명서 등 다른 증명서는 정부24에서 함께 발급받을 수 있습니다."""
    result = classify_one(build(text), SIGNATURES)
    assert result["doc_type"] == "resident_registration_copy", result["doc_type"]


def test_모르는_문서는_판단불가지_불필요가_아니다():
    """분류 실패를 '불필요'로 내보내면 필수 서류 누락이 조용히 통과한다."""
    result = classify_one(build(UNRELATED), SIGNATURES)
    assert result["doc_type"] is None, result["doc_type"]
    assert result["needs_user_confirm"] is True
    assert judge_relevance(result["doc_type"], TASK)["status"] == "판단 불가"


def test_분류됐지만_업무에_없으면_불필요다():
    assert judge_relevance("income_tax_return", TASK)["status"] == "이번 업무에는 불필요"
    assert judge_relevance("utility_bill", TASK)["status"] == "관련"


def test_발급일을_뽑는다():
    result = classify_one(build(DEUNGBON), SIGNATURES)
    assert result["fields"].get("issued_at") == "2026-08-11", result["fields"]


def test_출력에_원문_텍스트가_없다():
    """개인정보 원칙 — 분류 결과는 원문을 담지 않는다."""
    blob = repr(classify_one(build(DEUNGBON), SIGNATURES))
    assert "홍길동" not in blob, "출력에 원문이 새고 있다"
    assert "김영희" not in blob, "출력에 원문이 새고 있다"


def run(name: str, fn) -> bool:
    try:
        fn()
    except AssertionError as exc:
        print(f"FAIL {name}: {exc}")
        return False
    print(f"ok   {name}")
    return True


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = sum(run(name, fn) for name, fn in tests)
    print(f"\n{passed}/{len(tests)} 통과")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
