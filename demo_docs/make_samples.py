"""카카오뱅크 한도계좌 해제 회귀검증용 합성 PDF 8종을 만든다.

실제 기관 문서를 복제하지 않는다. 모든 기관명·주소·번호·직인은 가상이며,
각 페이지에 합성 샘플 표시를 반복해 실제 증명서로 오인할 수 없게 한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from reportlab.graphics.barcode import code128
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas


HERE = Path(__file__).resolve().parent
W, H = A4
FONT = "HYSMyeongJo-Medium"
INK = HexColor("#172033")
MUTED = HexColor("#667085")
LINE = HexColor("#CBD5E1")
PALE = HexColor("#F5F7FA")
BLUE = HexColor("#315C9B")
TEAL = HexColor("#177D77")
RED = HexColor("#B42318")
YELLOW = HexColor("#FFF6CC")
FOOTER = "ProofBridge 테스트용 합성 샘플 · 실제 증명서가 아니며 효력이 없습니다"

pdfmetrics.registerFont(UnicodeCIDFont(FONT))


def text(c: canvas.Canvas, x: float, y: float, value: str, size: float = 9, *, color=INK) -> None:
    c.setFont(FONT, size)
    c.setFillColor(color)
    c.drawString(x, y, value)


def right(c: canvas.Canvas, x: float, y: float, value: str, size: float = 9, *, color=INK) -> None:
    c.setFont(FONT, size)
    c.setFillColor(color)
    c.drawRightString(x, y, value)


def center(c: canvas.Canvas, x: float, y: float, value: str, size: float = 9, *, color=INK) -> None:
    c.setFont(FONT, size)
    c.setFillColor(color)
    c.drawCentredString(x, y, value)


def start(name: str, *, issuer: str, document_code: str) -> canvas.Canvas:
    c = canvas.Canvas(str(HERE / name), pagesize=A4, invariant=1)
    c.setTitle("ProofBridge 합성 샘플")
    c.setAuthor("ProofBridge synthetic fixture generator")
    c.setFillColor(PALE)
    c.rect(34, H - 64, W - 68, 30, fill=1, stroke=0)
    text(c, 44, H - 52, issuer, 9)
    right(c, W - 44, H - 52, f"문서코드 {document_code}", 8, color=MUTED)
    c.setFillColor(YELLOW)
    c.roundRect(W - 128, H - 94, 84, 20, 4, fill=1, stroke=0)
    center(c, W - 86, H - 87, "합성 SAMPLE", 8, color=RED)
    return c


def finish(c: canvas.Canvas) -> None:
    c.setStrokeColor(LINE)
    c.line(36, 47, W - 36, 47)
    text(c, 40, 31, FOOTER, 7.5, color=RED)
    right(c, W - 40, 31, "1 / 1", 7.5, color=MUTED)
    c.save()


def title(c: canvas.Canvas, value: str, subtitle: str = "", *, size: float = 20) -> None:
    center(c, W / 2, H - 116, value, size)
    if subtitle:
        center(c, W / 2, H - 135, subtitle, 8, color=MUTED)


def section(c: canvas.Canvas, y: float, value: str, *, accent=BLUE) -> float:
    c.setFillColor(accent)
    c.rect(40, y - 4, 4, 17, fill=1, stroke=0)
    text(c, 51, y, value, 11)
    return y - 18


def grid(
    c: canvas.Canvas,
    y: float,
    rows: Sequence[Sequence[str]],
    *,
    widths: Sequence[float] = (92, 411),
    row_height: float = 26,
) -> float:
    x = 46
    total = sum(widths)
    for row in rows:
        y -= row_height
        c.setFillColor(PALE)
        c.rect(x, y, widths[0], row_height, fill=1, stroke=0)
        c.setStrokeColor(LINE)
        c.rect(x, y, total, row_height, fill=0, stroke=1)
        c.line(x + widths[0], y, x + widths[0], y + row_height)
        text(c, x + 8, y + 9, row[0], 8, color=MUTED)
        text(c, x + widths[0] + 9, y + 9, row[1], 9)
    return y


def money_summary(c: canvas.Canvas, y: float, label: str, amount: str, due: str) -> float:
    c.setFillColor(HexColor("#EEF4FF"))
    c.roundRect(46, y - 64, W - 92, 56, 7, fill=1, stroke=0)
    text(c, 60, y - 29, label, 9, color=MUTED)
    text(c, 60, y - 50, amount, 17, color=BLUE)
    right(c, W - 60, y - 42, f"납부기한  {due}", 9)
    return y - 78


def barcode(c: canvas.Canvas, y: float, value: str) -> None:
    code = code128.Code128(value, barHeight=26, barWidth=0.62, humanReadable=False)
    code.drawOn(c, W - 191, y)
    right(c, W - 46, y - 11, value, 6.5, color=MUTED)


def stamp(c: canvas.Canvas, x: float, y: float) -> None:
    c.setStrokeColor(HexColor("#C84B31"))
    c.setLineWidth(1.6)
    c.circle(x, y, 24, fill=0, stroke=1)
    center(c, x, y - 4, "합성", 12, color=HexColor("#C84B31"))


def simple_table(c: canvas.Canvas, y: float, headers: Sequence[str], rows: Sequence[Sequence[str]], xs: Sequence[float]) -> float:
    c.setFillColor(PALE)
    c.rect(46, y - 25, 503, 25, fill=1, stroke=0)
    for x, label in zip(xs, headers):
        text(c, x, y - 16, label, 7.5, color=MUTED)
    height = 25 + 27 * len(rows)
    c.setStrokeColor(LINE)
    c.rect(46, y - height, 503, height, fill=0, stroke=1)
    for i, row in enumerate(rows):
        yy = y - 44 - i * 27
        for x, value in zip(xs, row):
            text(c, x, yy, value, 8)
    return y - height


def make_utility_bill() -> str:
    name = "합성_전기요금청구서.pdf"
    c = start(name, issuer="예시전력 고객센터", document_code="PB-EL-202608")
    title(c, "전기 요금 청구서", "2026년 8월분 · 가상 고지서")
    y = grid(c, H - 158, [("고객번호", "0000-0000-0000"), ("고객명", "홍길동"),
        ("사용장소", "서울특별시 예시구 예시로 000, 000동 000호"), ("청구일", "2026-08-05")])
    y = money_summary(c, y - 14, "이번 달 청구금액", "43,120 원", "2026-08-31")
    y = section(c, y, "요금 상세")
    y = grid(c, y, [("사용기간", "2026-07-01 ~ 2026-07-31"), ("사용량", "245 kWh"),
        ("기본요금", "9,100 원"), ("사용요금", "31,520 원"), ("부가세 등", "2,500 원")], row_height=23)
    y = section(c, y - 18, "납부 안내", accent=TEAL)
    grid(c, y, [("납부계좌", "예시은행 000-0000-0000-00"), ("문의", "예시전력 고객센터 0000-0000")])
    barcode(c, 88, "PBEL202608000000")
    finish(c)
    return name


def make_management_fee_notice() -> str:
    name = "합성_관리비고지서.pdf"
    c = start(name, issuer="예시아파트 관리사무소", document_code="PB-MF-2608")
    title(c, "공동주택 관리비 고지서", "2026년 8월분")
    y = grid(c, H - 158, [("입주자명", "홍길동"), ("동·호", "000동 000호"),
        ("주소", "서울특별시 예시구 예시로 000, 000동 000호"), ("청구년월", "2026년 8월")])
    y = money_summary(c, y - 14, "당월 청구금액", "145,000 원", "2026-08-31")
    y = section(c, y, "관리비 부과 내역")
    y = grid(c, y, [("일반관리비", "85,000 원"), ("수도요금", "18,000 원"),
        ("난방비", "42,000 원"), ("연체료", "0 원")], row_height=24)
    y = section(c, y - 18, "자동이체 및 문의", accent=TEAL)
    grid(c, y, [("납부계좌", "예시은행 000-000-000000"), ("관리사무소", "000-0000-0000")])
    text(c, 48, 91, "※ 주민등록표 등본과 함께 제출하는 합성 시나리오입니다.", 7.5, color=MUTED)
    finish(c)
    return name


def make_resident_copy() -> str:
    name = "합성_주민등록표등본.pdf"
    c = start(name, issuer="예시구 민원행정과 · 전자민원", document_code="PB-RR-000001")
    title(c, "주 민 등 록 표 ( 등 본 )", "합성 세대 정보 · 실제 행정문서 아님")
    text(c, 46, H - 157, "문서확인번호  0000-0000-0000-0000", 8, color=MUTED)
    right(c, W - 46, H - 157, "발급일자  2026-08-29", 8, color=MUTED)
    y = section(c, H - 188, "세대 기본정보")
    y = grid(c, y, [("세대주 성명", "홍길동"), ("주소", "서울특별시 예시구 예시로 000, 000동 000호"),
        ("세대구성 사유", "전입"), ("구성일", "2024-03-02")])
    y = section(c, y - 20, "세대원 정보")
    y = simple_table(c, y, ("성명", "세대주와의 관계", "주민등록번호", "전입일"),
        (("홍길동", "본인", "000000-0000000", "2024-03-02"), ("김영희", "배우자", "000000-0000000", "2024-03-02")),
        (54, 170, 315, 445))
    text(c, 46, y - 34, "위 기재사항은 합성 주민등록표 내용과 일치함을 테스트 목적으로 표시합니다.", 8.5)
    center(c, W / 2, y - 92, "예시구청장", 14)
    stamp(c, W / 2 + 76, y - 88)
    barcode(c, 86, "PBRR000000000001")
    finish(c)
    return name


def make_tax_bill() -> str:
    name = "합성_세금고지서.pdf"
    c = start(name, issuer="예시구 세무행정과", document_code="PB-TX-2026-0810")
    title(c, "지방세 납부고지서", "납세자 보관용 · 합성")
    y = grid(c, H - 158, [("납세자", "홍길동"), ("주소", "서울특별시 예시구 예시로 000"),
        ("세목", "재산세"), ("과세대상", "합성 테스트 자료"), ("고지일", "2026-08-10")], row_height=25)
    y = money_summary(c, y - 14, "납부할 세액", "123,450 원", "2026-08-31")
    y = section(c, y, "세액 산출 내역")
    y = grid(c, y, [("본세", "110,000 원"), ("지방교육세", "13,450 원"), ("합계", "123,450 원")], row_height=24)
    y = section(c, y - 18, "전자납부 안내", accent=TEAL)
    grid(c, y, [("전자납부번호", "00000-0-00-0000000"), ("가상계좌", "예시은행 000-000000-00-000")])
    barcode(c, 87, "PBTX202608100000")
    finish(c)
    return name


def make_health_insurance_certificate() -> str:
    name = "합성_건강보험자격득실확인서.pdf"
    c = start(name, issuer="예시 건강보험 민원센터", document_code="PB-HI-000001")
    title(c, "건강보험 자격득실 확인서", "공식 기관 형식을 복제하지 않은 합성 양식")
    text(c, 46, H - 158, "문서확인번호  0000-0000-0000-0000", 8, color=MUTED)
    right(c, W - 46, H - 158, "발급일자  2026-08-29", 8, color=MUTED)
    y = section(c, H - 188, "가입자 정보")
    y = grid(c, y, [("가입자 성명", "홍길동"), ("생년월일", "1990-01-01")])
    y = section(c, y - 20, "자격득실 내역")
    y = simple_table(c, y, ("구분", "사업장 명칭", "자격취득일", "자격상실일"),
        (("직장", "주식회사 예시", "2023-03-02", "-"), ("지역", "예시구", "2020-01-01", "2023-03-01")),
        (54, 130, 330, 435))
    text(c, 46, y - 34, "위 가입자의 건강보험 자격득실 내역을 합성 데이터로 확인합니다.", 8.5)
    center(c, W / 2, y - 92, "국민건강보험공단 예시 민원센터장", 12)
    stamp(c, W / 2 + 130, y - 88)
    barcode(c, 87, "PBHI000000000001")
    finish(c)
    return name


def make_employment_contract() -> str:
    name = "합성_근로계약서.pdf"
    c = start(name, issuer="주식회사 예시 · 인사팀", document_code="PB-EC-2025-1220")
    title(c, "근 로 계 약 서", "기간의 정함이 있는 근로계약 · 합성")
    y = section(c, H - 163, "계약 당사자")
    y = grid(c, y, [("사용자", "주식회사 예시  대표자 김예시"), ("사업장", "서울특별시 예시구 예시로 000"),
        ("근로자", "홍길동"), ("생년월일", "1990-01-01")], row_height=25)
    y = section(c, y - 18, "근로조건")
    y = grid(c, y, [("근로기간", "2026-01-01 ~ 2026-12-31"), ("근무장소", "서울특별시 예시구 예시로 000"),
        ("업무내용", "서비스 운영 지원"), ("근로시간", "09:00 ~ 18:00 (휴게 12:00 ~ 13:00)"),
        ("임금", "월 3,000,000 원 · 매월 25일 지급")], row_height=25)
    y = section(c, y - 18, "계약 확인", accent=TEAL)
    text(c, 50, y - 14, "본 계약서는 OCR 검증을 위한 가상 당사자 간 합성 문서입니다.", 8)
    text(c, 50, y - 37, "계약일  2025-12-20", 9)
    grid(c, y - 48, [("사용자 서명", "김예시 (합성 인)"), ("근로자 서명", "홍길동 (합성 인)")], row_height=27)
    finish(c)
    return name


def make_business_registration_certificate() -> str:
    name = "합성_사업자등록증.pdf"
    c = start(name, issuer="예시세무서 민원봉사실", document_code="PB-BR-000000")
    title(c, "사 업 자 등 록 증", "법인사업자 · 합성")
    y = grid(c, H - 164, [("등록번호", "000-00-00000"), ("법인명", "주식회사 예시"), ("대표자", "김예시"),
        ("개업연월일", "2020-01-01"), ("사업장 소재지", "서울특별시 예시구 예시로 000"),
        ("본점 소재지", "사업장 소재지와 같음"), ("업태", "정보통신업"), ("종목", "소프트웨어 개발 및 공급")], row_height=28)
    text(c, 46, y - 36, "사업자등록번호 : 000-00-00000", 8, color=MUTED)
    text(c, 46, y - 65, "위 사업자는 합성 테스트 목적으로 등록된 것으로 표시합니다.", 9)
    center(c, W / 2, y - 112, "예시세무서장", 14)
    stamp(c, W / 2 + 75, y - 108)
    barcode(c, 87, "PBBR000000000000")
    finish(c)
    return name


def checklist(c: canvas.Canvas, y: float, items: Iterable[str]) -> None:
    for item in items:
        c.setStrokeColor(LINE)
        c.rect(54, y - 3, 9, 9, fill=0, stroke=1)
        text(c, 70, y - 2, item, 8.5)
        y -= 20


def make_mobile_phone_payment_certificate() -> str:
    name = "합성_휴대폰요금납부확인서.pdf"
    c = start(name, issuer="예시모바일 고객지원", document_code="PB-MP-20260829")
    title(c, "휴대폰 요금 납부계좌 등록 및 납부확인서", "예시모바일 · 합성", size=16)
    y = grid(c, H - 158, [("발급일", "2026-08-29"), ("가입자명", "홍길동"),
        ("휴대폰번호", "010-0000-0000"), ("납부계좌", "예시은행 000-0000-000000"), ("납부방법", "계좌 자동이체")], row_height=26)
    y = section(c, y - 20, "최근 납부내역")
    y = simple_table(c, y, ("청구월", "청구금액", "납부일", "상태"),
        (("2026년 7월", "55,000 원", "2026-07-25", "납부확인"), ("2026년 6월", "55,000 원", "2026-06-25", "납부확인"),
         ("2026년 5월", "52,000 원", "2026-05-25", "납부확인")), (54, 205, 340, 455))
    y = section(c, y - 20, "확인 사항", accent=TEAL)
    checklist(c, y - 8, ("납부계좌 등록 상태 확인", "최근 요금 납부내역 확인", "발급일 기준 합성 데이터 확인"))
    barcode(c, 87, "PBMP202608290000")
    finish(c)
    return name


def main() -> int:
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    made = [make_utility_bill(), make_management_fee_notice(), make_resident_copy(), make_tax_bill(),
        make_health_insurance_certificate(), make_employment_contract(), make_business_registration_certificate(),
        make_mobile_phone_payment_certificate()]
    for name in made:
        print(f"  {name}  ({(HERE / name).stat().st_size:,} bytes)")
    print(f"\n{len(made)}개 생성. 전부 합성 데이터이다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
