"""합성 법인서류 PDF와 `labels.csv`를 만든다.

대상 조합은 하나은행 / 법인계좌 개설 / 대면 / 본인 하나뿐이다.
여기서 만드는 건 전부 가짜 법인·가짜 번호다. 실물 서류를 넣지 않는다.

분류 모듈은 문서 종류만 정하고 내용 필드는 뽑지 않는다. 그래서 `labels.csv`에도
명의·주소·금액을 적지 않고 `expected_doc_type`과 `expected_relevance`만 남긴다.

    python generate.py                 # 오늘 기준
    python generate.py --as-of 2026-09-01
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
SAMPLE_DIR = BASE_DIR / "samples"
LABELS_CSV = BASE_DIR / "labels.csv"
MANIFEST = SAMPLE_DIR / "_generation.json"

# 분류 모듈이 찾는 문자열. 렌더 후 실제 추출 텍스트에 있는지 확인한다.
ANCHORS: dict[str, tuple[str, ...]] = {
    "business_registration_certificate": ("사업자등록증", "사업자등록번호", "상호", "대표자"),
    "business_registration_verification": ("사업자등록증명", "사업자등록번호", "상호", "대표자"),
    "corporate_registry_certificate": ("등기사항전부증명서", "법인등록번호", "상호", "본점"),
    "corporate_seal_certificate": ("인감증명서", "법인등록번호", "상호", "인감"),
    "power_of_attorney": ("위임장", "위임인", "수임인", "위임사항"),
    "shareholder_registry": ("주주명부", "주주", "주식수"),
    "share_change_statement": ("주식등변동상황명세서", "사업연도", "주주", "주식수"),
    "articles_of_incorporation": ("정관", "총칙", "목적", "상호"),
    "vat_tax_base_certificate": ("부가가치세과세표준증명", "사업자등록번호", "과세기간", "과세표준"),
    "standard_financial_statement_certificate": ("표준재무제표증명", "사업자등록번호", "사업연도", "재무제표"),
}

# 실물 서식에 그 문자열이 그대로 없는 앵커. 억지로 넣으면 없는 서식을 만들어내는 셈이라
# 생성은 실물대로 두고, 대신 DB 쪽에 고칠 거리로 보고한다.
KNOWN_ANCHOR_GAPS: dict[tuple[str, str], str] = {
    ("corporate_registry_certificate", "법인등록번호"): "등기사항전부증명서 표기는 `등록번호`다",
}

# 가상의 법인 하나로 통일한다. 교차 확인 필드가 문서마다 어긋나면 그건 별개의 시나리오다.
COMPANY = {
    "corp_name": "주식회사 한빛물류",
    "ceo": "김민준",
    "ceo_rrn": "900101-1******",
    "biz_no": "123-45-67890",
    "corp_no": "110111-1234567",
    "hq_addr": "서울특별시 강서구 마곡중앙로 99, 3층 301호",
    "biz_type": "운수업",
    "biz_item": "화물운송 주선업",
    "tax_office": "강서세무서장",
    "registry_office": "서울중앙지방법원 등기국",
    "registry_no": "018342",
    "branch": "마곡나루",
    "agent": "이서준",
    "agent_birth": "1993. 4. 2.",
}


def dot(d: date) -> str:
    return f"{d.year}. {d.month}. {d.day}."


def ko(d: date) -> str:
    return f"{d.year}년 {d.month}월 {d.day}일"


def dash(d: date) -> str:
    return d.isoformat()


def build_docs(as_of: date) -> list[dict]:
    """생성할 문서 목록. 날짜는 전부 기준일에서 역산해 정답표가 시간에 안 썩게 한다."""
    ago = lambda n: as_of - timedelta(days=n)  # noqa: E731

    registry_fresh = {
        "issued_dot": dot(ago(18)),
        "moved_dot": dot(date(2023, 5, 11)),
        "moved_reg_dot": dot(date(2023, 5, 19)),
        "capital_dot": dot(date(2024, 2, 6)),
        "capital_reg_dot": dot(date(2024, 2, 14)),
        "issue_no": "7200-AAPZ-BYSY",
    }

    return [
        {
            "file": "사업자등록증.pdf",
            "doc_type": "business_registration_certificate",
            "template": "business_registration_certificate.html",
            "context": {
                "doc_title": "사업자등록증",
                "opened_ko": ko(date(2022, 3, 2)),
                "issued_ko": ko(ago(410)),  # 사업자등록증은 재발급 전까지 갱신되지 않는다
            },
        },
        {
            "file": "사업자등록증명.pdf",
            "doc_type": "business_registration_verification",
            "template": "business_registration_verification.html",
            "context": {
                "doc_title": "사업자등록증명",
                "opened_dot": dot(date(2022, 3, 2)),
                "registered_dot": dot(date(2022, 3, 11)),
                "issued_dot": dot(ago(9)),
                "issue_no": "8336-536-3629-975",
                "receipt_no": "503023892290",
            },
        },
        {
            "file": "법인등기부.pdf",
            "doc_type": "corporate_registry_certificate",
            "template": "corporate_registry_certificate.html",
            "context": {"doc_title": "등기사항전부증명서", **registry_fresh},
        },
        {
            # 기한 만료 케이스. issued_within_days가 무엇이든 1년이면 걸려야 한다.
            "file": "법인등기부_기한만료.pdf",
            "doc_type": "corporate_registry_certificate",
            "template": "corporate_registry_certificate.html",
            "context": {
                "doc_title": "등기사항전부증명서",
                **registry_fresh,
                "issued_dot": dot(ago(365)),
                "issue_no": "5108-QWNR-KZTD",
            },
        },
        {
            "file": "법인인감증명서.pdf",
            "doc_type": "corporate_seal_certificate",
            "template": "corporate_seal_certificate.html",
            "context": {
                "doc_title": "인감증명서",
                "issued_ko": ko(ago(14)),
                "issue_no": "OAYK-WUKX-ICG5",
            },
        },
        {
            "file": "위임장.pdf",
            "doc_type": "power_of_attorney",
            "template": "power_of_attorney.html",
            "context": {
                "doc_title": "위임장",
                "issued_ko": ko(ago(3)),
                "confirmed_ko": ko(ago(2)),
            },
        },
        {
            "file": "주주명부.pdf",
            "doc_type": "shareholder_registry",
            "template": "shareholder_registry.html",
            "context": {
                "doc_title": "주주명부",
                "issued_dash": dash(ago(26)),
                "basis_dash": dash(ago(31)),
            },
        },
        {
            "file": "주식등변동상황명세서.pdf",
            "doc_type": "share_change_statement",
            "template": "share_change_statement.html",
            "context": {
                "doc_title": "주식등변동상황명세서",
                "issued_dash": dash(ago(26)),
                "fy_start_dash": dash(date(as_of.year - 1, 1, 1)),
                "fy_end_dash": dash(date(as_of.year - 1, 12, 31)),
            },
        },
        {
            "file": "정관.pdf",
            "doc_type": "articles_of_incorporation",
            "template": "articles_of_incorporation.html",
            "context": {
                "doc_title": "정관",
                "founded_dash": dash(date(2022, 2, 25)),
                "issued_dash": dash(date(2024, 3, 29)),
            },
        },
        {
            "file": "부가가치세과세표준증명.pdf",
            "doc_type": "vat_tax_base_certificate",
            "template": "vat_tax_base_certificate.html",
            "context": {
                "doc_title": "부가가치세과세표준증명",
                "issued_ko": ko(ago(11)),
                "issue_no": "7816-481-2204-118",
                "receipt_no": "503504436440",
                "vat1_from": f"{as_of.year - 1}/01/01",
                "vat1_to": f"{as_of.year - 1}/12/31",
                "vat2_from": f"{as_of.year}/01/01",
                "vat2_to": f"{as_of.year}/06/30",
            },
        },
        {
            "file": "표준재무제표증명.pdf",
            "doc_type": "standard_financial_statement_certificate",
            "template": "standard_financial_statement_certificate.html",
            "context": {
                "doc_title": "표준재무제표증명",
                "issued_dot": dot(ago(11)),
                "filed_dot": dot(date(as_of.year, 3, 28)),
                "fy_start_dot": dot(date(as_of.year - 1, 1, 1)),
                "fy_end_dot": dot(date(as_of.year - 1, 12, 31)),
                "issue_no": "5121-092-8841-330",
            },
        },
        {
            # 함정 1 — 10종에 없는 문서. 법인인감증명서로 오인하면 안 되고,
            # 못 알아본 걸 '이번 업무에는 불필요'로 내보내도 안 된다.
            "file": "개인인감증명서.pdf",
            "doc_type": None,
            "template": "personal_seal_certificate.html",
            "context": {
                "doc_title": "인감증명서",
                "issued_ko": ko(ago(20)),
                "issue_no": "1180-3345-9021",
            },
        },
        {
            "file": "취업후기.pdf",  # 함정 2 — 증명서가 아닌 산문
            "doc_type": None,
            "template": "irrelevant_essay.html",
            "context": {"doc_title": "이직 후기"},
        },
        {
            "file": "빈페이지.pdf",  # 함정 3 — 내용 없는 1쪽
            "doc_type": None,
            "template": "blank_page.html",
            "context": {"doc_title": "빈 문서"},
        },
    ]


def render_all(docs: list[dict], out_dir: Path) -> None:
    from playwright.sync_api import sync_playwright

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), undefined=StrictUndefined)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        for doc in docs:
            html = env.get_template(doc["template"]).render(**COMPANY, **doc["context"])
            page.set_content(html, wait_until="load")
            page.pdf(path=str(out_dir / doc["file"]), format="A4", print_background=True)
            print(f"  {doc['file']}")
        browser.close()


def inspect(pdf_path: Path) -> dict:
    """추출 텍스트와 제목 후보(가장 큰 글자)의 크기·위치를 돌려준다."""
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        page = doc[0]
        height = page.rect.height
        spans = [
            span
            for block in page.get_text("dict")["blocks"]
            for line in block.get("lines", [])
            for span in line["spans"]
            if span["text"].strip()
        ]
        if not spans:
            return {"text": "", "title": None}

        sizes = sorted(s["size"] for s in spans)
        body_size = sizes[len(sizes) // 2]
        biggest = max(spans, key=lambda s: s["size"])
        return {
            "text": page.get_text(),
            "title": {
                "text": biggest["text"].strip(),
                "ratio": biggest["size"] / body_size,
                "top_pct": biggest["bbox"][1] / height * 100,
            },
        }


def verify(docs: list[dict], out_dir: Path) -> tuple[list[str], list[str]]:
    """생성물이 분류 모듈이 기대하는 모양인지 스스로 점검한다."""
    problems: list[str] = []
    gaps: list[str] = []
    for doc in docs:
        info = inspect(out_dir / doc["file"])
        doc_type = doc["doc_type"]
        if doc_type is None:
            continue

        for anchor in ANCHORS[doc_type]:
            if anchor in info["text"]:
                continue
            reason = KNOWN_ANCHOR_GAPS.get((doc_type, anchor))
            if reason:
                gaps.append(f"{doc_type} · {anchor} — {reason}")
            else:
                problems.append(f"{doc['file']} — 앵커 누락 {anchor!r}")

        title = info["title"]
        if title is None:
            problems.append(f"{doc['file']} — 텍스트 없음")
            continue
        if title["ratio"] < 1.5:
            problems.append(f"{doc['file']} — 제목이 본문의 {title['ratio']:.2f}배 (1.5배 미만)")
        if title["top_pct"] > 30:
            problems.append(f"{doc['file']} — 제목이 상단 {title['top_pct']:.0f}% 지점 (30% 초과)")
    return problems, sorted(set(gaps))


def main() -> int:
    parser = argparse.ArgumentParser(description="합성 법인서류 생성")
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=date.today(),
        help="기준일(YYYY-MM-DD). 문서 날짜를 여기서 역산한다. 기본값은 오늘",
    )
    parser.add_argument("--keep", action="store_true", help="samples/를 비우지 않고 덮어쓴다")
    args = parser.parse_args()

    docs = build_docs(args.as_of)

    if SAMPLE_DIR.exists() and not args.keep:
        shutil.rmtree(SAMPLE_DIR)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"기준일 {args.as_of} · {len(docs)}건")
    render_all(docs, SAMPLE_DIR)

    with LABELS_CSV.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["file", "expected_doc_type", "expected_relevance"])
        for doc in docs:
            relevance = "관련" if doc["doc_type"] else "판단 불가"
            writer.writerow([doc["file"], doc["doc_type"] or "", relevance])
    print(f"\nlabels.csv {len(docs)}행")

    MANIFEST.write_text(
        json.dumps(
            {
                "as_of": args.as_of.isoformat(),
                "company": COMPANY,
                "files": {d["file"]: d["context"] for d in docs},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    problems, gaps = verify(docs, SAMPLE_DIR)
    if gaps:
        print("\n[DB 앵커 확인 필요] 실물 서식에 그 문자열이 없다")
        for line in gaps:
            print(f"  {line}")
    if problems:
        print("\n[점검 실패]")
        for line in problems:
            print(f"  {line}")
        return 1
    print("\n점검 통과 — 앵커·제목 크기·제목 위치")
    return 0


if __name__ == "__main__":
    sys.exit(main())
