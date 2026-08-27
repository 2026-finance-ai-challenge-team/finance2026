"""데모용 합성 문서를 만든다. 실제 개인정보는 한 글자도 쓰지 않는다.

    finance/Scripts/python.exe demo_docs/make_samples.py

여기서 나오는 PDF는 **테스트 픽스처**다. 실제 증명서가 아니며, 각 문서 하단에
그 사실을 명시한다. 저장소에 커밋해도 되는 유일한 문서 종류다.

이름·주소·번호는 전부 지어낸 값이다.
- 이름: 홍길동, 김영희 (공개 예시 이름)
- 주민번호: 000000-0000000 형태의 자리표시자
- 주소·번호: 실재하지 않는 값
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
W, H = A4

# reportlab 내장 한국어 CID 폰트. 별도 폰트 파일이 필요 없다.
pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
FONT = "HYSMyeongJo-Medium"

FOOTER = "이 문서는 ProofBridge 테스트용 합성 샘플입니다. 실제 증명서가 아니며 효력이 없습니다."


def start(name: str) -> canvas.Canvas:
    c = canvas.Canvas(str(HERE / name), pagesize=A4)
    c.setTitle("ProofBridge 합성 샘플")
    return c


def finish(c: canvas.Canvas) -> None:
    c.setFont(FONT, 8)
    c.setFillGray(0.45)
    c.drawCentredString(W / 2, 28, FOOTER)
    c.setFillGray(0)
    c.save()


def line(c: canvas.Canvas, x: float, y: float, text: str, size: int = 10) -> None:
    c.setFont(FONT, size)
    c.drawString(x, y, text)


def make_resident_copy() -> str:
    """주민등록표 등본 (합성). 제목을 크게 인쇄해 글자 크기 기반 제목 검출을 태운다."""
    name = "합성_주민등록표등본.pdf"
    c = start(name)

    c.setFont(FONT, 22)
    c.drawCentredString(W / 2, H - 90, "주 민 등 록 표 ( 등 본 )")

    line(c, 60, H - 130, "행정안전부 · 정부24", 11)
    line(c, 60, H - 150, "문서확인번호 : 0000-0000-0000-0000")
    line(c, 60, H - 168, "발급일자 : 2026-08-19")

    line(c, 60, H - 205, "세대주 성명 : 홍길동        세대주와의 관계 : 본인", 11)
    line(c, 60, H - 225, "주소 : 서울특별시 예시구 예시로 000, 000동 000호")
    line(c, 60, H - 243, "전입일 : 2024-03-02        변동사유 : 전입")

    line(c, 60, H - 280, "세대원", 12)
    for i, (nm, rel) in enumerate([("김영희", "배우자"), ("홍길순", "자녀")]):
        line(c, 70, H - 302 - i * 18, f"{nm}    {rel}    주민등록번호 000000-0000000")

    line(c, 60, H - 380, "위 기재사항은 주민등록표의 내용과 틀림없음을 증명합니다.", 11)
    line(c, 60, H - 410, "서울특별시 예시구청장", 13)
    finish(c)
    return name


def make_utility_bill() -> str:
    """전기요금 청구서 (합성). 현재 우리 업무 정의에서 '필수'인데 실물이 없던 종류다."""
    name = "합성_전기요금청구서.pdf"
    c = start(name)

    c.setFont(FONT, 20)
    c.drawCentredString(W / 2, H - 90, "전기 요금 청구서")

    line(c, 60, H - 130, "한국전력공사", 12)
    line(c, 60, H - 155, "고객번호 : 0000-0000-0000")
    line(c, 60, H - 173, "고객명 : 홍길동")
    line(c, 60, H - 191, "사용장소 : 서울특별시 예시구 예시로 000, 000동 000호")

    line(c, 60, H - 230, "청구일 : 2026-08-05", 11)
    line(c, 60, H - 250, "납부기한 : 2026-08-31")
    line(c, 60, H - 270, "청구금액 : 43,120 원", 13)

    line(c, 60, H - 310, "사용기간 : 2026-07-01 ~ 2026-07-31", 11)
    line(c, 60, H - 330, "사용량 : 245 kWh")
    line(c, 60, H - 350, "납부계좌 : 예시은행 000-0000-0000-00 (예금주 한국전력공사)")
    finish(c)
    return name


def make_employment_certificate() -> str:
    """재직증명서 (합성). 사문서라 현재 시그니처로 잘 안 잡히는 대표 사례다."""
    name = "합성_재직증명서.pdf"
    c = start(name)

    c.setFont(FONT, 20)
    c.drawCentredString(W / 2, H - 95, "재 직 증 명 서")

    line(c, 60, H - 150, "성명 : 홍길동", 11)
    line(c, 60, H - 170, "생년월일 : 1990-01-01")
    line(c, 60, H - 190, "소속 : 개발본부 플랫폼팀")
    line(c, 60, H - 210, "직위 : 선임연구원")
    line(c, 60, H - 230, "재직기간 : 2023-03-02 ~ 현재")
    line(c, 60, H - 250, "담당업무 : 백엔드 개발")

    line(c, 60, H - 300, "위와 같이 재직하고 있음을 증명합니다.", 12)
    line(c, 60, H - 340, "발급일 : 2026-08-19", 11)
    line(c, 60, H - 375, "주식회사 예시  대표이사 (인)", 13)
    finish(c)
    return name


def main() -> int:
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    made = [make_resident_copy(), make_utility_bill(), make_employment_certificate()]
    for name in made:
        size = (HERE / name).stat().st_size
        print(f"  {name}  ({size:,} bytes)")
    print(f"\n{len(made)}개 생성. 전부 합성 데이터이며 커밋해도 된다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
