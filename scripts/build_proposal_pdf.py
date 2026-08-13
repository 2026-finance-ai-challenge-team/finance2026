from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "output/pdf/proofbridge-project-proposal.pdf"

INK = colors.HexColor("#102F43")
MINT = colors.HexColor("#B8E8D5")
MINT_DARK = colors.HexColor("#287A67")
CORAL = colors.HexColor("#F5795B")
LEMON = colors.HexColor("#F6D86B")
SKY = colors.HexColor("#CBE7F4")
MIST = colors.HexColor("#F5F7F2")
WHITE = colors.white
GREY = colors.HexColor("#506674")
LINE = colors.HexColor("#CCD8DC")


def register_fonts() -> None:
    fonts = Path("C:/Windows/Fonts")
    regular = fonts / "malgun.ttf"
    bold = fonts / "malgunbd.ttf"
    if not regular.exists() or not bold.exists():
        raise SystemExit("맑은 고딕 글꼴을 찾을 수 없습니다.")
    pdfmetrics.registerFont(TTFont("Malgun", str(regular)))
    pdfmetrics.registerFont(TTFont("MalgunBold", str(bold)))
    pdfmetrics.registerFontFamily("Malgun", normal="Malgun", bold="MalgunBold")


register_fonts()
styles = getSampleStyleSheet()


def style(name: str, **kwargs) -> ParagraphStyle:
    defaults = {
        "fontName": "Malgun",
        "fontSize": 9.2,
        "leading": 14,
        "textColor": INK,
        "wordWrap": "CJK",
        "spaceAfter": 4,
    }
    defaults.update(kwargs)
    return ParagraphStyle(name, **defaults)


S = {
    "cover_kicker": style("cover_kicker", fontName="MalgunBold", fontSize=10, leading=14, textColor=MINT_DARK),
    "cover_title": style("cover_title", fontName="MalgunBold", fontSize=34, leading=39, textColor=INK),
    "cover_sub": style("cover_sub", fontName="MalgunBold", fontSize=15, leading=22, textColor=INK),
    "cover_copy": style("cover_copy", fontName="MalgunBold", fontSize=18, leading=26, textColor=CORAL),
    "h1": style("h1", fontName="MalgunBold", fontSize=19, leading=26, textColor=INK, spaceAfter=7),
    "h2": style("h2", fontName="MalgunBold", fontSize=11.5, leading=17, textColor=INK, spaceBefore=5, spaceAfter=4),
    "body": style("body"),
    "small": style("small", fontSize=7.8, leading=11.5, textColor=GREY),
    "tiny": style("tiny", fontSize=6.8, leading=9.4, textColor=GREY),
    "card_title": style("card_title", fontName="MalgunBold", fontSize=10, leading=14, textColor=INK),
    "table_head": style("table_head", fontName="MalgunBold", fontSize=8, leading=11, textColor=WHITE),
    "card_body": style("card_body", fontSize=8.2, leading=12.2, textColor=INK),
    "tag": style("tag", fontName="MalgunBold", fontSize=7.5, leading=10, textColor=INK, alignment=TA_CENTER),
    "quote": style("quote", fontName="MalgunBold", fontSize=12, leading=18, textColor=INK),
    "center": style("center", alignment=TA_CENTER),
}


def p(text: str, kind: str = "body") -> Paragraph:
    return Paragraph(text, S[kind])


def title(no: str, heading: str, lead: str) -> list:
    return [
        p(f"{no} / PROJECT PROPOSAL", "cover_kicker"),
        p(heading, "h1"),
        p(lead, "body"),
        Spacer(1, 4 * mm),
    ]


