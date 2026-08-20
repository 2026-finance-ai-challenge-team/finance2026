"""`scenarios.csv`를 만든다 — 필수 서류를 하나씩 빼면서 "부족"이 제대로 나오는지 볼 표.

필수 목록은 찬형의 규칙 DB에서 읽는 게 원칙이다. 못 읽으면 하드코딩으로 폴백하고
폴백했다는 사실을 반드시 출력한다. 조용히 폴백하면 DB가 바뀐 걸 모른 채 계속 통과한다.

    python make_scenarios.py
    EVAL_DB_URL=postgresql://... python make_scenarios.py
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LABELS_CSV = BASE_DIR / "labels.csv"
SCENARIOS_CSV = BASE_DIR / "scenarios.csv"

CHANNEL = "branch"
VISITOR_TYPE = "representative"

REQUIREMENT_SQL = """
SELECT d.doc_type, rd.issued_within_days, rd.choice_group, rs.requirement_level
FROM requirement_documents rd
JOIN documents d ON d.id = rd.document_id
JOIN requirement_sets rs ON rs.id = rd.requirement_set_id
WHERE rs.channel = %(channel)s AND rs.visitor_type = %(visitor_type)s
"""

# TODO(swap): DB 조회가 되면 아래 두 블록을 지운다. 지금은 하나은행 법인계좌 개설 안내를
# 사람이 읽고 옮겨적은 임시값이라 Q1(목록이 맞나) 검증을 통과한 값이 아니다.
FALLBACK_REQUIRED = [
    "business_registration_certificate",
    "corporate_registry_certificate",
    "corporate_seal_certificate",
    "articles_of_incorporation",
]
FALLBACK_CHOICE_GROUPS = {
    "beneficial_owner_evidence": ["shareholder_registry", "share_change_statement"],
}

FIELDS = ["id", "kind", "files", "expect_missing", "expect_expired", "note"]


def load_requirements() -> tuple[list[str], dict[str, list[str]], bool]:
    """(필수 목록, 선택 그룹, DB에서 읽었는지)."""
    db_url = os.environ.get("EVAL_DB_URL")
    if not db_url:
        return FALLBACK_REQUIRED, FALLBACK_CHOICE_GROUPS, False

    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("psycopg2가 없어 DB를 건너뛴다.", file=sys.stderr)
        return FALLBACK_REQUIRED, FALLBACK_CHOICE_GROUPS, False

    try:
        with psycopg2.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(REQUIREMENT_SQL, {"channel": CHANNEL, "visitor_type": VISITOR_TYPE})
            rows = cur.fetchall()
    except Exception as exc:  # 연결 실패도 폴백 사유로 보고한다
        print(f"DB 조회 실패 — {exc}", file=sys.stderr)
        return FALLBACK_REQUIRED, FALLBACK_CHOICE_GROUPS, False

    if not rows:
        print(f"DB에 {CHANNEL}/{VISITOR_TYPE} 요건이 없다.", file=sys.stderr)
        return FALLBACK_REQUIRED, FALLBACK_CHOICE_GROUPS, False

    required: list[str] = []
    groups: dict[str, list[str]] = {}
    for doc_type, _within_days, choice_group, level in rows:
        if choice_group:
            groups.setdefault(choice_group, []).append(doc_type)
        elif level == "required":
            required.append(doc_type)
    return required, groups, True


def canonical_files() -> dict[str, str]:
    """doc_type -> 대표 샘플 파일. 기한만료본·이미지 변형은 대표에서 제외한다."""
    mapping: dict[str, str] = {}
    with LABELS_CSV.open(encoding="utf-8") as fp:
        for row in csv.DictReader(fp):
            doc_type = row["expected_doc_type"]
            name = row["file"]
            if not doc_type or not name.endswith(".pdf") or "_" in Path(name).stem:
                continue
            mapping.setdefault(doc_type, name)
    return mapping


def build_rows(required: list[str], groups: dict[str, list[str]], files: dict[str, str]) -> list[dict]:
    def to_files(doc_types: list[str]) -> str:
        return ",".join(files[d] for d in doc_types if d in files)

    # 기준 묶음 = 필수 전부 + 각 선택 그룹에서 하나. 이 상태에서 부족이 나오면 안 된다.
    baseline = list(required) + [members[0] for members in groups.values() if members]
    all_expected = list(required) + list(groups.keys())

    rows: list[dict] = [
        {
            "id": "sc0",
            "kind": "auto",
            "files": to_files(baseline),
            "expect_missing": "",
            "expect_expired": "",
            "note": "기준 묶음 — 부족 없음",
        }
    ]

    # 하나씩 빼기. 뺐는데 부족으로 안 나오면 그 서류는 목록에만 있고 실제로는 안 보는 것이다.
    for doc_type in required:
        rows.append(
            {
                "id": f"sc_{doc_type}",
                "kind": "auto",
                "files": to_files([d for d in baseline if d != doc_type]),
                "expect_missing": doc_type,
                "expect_expired": "",
                "note": f"{doc_type} 하나만 빠진 상태",
            }
        )

    group_id, members = next(iter(groups.items()), ("", []))
    first, second = (members + ["", ""])[:2]

    traps = [
        ("t1", "대체", required + [first], "", "", "대체서류 중 하나만 내도 충족"),
        ("t2", "대체", required + [second], "", "", "다른 하나만 내도 충족"),
        ("t3", "대체", required, group_id, "", "대체서류 둘 다 없음 — 부족으로 나와야 한다"),
        ("t4", "대체", required + [first, second], "", "", "둘 다 냈다고 둘 다 요구하면 과잉"),
        ("t6", "기한", None, "", "corporate_registry_certificate", "1년 지난 등기부 — 기한 만료"),
        ("t7", "엣지", ["__취업후기__"], "|".join(all_expected), "", "증명서가 아닌 파일 하나 — 전부 부족, 안 죽음"),
        ("t8", "엣지", [], "|".join(all_expected), "", "파일 0개 — 전부 부족, 안 죽음"),
        ("t9", "유사쌍", ["__사업자등록증명__"], "|".join(all_expected), "", "사업자등록증명을 사업자등록증으로 오인하면 안 된다"),
        ("t10", "유사쌍", ["__개인인감__"], "|".join(all_expected), "", "개인인감증명서를 법인인감증명서로 오인하면 안 된다"),
    ]

    special = {
        "__취업후기__": "취업후기.pdf",
        "__사업자등록증명__": "사업자등록증명.pdf",
        "__개인인감__": "개인인감증명서.pdf",
    }

    for trap_id, kind, doc_types, missing, expired, note in traps:
        if doc_types is None:  # t6 — 등기부만 기한만료본으로 바꾼 기준 묶음
            names = [
                "법인등기부_기한만료.pdf" if d == "corporate_registry_certificate" else files[d]
                for d in baseline
                if d in files or d == "corporate_registry_certificate"
            ]
        else:
            names = [special.get(d, files.get(d, "")) for d in doc_types]
        rows.append(
            {
                "id": trap_id,
                "kind": kind,
                "files": ",".join(n for n in names if n),
                "expect_missing": missing,
                "expect_expired": expired,
                "note": note,
            }
        )

    # t5는 같은 파일을 두 번 넣는다. 중복 제거가 되는지가 초점이라 따로 만든다.
    dup = files.get("business_registration_certificate", "")
    rows.append(
        {
            "id": "t5",
            "kind": "중복",
            "files": f"{dup},{dup}",
            "expect_missing": "|".join(d for d in all_expected if d != "business_registration_certificate"),
            "expect_expired": "",
            "note": "같은 파일 2번 — 2개로 세면 안 된다",
        }
    )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="시나리오 표 생성")
    parser.add_argument("--print", action="store_true", help="생성한 표를 화면에도 출력")
    args = parser.parse_args()

    if not LABELS_CSV.is_file():
        print("labels.csv가 없다. 먼저 generate.py를 돌린다.", file=sys.stderr)
        return 1

    required, groups, from_db = load_requirements()
    if from_db:
        print(f"요건 출처: DB ({CHANNEL}/{VISITOR_TYPE})")
    else:
        print("요건 출처: 하드코딩 폴백 — DB를 못 읽었다. 이 표는 규칙 변경을 반영하지 못한다.")
    print(f"  필수 {len(required)}종 · 선택 그룹 {len(groups)}개")

    files = canonical_files()
    unmapped = [d for d in required if d not in files]
    if unmapped:
        print(f"  샘플이 없는 필수 서류 {unmapped} — generate.py 목록을 확인한다.", file=sys.stderr)

    rows = build_rows(required, groups, files)
    with SCENARIOS_CSV.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"scenarios.csv {len(rows)}행 (자동 {sum(1 for r in rows if r['kind'] == 'auto')} · 함정 {sum(1 for r in rows if r['kind'] != 'auto')})")
    if args.print:
        for row in rows:
            print(f"  {row['id']:>34} {row['kind']:<5} {row['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
