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
from modules.doc_classify.extract import Extracted, Page, visual_title  # noqa: E402

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


def ocr_field(text: str, *, top: float, height: float, left: float = 0.0) -> dict:
    """CLOVA 응답 형태의 필드 하나를 만든다."""
    return {
        "inferText": text,
        "boundingPoly": {
            "vertices": [
                {"x": left, "y": top},
                {"x": left + 20 * len(text), "y": top},
                {"x": left + 20 * len(text), "y": top + height},
                {"x": left, "y": top + height},
            ]
        },
    }


def test_글자_크기로_제목을_찾는다():
    """실측 재현: 큰 제목은 낱자로 쪼개지고, 하단 직인도 제목만큼 크다."""
    fields = [
        # 상단의 큰 제목 — CLOVA가 낱자로 쪼갠 형태
        *[ocr_field(ch, top=90, height=38, left=i * 40) for i, ch in enumerate("주민등록표")],
        *[ocr_field(ch, top=130, height=36, left=i * 40) for i, ch in enumerate("(초본)")],
        # 본문 (작은 글씨). 실제 문서는 필드가 수백 개라 중앙값이 본문 크기에서 잡힌다.
        *[ocr_field(f"본문{i}", top=300 + i * 14, height=21) for i in range(40)],
        *[ocr_field(w, top=400, height=21, left=200) for w in ["주소", "변동일", "변동사유"]],
        # 하단 발급기관 직인 — 제목만큼 크지만 아래에 있다
        ocr_field("서울특별시 구로구청장", top=880, height=39),
    ]
    title = visual_title(fields)
    squeezed = title.replace(" ", "")
    assert "주민등록표" in squeezed, title
    assert "초본" in squeezed, title
    assert "구로구청장" not in squeezed, f"하단 직인이 제목에 섞였다: {title}"


def test_낱자로_쪼개진_제목도_분류된다():
    """'주 민 등 록 표 ( 초 본 )' 형태가 시그니처에 걸려야 한다."""
    page = Page(1, "주소 변동 사항\n변동일 2024-03-02\n문서확인번호 1234", "ocr")
    page.title = "주 민 등 록 표 ( 초 본 ) 서울특별시"
    result = classify_one(Extracted(path=Path("사진.jpg"), kind="jpg", pages=[page]), SIGNATURES)
    assert result["doc_type"] == "resident_registration_abstract", result["doc_type"]
    assert not result["needs_user_confirm"]


def test_유효기간을_계산한다():
    from datetime import date

    from modules.doc_classify.classify import expiry_of

    def check(issued: str, confident: bool):
        return expiry_of(
            {
                "doc_type": "resident_registration_copy",
                "fields": {"issued_at": issued, "issued_at_confident": confident},
            },
            SIGNATURES,
            today=date(2026, 8, 18),
        )

    # 등본 유효기간 90일. 2026-08-11 발급 → 2026-11-09 만료.
    fresh = check("2026-08-11", True)
    assert fresh["expires_at"] == "2026-11-09", fresh
    assert fresh["days_left"] == 83 and fresh["note"] == "83일 남음", fresh

    stale = check("2026-01-01", True)
    assert stale["days_left"] < 0 and stale["note"] == "기한 만료", stale

    # 발급일이 추정이면 '유효함'을 단정하지 않는다. 거짓 준비 완료를 막는 방향이다.
    guessed_ok = check("2026-08-11", False)
    assert guessed_ok["estimated"] is True, guessed_ok
    assert "확인 필요" in guessed_ok["note"], guessed_ok

    # 추정이어도 만료 쪽은 알려준다. 그쪽으로 틀리는 건 안전하다.
    guessed_expired = check("2026-01-01", False)
    assert "지났을 수 있음" in guessed_expired["note"], guessed_expired

    # 발급일을 못 읽으면 만료를 단정하지 않는다.
    unknown = expiry_of(
        {"doc_type": "resident_registration_copy", "fields": {}}, SIGNATURES, today=date(2026, 8, 18)
    )
    assert unknown["expires_at"] is None and "발급일" in unknown["note"], unknown


def test_파일명을_안전하게_정규화한다():
    from modules.doc_classify.pack import safe_component, submission_name

    assert safe_component('주민등록표 등본<>:"/\\|?*') == "주민등록표등본"
    assert safe_component("") == "미상"

    doc = {
        "source_name": "정부24 - 주민등록표 등본(초본) 발급 _ 문서출력.pdf",
        "classification": {"label_ko": "주민등록표 초본"},
        "fields": {"issued_at": "2026-08-11"},
    }
    assert submission_name(doc, 1) == "2026-08-11_주민등록표초본_01.pdf"

    # 분류 실패는 원본 이름을 살리되 눈에 띄게 표시한다
    unknown = {"source_name": "IMG_2931.jpg", "classification": {"label_ko": None}, "fields": {}}
    assert submission_name(unknown, 7).startswith("확인필요_IMG_2931")


def test_리포트에_원문이_새지_않는다():
    from modules.doc_classify.pack import build_report

    result = {
        "task_id": "t",
        "task_label": "테스트 업무",
        "checked_at": "2026-08-18",
        "task_verified": False,
        "ocr_calls_total": 0,
        "missing": {"required": ["utility_bill"], "conditional": [], "alternatives": []},
        "documents": [
            {
                "source_name": "a.pdf",
                "classification": {"doc_type": "resident_registration_copy", "label_ko": "주민등록표 등본"},
                "fields": {"issuer": "행정안전부", "issued_at": "2026-08-11"},
                "validity": {"expires_at": "2026-11-09", "days_left": 83, "note": "83일 남음"},
                "relevance": {"status": "관련"},
                "confirm_reason": None,
            }
        ],
    }
    report = build_report(result, SIGNATURES)
    assert "주민등록표 등본" in report
    assert "공공요금" in report, "부족한 서류가 리포트에 안 나온다"
    assert "2026-11-09" in report
    assert "임시값" in report, "미검증 경고가 빠졌다"


def test_샘플_JSON이_계약을_지킨다():
    """웹이 붙을 샘플이 깨지면 화면도 깨진다. 계약 위반을 여기서 잡는다."""
    import json

    from modules.doc_classify.schema import validate

    path = Path(__file__).resolve().parent / "examples" / "classify-result.sample.json"
    sample = json.loads(path.read_text(encoding="utf-8"))
    validate(sample)

    statuses = {d["relevance"]["status"] for d in sample["documents"]}
    assert statuses == {"관련", "이번 업무에는 불필요", "판단 불가"}, (
        f"샘플이 세 가지 관련성을 모두 보여줘야 화면 케이스가 다 검증된다: {statuses}"
    )


def test_계약이_분류실패를_불필요로_내보내지_못하게_막는다():
    """스키마 검증이 실제로 위험한 조합을 거른다."""
    from modules.doc_classify.schema import SCHEMA_VERSION, SchemaError, validate

    bad = {
        "schema_version": SCHEMA_VERSION,
        "task_id": "t",
        "checked_at": "2026-08-19",
        "documents": [
            {
                "file_id": "f01",
                "source_name": "a.pdf",
                "media": {"kind": "pdf", "pages": 1},
                "classification": {"doc_type": None, "confidence": 0.1, "evidence": []},
                "relevance": {"status": "이번 업무에는 불필요"},
            }
        ],
    }
    try:
        validate(bad)
    except SchemaError as exc:
        assert "판단 불가" in str(exc), exc
    else:
        raise AssertionError("분류 실패를 '불필요'로 내보냈는데 통과했다")


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