def tag(label: str, text: str, color=MINT) -> Table:
    table = Table(
        [[p(label, "tag"), p(text, "card_body")]],
        colWidths=[25 * mm, 142 * mm],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), color),
                ("BACKGROUND", (1, 0), (1, 0), WHITE),
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def cards(items: list[tuple[str, str, colors.Color]], widths=None) -> Table:
    widths = widths or [55.5 * mm] * len(items)
    data = [[p(a, "card_title") for a, _, _ in items], [p(b, "card_body") for _, b, _ in items]]
    table = Table(data, colWidths=widths, hAlign="LEFT")
    commands = [
        ("BOX", (0, 0), (-1, -1), 0.7, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]
    for index, (_, _, color) in enumerate(items):
        commands.append(("BACKGROUND", (index, 0), (index, 0), color))
        commands.append(("BACKGROUND", (index, 1), (index, 1), WHITE))
    table.setStyle(TableStyle(commands))
    return table


def matrix(rows: list[list[str]], widths: list[float], font_size=7.5) -> Table:
    data = [[p(cell, "table_head" if row_index == 0 else "small") for cell in row] for row_index, row in enumerate(rows)]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "MalgunBold"),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, MIST]),
                ("GRID", (0, 0), (-1, -1), 0.45, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def flow(items: list[str]) -> Table:
    row = []
    widths = []
    for index, item in enumerate(items):
        row.append(p(item, "tag"))
        widths.append(29 * mm)
        if index < len(items) - 1:
            row.append(p("→", "center"))
            widths.append(6 * mm)
    table = Table([row], colWidths=widths, hAlign="LEFT")
    commands = [("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    for index in range(0, len(row), 2):
        commands.extend(
            [
                ("BACKGROUND", (index, 0), (index, 0), SKY if index % 4 == 0 else MINT),
                ("BOX", (index, 0), (index, 0), 0.6, LINE),
                ("TOPPADDING", (index, 0), (index, 0), 8),
                ("BOTTOMPADDING", (index, 0), (index, 0), 8),
            ]
        )
    table.setStyle(TableStyle(commands))
    return table


def page_frame(canvas, doc) -> None:
    page = canvas.getPageNumber()
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(MIST)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    canvas.setFillColor(INK)
    canvas.rect(0, height - 10 * mm, width, 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(MINT)
    canvas.circle(15 * mm, height - 5 * mm, 2 * mm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("MalgunBold", 7.5)
    canvas.drawString(22 * mm, height - 6.8 * mm, "ProofBridge · 2026 금융 AI Challenge")
    canvas.setFillColor(GREY)
    canvas.setFont("Malgun", 7)
    canvas.drawRightString(width - 15 * mm, 9 * mm, f"{page:02d}  |  2026-08-12")
    canvas.setStrokeColor(CORAL)
    canvas.setLineWidth(2.2)
    canvas.line(15 * mm, 14 * mm, 36 * mm, 14 * mm)
    canvas.restoreState()


story = []

# 1. Cover
story += [
    Spacer(1, 24 * mm),
    p("FINANCIAL PAPERWORK COMPLETION LAYER", "cover_kicker"),
    Spacer(1, 3 * mm),
    p("ProofBridge", "cover_title"),
    p("서류를 아는 사람만 통과하는 금융업무를 없애는 준비 완성 계층", "cover_sub"),
    Spacer(1, 10 * mm),
    p("“모르면 그냥 다 넣으세요. 필요한 것만 챙겨드릴게요.”", "cover_copy"),
    Spacer(1, 10 * mm),
    tag("전략 판단", "공공 마이데이터를 대체하지 않고, 공공 경로와 남은 증빙을 합쳐 실제 제출 직전까지 완성하는 Banking Task Completion Layer다.", LEMON),
    Spacer(1, 7 * mm),
    cards(
        [
            ("공공 증빙", "공식 동의·제출 경로를 먼저 안내한다.", SKY),
            ("사용자 파일", "AI가 사문서·사진의 종류와 핵심 필드를 이해한다.", MINT),
            ("준비 완료 키트", "규칙이 디지털·인쇄·방문 실행 순서를 만든다.", LEMON),
        ]
    ),
    Spacer(1, 8 * mm),
    p("첫 완주 업무", "h2"),
    p("금융거래 목적 증빙 및 한도제한계좌 해제 준비 · KB국민은행 / 우리은행 / 카카오뱅크 공개 기준을 단계적으로 검증", "body"),
    Spacer(1, 6 * mm),
    p("제안서 상태: 공개 조사 기반 방향성 + 클릭 가능한 합성 데모. 실제 OCR·공공 마이데이터 연동·은행 자동 제출은 아직 구현하지 않았다.", "small"),
    PageBreak(),
]

# 2. Problem
story += title("01", "서류 발급보다 ‘판단과 조립’이 어렵다", "사용자는 버튼 위치보다 내가 가진 파일이 무엇인지, 이번 업무에 인정되는지, 빠진 것은 무엇인지에서 막힌다.")
story += [
    tag("확인 사실", "금융위원회는 증빙 안내 부족으로 영업점을 반복 방문하는 문제, 전업주부·금융취약계층의 객관적 증빙 곤란, 공공 마이데이터를 통한 실물서류 최소화를 공식적으로 제시했다. [S1]", SKY),
    Spacer(1, 5 * mm),
    p("사용자가 겪는 다섯 번의 멈춤", "h2"),
    cards(
        [
            ("① 이름을 모름", "파일이 어떤 서류인지 설명하기 어렵다.", SKY),
            ("② 조건을 모름", "필수·조건부·대체 관계를 해석하지 못한다.", MINT),
            ("③ 상태를 모름", "발급일·명의·주소 불일치를 놓친다.", LEMON),
        ]
    ),
    Spacer(1, 3 * mm),
    cards(
        [
            ("④ 채널을 모름", "앱·전자지갑·출력·영업점 경로가 분리돼 있다.", SKY),
            ("⑤ 실패 비용", "한 장 누락이 재방문과 심사 지연으로 이어진다.", colors.HexColor("#FFD4C8")),
        ],
        widths=[83.5 * mm, 83.5 * mm],
    ),
    Spacer(1, 6 * mm),
    p("기존 안내의 경계", "h2"),
    matrix(
        [
            ["공식 근거", "확인된 현재 흐름", "남는 공백"],
            ["KB국민은행 [S6]", "목적별 증빙 예시와 추가 자료 가능성", "사용자가 자기 파일을 예시와 대조해야 함"],
            ["카카오뱅크 [S7]", "앱 제출, 일부 원본 출력·촬영, 심사 대기", "제출 전 원본·형식·조합 검증"],
            ["공공 마이데이터 [S2]", "동의 기반 행정정보 제공", "사문서·사진·현장 지참물"],
        ],
        [36 * mm, 63 * mm, 68 * mm],
    ),
    Spacer(1, 6 * mm),
    tag("전략 판단", "안내 페이지를 하나 더 만드는 것이 아니라, 뒤섞인 자료에서 출발해 사용자의 다음 행동과 제출 채널까지 완성해야 한다.", LEMON),
    PageBreak(),
]

# 3. Users
story += title("02", "대상은 나이가 아니라 금융업무 경험의 공백", "청년·고령층·주부·외국인 거주자는 서로 다르지만 ‘무엇을 질문해야 하는지 모른다’는 공통 문제가 있다.")
story += [
    p("핵심 사용자 정의", "h2"),
    tag("전략 판단", "금융업무의 목적은 알지만 필요한 서류명·조건·제출 채널을 스스로 설명하지 못하는 사용자", MINT),
    Spacer(1, 6 * mm),
    matrix(
        [
            ["경험 공백", "대표 사용자", "ProofBridge가 줄일 판단"],
            ["첫 금융업무", "청소년·청년·첫 취업자", "용어 대신 목적부터 선택"],
            ["가구 업무 대행", "주부·보호자·가족 돌봄자", "명의·주소·기간 교차 확인"],
            ["디지털 채널 비숙련", "고령층", "한 화면 한 결정, 큰 글자"],
            ["한국 제도 비숙련", "외국인 거주자", "쉬운 문장과 공식 경로"],
            ["예외 상황", "프리랜서·소상공인", "조건부·대체 자료 설명"],
        ],
        [46 * mm, 53 * mm, 68 * mm],
    ),
    Spacer(1, 7 * mm),
    p("사용자가 고용하는 일", "h2"),
    tag("JTBD", "“서류명을 모를 때 내가 가진 것을 한꺼번에 보여주면, 쓸 수 있는 것과 부족한 것을 구분하고 끝내는 방법까지 알려달라.”", LEMON),
    Spacer(1, 7 * mm),
    p("접근성은 부가기능이 아니다", "h2"),
    cards(
        [
            ("읽기", "큰 기본 글자, 충분한 대비, 쉬운 한국어", SKY),
            ("조작", "키보드 탐색, 큰 클릭 영역, 한 단계 한 행동", MINT),
            ("회복", "오류 이유와 복구 방법, 낮은 신뢰도 확인", LEMON),
        ]
    ),
    Spacer(1, 6 * mm),
    p("현재 데모에는 큰 글자 전환, 명확한 포커스, 합성 샘플 고지, 상태를 색상과 텍스트로 함께 구분하는 기본 접근성을 반영했다.", "small"),
    PageBreak(),
]

# 4. Differentiation
story += title("03", "차별점은 기술 하나가 아니라 ‘마지막 공백’의 결합", "공공 인프라·은행 앱·OCR은 이미 존재한다. ProofBridge는 이 기능을 사용자 쪽에서 하나의 완료 흐름으로 조정한다.")
story += [
    matrix(
        [
            ["공개 서비스", "공공 경로", "파일 이해", "업무 규칙", "완료 산출물"],
            ["공공 마이데이터", "●", "—", "업무 범위", "공식 데이터 제출"],
            ["정부24 전자증명서", "●", "—", "—", "증명서 전송"],
            ["은행·증권사 앱", "부분", "—", "자사 범위", "자사 제출·심사"],
            ["OCR·Document AI", "—", "●", "—", "텍스트·필드"],
            ["해외 패킷 서비스", "—", "부분", "해당 업무", "제출 패키지"],
            ["ProofBridge 계획", "공식 안내", "●", "출처 기반", "디지털·인쇄·방문"],
        ],
        [43 * mm, 26 * mm, 27 * mm, 31 * mm, 40 * mm],
    ),
    Spacer(1, 7 * mm),
    tag("확인 사실", "한화투자증권은 공공 마이데이터 기반 출금한도 제한 해제를, 신한은행은 고령층·디지털 취약계층을 고려한 영업점 서류 간소화를 이미 제공한다. [S4][S5]", SKY),
    Spacer(1, 4 * mm),
    tag("전략 판단", "공개 조사 범위에서 확인한 공백은 ‘공공 제출 대상 + 사용자의 사문서 + 현장 지참물’을 한 준비 상태로 계산하고 실행 키트로 만드는 한국 소비자 흐름이다.", LEMON),
    Spacer(1, 7 * mm),
    p("정직한 포지셔닝", "h2"),
    cards(
        [
            ("말할 수 있음", "한국 생활금융에 특화된 소비자용 증빙 완성 흐름\n공공 마이데이터 위의 업무 완성 계층", MINT),
            ("말하지 않음", "세계·국내 최초\n100% 승인·자동 해제\n전 은행 실시간 지원", colors.HexColor("#FFD4C8")),
        ],
        widths=[83.5 * mm, 83.5 * mm],
    ),
    Spacer(1, 7 * mm),
    p("조사 한계", "h2"),
    p("2026-08-12 공개 자료에서 동일한 전체 결합 흐름은 확인하지 못했다. 이는 시장 전체의 부재, 특허 가능성 또는 자유실시를 증명하지 않는다. 상용화 전에는 KIPRIS 청구항 단위 검토가 별도로 필요하다.", "small"),
    PageBreak(),
]

# 5. Public MyData
story += title("04", "공공 마이데이터를 흡수하는 법: 다시 받지 말고 먼저 보낸다", "공공 증빙은 공식 경로로, 남은 자료만 ProofBridge로 처리하는 것이 서비스 경계이자 신뢰 설계다.")
story += [
    flow(["업무·조건 선택", "공공 대상 분리", "공식 경로 안내", "남은 파일 분석", "전체 상태 계산"]),
    Spacer(1, 7 * mm),
    cards(
        [
            ("공공 경로", "공공 마이데이터·전자문서지갑에서 보내야 할 자료와 실행 순서", SKY),
            ("사용자 보완", "관리비 고지서·근로계약서·사진 등 남은 사문서", MINT),
            ("현장 지참", "신분증·원본·서명·출력 부수와 창구 요청 문장", LEMON),
        ]
    ),
    Spacer(1, 7 * mm),
    p("연동 단계", "h2"),
    matrix(
        [
            ["단계", "ProofBridge 범위", "표시 방식"],
            ["현재 데모", "대상 여부·공식 링크·확인일 스냅샷", "실제 전송이 아님을 명시"],
            ["MVP", "지원 업무의 공식 경로 안내와 전체 상태 합산", "지원 범위에 한정"],
            ["승인 후", "이용기관 신청·테스트·동의·전송 연동", "승인 완료 후에만 활성화"],
        ],
        [35 * mm, 78 * mm, 54 * mm],
    ),
    Spacer(1, 7 * mm),
    tag("확인 사실", "공공 마이데이터 실제 연계는 단순 API 키 발급이 아니다. 신청서, 환경조사, 현장실사, 심의와 승인 절차가 있으며 신청일부터 3개월 이내 결과를 통보한다. [S8]", SKY),
    Spacer(1, 4 * mm),
    tag("구현 계획", "이용기관 승인을 받기 전 MVP는 정부24·공공 마이데이터의 공식 이용 경로를 안내하고, 실제 동의·전송처럼 보이는 UI를 만들지 않는다.", LEMON),
    PageBreak(),
]

# 6. AI and rules
story += title("05", "AI는 문서를 이해하고, 규칙은 준비 완료를 판정한다", "비정형 입력의 장점은 AI로 얻되, 금융업무 판정은 공식 출처가 붙은 버전형 규칙으로 통제한다.")
story += [
    flow(["파일 검증", "텍스트 우선", "필요 페이지만 OCR", "필드 확인", "규칙 판정"]),
    Spacer(1, 7 * mm),
    matrix(
        [
            ["AI가 맡는 일", "규칙이 맡는 일"],
            ["PDF·사진의 문서 종류 분류", "필수·조건부·대체 서류 관계"],
            ["발급기관·명의·발급일·주소 추출", "유효기간·교차 필드·허용 형식"],
            ["낮은 신뢰도 확인 질문", "다섯 상태와 공식 근거 연결"],
            ["근거가 주어진 결과의 쉬운 설명", "근거가 없으면 확인 필요로 실패 안전 처리"],
        ],
        [83.5 * mm, 83.5 * mm],
    ),
    Spacer(1, 7 * mm),
    p("다섯 가지 사용자 상태", "h2"),
    cards(
        [
            ("준비 완료", "공개 기준에서 사용할 수 있음", MINT),
            ("추가 필요", "필수·조건부 자료가 없음", LEMON),
            ("정보 불일치", "이름·주소·기간 확인 필요", colors.HexColor("#FFD4C8")),
        ]
    ),
    Spacer(1, 3 * mm),
    cards(
        [
            ("기한 만료", "공식 유효기간 규칙을 충족하지 못함", SKY),
            ("이번에는 불필요", "인식했지만 제출 묶음에서 제외", MIST),
        ],
        widths=[83.5 * mm, 83.5 * mm],
    ),
    Spacer(1, 7 * mm),
    tag("안전 원칙", "LLM은 ‘준비 완료’를 자유 추론하지 않는다. 현재 데모는 합성 샘플의 사전 계산 결과이며 실제 AI 분석으로 위장하지 않는다.", LEMON),
    PageBreak(),
]

# 7. Demo
story += title("06", "클릭 데모: 한 개의 골든 시나리오로 전체 흐름을 보인다", "폭넓은 가짜 기능보다 공공·사문서·현장 요건이 섞인 한 사례를 처음부터 끝까지 설명한다.")
story += [
    p("합성 시나리오", "h2"),
    tag("현재 데모", "카카오뱅크 한도계좌 · 생활비/공과금 목적 · 주민등록등본 + 관리비 고지서 + 무관 문서", MINT),
    Spacer(1, 6 * mm),
    matrix(
        [
            ["단계", "사용자가 보는 것", "데모 상태"],
            ["1. 업무 선택", "은행·목적·사용자 조건", "클릭 가능"],
            ["2. 준비물 분리", "공공 경로 / 직접 준비 / 현장 지참", "클릭 가능"],
            ["3. 샘플 투입", "실제 업로드가 아닌 합성 샘플 고지", "클릭 가능"],
            ["4. 결과", "준비·추가·불일치·불필요 상태와 근거", "클릭 가능"],
            ["5. 키트", "공공·디지털·인쇄·방문 탭", "미리보기"],
        ],
        [32 * mm, 93 * mm, 42 * mm],
    ),
    Spacer(1, 7 * mm),
    p("보이는 차별점", "h2"),
    cards(
        [
            ("경쟁이 아닌 연결", "등본은 공식 경로로 보내고 관리비 고지서만 보완한다.", SKY),
            ("판정 이유", "주소가 다르면 어느 필드를 확인해야 하는지 보여준다.", MINT),
            ("다음 행동", "출력·촬영·원본 지참 순서를 채널별로 나눈다.", LEMON),
        ]
    ),
    Spacer(1, 7 * mm),
    p("현재 데모와 MVP 목표의 경계", "h2"),
    p("현재는 합성 데이터 기반 프론트엔드 청사진이다. 실제 파일 업로드·OCR·규칙 데이터·ZIP·삭제·FIN MAP은 합성 정답표와 보안 경로를 먼저 만든 뒤 순차 연결한다. 구현되지 않은 기능은 화면에서 ‘연결 예정’으로 표시한다.", "small"),
    PageBreak(),
]

# 8. Trust
story += title("07", "가장 위험한 실패는 부족한 서류를 ‘준비 완료’라고 말하는 것", "전체 정확도보다 거짓 준비 완료율, 누락 탐지, 출처 연결과 삭제 성공을 우선한다.")
story += [
    cards(
        [
            ("결정 안전성", "고정 합성 회귀 세트에서 거짓 준비 완료 0건을 내부 통과선으로 삼는다.", colors.HexColor("#FFD4C8")),
            ("설명 가능성", "모든 규칙 항목에 공식 URL·기준일·마지막 확인일을 붙인다.", SKY),
            ("개인정보", "원본보다 최소 필드를 처리하고 즉시 삭제 결과를 확인한다.", MINT),
        ]
    ),
    Spacer(1, 7 * mm),
    matrix(
        [
            ["검증 지표", "우선 확인할 실패", "MVP 증거"],
            ["거짓 준비 완료율", "누락인데 완료로 표시", "합성 누락 세트 회귀"],
            ["누락 탐지 재현율", "필수 자료를 놓침", "은행·목적별 정답표"],
            ["근거 연결률", "출처·기준일 없는 판정", "규칙 스키마 검사"],
            ["원본 불변성", "문서 내용·전자서명 변경", "입출력 해시 대조"],
            ["삭제 성공률", "원본·파생 데이터 잔존", "즉시 삭제 통합 검사"],
            ["무설명 완주율", "심사자가 흐름을 이탈", "외부 브라우저 사용성 검사"],
        ],
        [44 * mm, 63 * mm, 60 * mm],
    ),
    Spacer(1, 7 * mm),
    p("개인정보 최소 원칙", "h2"),
    p("비회원 일회성 세션 · 주민번호 뒷자리와 계좌번호 마스킹 · 원문 로그 금지 · 실제 개인정보 대신 합성 샘플 · 외부 AI에는 최소 필드만 전달 · 사용자 즉시 삭제와 세션 종료 삭제", "body"),
    Spacer(1, 5 * mm),
    tag("공식 기준", "개인정보보호위원회 생성형 AI 개인정보 처리 안내서를 기준으로 목적 제한, 투명성, 안전조치와 데이터 최소화를 검토한다. [S12]", SKY),
    PageBreak(),
]

# 9. Roadmap
story += title("08", "9월 7일에는 ‘보이는 청사진’이 아니라 재현 가능한 한 경로를 제출한다", "프론트엔드 흐름을 먼저 고정하고, 합성 정답표·규칙·OCR·삭제를 가장 작은 순서로 연결한다.")
story += [
    matrix(
        [
            ["내부 시점", "완료 기준"],
            ["8/12–8/18", "클릭 데모·제안서·공식 규칙 출처 목록"],
            ["8/19–8/25", "합성 샘플·정답표·업로드→판정→키트 골든 경로"],
            ["8/26–8/31", "선택 OCR·규칙 v1·삭제·접근성, 기능 동결"],
            ["9/1–9/2", "전체 회귀와 설명 없는 사용자 완주 검증"],
            ["9/3–9/4", "기획서·기능명세서 PDF 동결"],
            ["9/5–9/6", "운영 배포 동결, 외부망·비로그인 제출 리허설"],
            ["9/7 09:00", "공식 10:00 마감보다 1시간 앞서 제출"],
        ],
        [41 * mm, 126 * mm],
    ),
    Spacer(1, 7 * mm),
    p("대회 적합성", "h2"),
    cards(
        [
            ("금융 현안", "증빙 정보 비대칭과 반복 방문", SKY),
            ("AI 필요성", "비정형 PDF·사진 이해", MINT),
            ("안전한 판정", "출처 기반 규칙과 실패 안전", LEMON),
        ]
    ),
    Spacer(1, 3 * mm),
    cards(
        [
            ("혼합 채널", "웹·은행 앱·전자지갑·영업점", SKY),
            ("심사 재현", "로그인 없는 합성 샘플 경로", MINT),
        ],
        widths=[83.5 * mm, 83.5 * mm],
    ),
    Spacer(1, 7 * mm),
    tag("확인 사실", "예선 필수 산출물은 공모전 기획서 PDF, 기능명세서 PDF, 실행 가능한 웹서비스 URL이며 2026-09-07 10:00까지 제출해야 한다. [S13]", SKY),
    Spacer(1, 4 * mm),
    p("기능명세서에는 미래상이 아니라 외부 환경에서 실제로 재현되는 현재 기능만 적는다.", "small"),
    PageBreak(),
]

# 10. APIs and sources
story += title("09", "API 가입 체크리스트: 데모는 키 없이, 실제 연결은 하나씩", "복수 공급자를 동시에 붙이지 않는다. 금융 규칙과 합성 정답표가 먼저 통과한 뒤 필요한 키만 만든다.")
story += [
    matrix(
        [
            ["시점", "서비스", "목적·발급 방식"],
            ["지금", "FIN MAP", "지점·ATM / 개발자 가입·서비스 신청·Client ID/Secret"],
            ["지금", "Kakao Local", "인쇄소 위치 / 앱 생성·REST API 키"],
            ["OCR 검증", "CLOVA OCR", "한국어 스캔 페이지만 / Domain·Invoke URL·Secret"],
            ["설명 품질 검증", "LLM 하나", "마스킹 필드 설명 / 서버 전용 프로젝트 키"],
            ["별도 승인", "공공 마이데이터", "이용기관 신청·환경조사·현장실사·심의"],
            ["제외", "AWS Textract", "공식 지원 언어에 한국어 없음"],
        ],
        [31 * mm, 42 * mm, 94 * mm],
    ),
    Spacer(1, 5 * mm),
    p("공식 출처", "h2"),
    p("[S1] 금융위원회 한도제한계좌 개선 · https://www.fsc.go.kr/po010101/82205", "tiny"),
    p("[S2] 공공 마이데이터 소개 · https://www.mydata.go.kr/pc/intro/serviceIntro.do?tab=tab_3&type=A", "tiny"),
    p("[S3] 정부 전자증명서 안내 · https://plus.gov.kr/portal/custcntr/utztngd/elprdocgd", "tiny"),
    p("[S4] 한화투자증권 공공 마이데이터 한도 해제 · https://m.hanwhawm.com:9090/main/bbs/indexView.cmd?nn_id=47761", "tiny"),
    p("[S5] 신한은행 영업점 공공 마이데이터 · https://www.shinhangroup.com/kr/archive/business/detail/355", "tiny"),
    p("[S6] KB국민은행 금융거래 목적 확인 · https://obank.kbstar.com/quics?articleId=134693", "tiny"),
    p("[S7] 카카오뱅크 한도계좌 안내 · https://blog.kakaobank.com/posts/service-limit-account", "tiny"),
    p("[S8] 공공 마이데이터 이용기관 신청 · https://adm.mydata.go.kr/intro/addHelpPage.do?type=index", "tiny"),
    p("[S9] FIN MAP · https://developers.kftc.or.kr/dev/openapi/map/all", "tiny"),
    p("[S10] Kakao Local · https://developers.kakao.com/docs/latest/ko/local/dev-guide", "tiny"),
    p("[S11] CLOVA OCR · https://guide.ncloud-docs.com/docs/clovaocr-start", "tiny"),
    p("[S12] 개인정보보호위원회 생성형 AI 안내서 · https://m.pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS217&nttId=11439", "tiny"),
    p("[S13] 2026 금융 AI Challenge · https://daker.ai/public/hackathons/2026-finance-ai-challenge", "tiny"),
    Spacer(1, 5 * mm),
    tag("다음 한 걸음", "FIN MAP 운영조건을 문의하고, 합성 금융문서 1세트로 CLOVA OCR 정확도·비용·삭제 조건을 검증한다. LLM과 공공 마이데이터 실제 연계는 그 뒤다.", LEMON),
]


def build() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=21 * mm,
        rightMargin=21 * mm,
        topMargin=19 * mm,
        bottomMargin=18 * mm,
        title="ProofBridge 프로젝트 제안서",
        author="Team ProofBridge",
        subject="2026 금융 AI Challenge",
    )
    doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    print(OUTPUT)


if __name__ == "__main__":
    build()
