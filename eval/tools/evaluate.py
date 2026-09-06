"""`labels.csv` + `scenarios.csv`로 파이프라인을 두드리고 채점.

전체 정확도가 아니라 틀린 방향을 측정.

- 부족한데 부족하다고 안 함        → 치명. 사용자가 믿고 갔다가 은행에서 거절
- 못 알아본 문서를 '불필요'로 처리 → 치명. 필수 서류가 조용히 누락
- 유사쌍을 반대쪽으로 분류         → 치명. 낸 적 없는 서류를 냈다고 계수
- 과잉 요구                        → 기록만. 서류 한 장 추가 발급으로 해결

치명 1건 이상이면 종료 코드 1.

    python tools/evaluate.py                 # 어댑터 자동 탐색
    python tools/evaluate.py --adapter demo  # 파이프라인 없이 채점기만 확인
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BASE_DIR.parent
SAMPLE_DIR = BASE_DIR / "data" / "samples"
LABELS_CSV = BASE_DIR / "data" / "labels.csv"
SCENARIOS_CSV = BASE_DIR / "data" / "scenarios.csv"
REPORT_DIR = BASE_DIR / "reports"

UNKNOWN = "판단 불가"
NOT_NEEDED = "이번 업무에는 불필요"

# 반대쪽으로 분류하면 치명인 짝. None은 10종 밖 문서
NEGATIVE_PAIRS: tuple[tuple[str | None, str | None], ...] = (
    ("business_registration_certificate", "business_registration_verification"),
    ("shareholder_registry", "share_change_statement"),
    (None, "corporate_seal_certificate"),
)

CHOICE_GROUPS = {"beneficial_owner_evidence": ("shareholder_registry", "share_change_statement")}

COVERAGE_SQL = """
SELECT COUNT(*) FILTER (WHERE source_url IS NOT NULL AND checked_at IS NOT NULL), COUNT(*)
FROM {table}
"""
COVERAGE_TABLES = ("documents", "requirement_documents", "policy_conditions")


# ─────────────────────────────────────────────────────────────────────────────
# 어댑터 — 파이프라인 호출 방식 확정 시 이 구간만 교체
# ─────────────────────────────────────────────────────────────────────────────


class ModuleAdapter:
    """저장소의 파이썬 모듈을 직접 import. 가장 빠르고 오차 적음."""

    name = "module"

    def __init__(self) -> None:
        sys.path.insert(0, str(REPO_ROOT))
        self._classify = importlib.import_module("modules.doc_classify")
        self._judge = importlib.import_module("modules.requirements")

    def classify_one(self, path: Path) -> dict:
        return self._classify.classify(str(path))  # TODO(swap): 실제 함수명 확인

    def judge(self, paths: list[Path]) -> dict:
        return self._judge.judge([str(p) for p in paths])  # TODO(swap)


class CliAdapter:
    """`python -m modules.doc_classify.cli --report`를 호출해 JSON 수신."""

    name = "cli"
    MODULE = "modules.doc_classify.cli"

    def __init__(self) -> None:
        # 존재 확인. 없으면 auto가 cli 선택 후 매 호출마다 실패
        probe = subprocess.run(
            [sys.executable, "-m", self.MODULE, "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if probe.returncode != 0:
            raise RuntimeError(f"{self.MODULE} 실행 불가")

    def _run(self, args: list[str]) -> dict:
        proc = subprocess.run(
            [sys.executable, "-m", self.MODULE, *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip()[:200])
        return json.loads(proc.stdout)

    def classify_one(self, path: Path) -> dict:
        return self._run(["--report", str(path)])

    def judge(self, paths: list[Path]) -> dict:
        return self._run(["--judge", *[str(p) for p in paths]])  # TODO(swap)


class HttpAdapter:
    """기동 중인 주소를 호출. 여기서 서버 기동은 안 함."""

    name = "http"

    def __init__(self, base: str) -> None:
        import requests

        self._requests = requests
        self.base = base.rstrip("/")

    def classify_one(self, path: Path) -> dict:
        with path.open("rb") as fp:
            res = self._requests.post(f"{self.base}/analyze", files={"file": fp}, timeout=120)
        res.raise_for_status()
        return res.json()

    def judge(self, paths: list[Path]) -> dict:
        res = self._requests.post(
            f"{self.base}/judge", json={"files": [p.name for p in paths]}, timeout=120
        )
        res.raise_for_status()
        return res.json()


class DemoAdapter:
    """정답표를 그대로 되돌려주는 가짜 파이프라인.

    채점기 동작 확인용. 성능 측정이 아님.
    각 검사의 발동 여부를 보려고 결함 2건을 의도적으로 포함 —
    저조도 이미지 오분류(`[혼동]`), 중복 파일 2회 계수(`[실패]` t5).
    """

    name = "demo"

    def __init__(self, labels: list[dict]) -> None:
        self.truth = {row["file"]: row for row in labels}

    def classify_one(self, path: Path) -> dict:
        row = self.truth.get(path.name, {})
        doc_type = row.get("expected_doc_type") or None
        if path.name == "법인등기부_어두움.png":  # 저조도에서 놓친 경우를 가정
            return {"doc_type": None, "confidence": 0.31, "relevance": UNKNOWN}
        return {
            "doc_type": doc_type,
            "confidence": 0.94 if doc_type else 0.22,
            "relevance": "관련" if doc_type else UNKNOWN,
        }

    def judge(self, paths: list[Path]) -> dict:
        from make_scenarios import FALLBACK_CHOICE_GROUPS, FALLBACK_REQUIRED

        expired, accepted = [], []
        for path in paths:
            doc_type = (self.truth.get(path.name, {}) or {}).get("expected_doc_type") or None
            if doc_type is None:
                continue
            if "기한만료" in path.name:
                expired.append(doc_type)
            else:
                accepted.append(doc_type)

        missing = [d for d in FALLBACK_REQUIRED if d not in accepted]
        for group_id, members in FALLBACK_CHOICE_GROUPS.items():
            if not any(m in accepted for m in members):
                missing.append(group_id)
        return {"missing": missing, "expired": expired, "accepted": accepted, "notes": []}


def resolve_adapter(choice: str, labels: list[dict]):
    """import → CLI → HTTP 순으로 시도. 전부 실패 시 None."""
    if choice == "demo":
        return DemoAdapter(labels)

    attempts = {
        "module": lambda: ModuleAdapter(),
        "cli": lambda: CliAdapter(),
        "http": lambda: HttpAdapter(os.environ["EVAL_API_BASE"]),
    }
    order = [choice] if choice != "auto" else ["module", "cli", "http"]
    for name in order:
        try:
            adapter = attempts[name]()
        except Exception as exc:
            if choice != "auto":
                print(f"{name} 어댑터 실패 — {exc}", file=sys.stderr)
            continue
        return adapter
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 채점
# ─────────────────────────────────────────────────────────────────────────────


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fp:
        return list(csv.DictReader(fp))


def split(value: str) -> list[str]:
    return [item for item in (value or "").split("|") if item]


def satisfies(expected: str, reported: set[str]) -> bool:
    """선택 그룹은 그룹 id로 답해도, 구성원 중 하나로 답해도 정답 처리."""
    if expected in reported:
        return True
    return any(member in reported for member in CHOICE_GROUPS.get(expected, ()))


def score_classification(adapter, labels: list[dict]) -> dict:
    correct = unknown_correct = unknown_total = 0
    fatal_not_needed: list[str] = []
    fatal_pair: list[str] = []
    confused: list[str] = []
    errors: list[str] = []

    for row in labels:
        path = SAMPLE_DIR / row["file"]
        expected = row["expected_doc_type"] or None
        expects_unknown = row["expected_relevance"] == UNKNOWN
        unknown_total += expects_unknown

        try:
            result = adapter.classify_one(path)
        except Exception as exc:
            errors.append(f"{row['file']} — 호출 실패 {exc}")
            continue

        got = result.get("doc_type") or None
        relevance = result.get("relevance") or ""

        if expects_unknown:
            if relevance == NOT_NEEDED:
                fatal_not_needed.append(f"{row['file']} — 판단 불가를 '{NOT_NEEDED}'로 출력")
            elif got is None:
                unknown_correct += 1
        if got == expected:
            correct += 1
            continue

        pair_hit = any({expected, got} == {a, b} for a, b in NEGATIVE_PAIRS)
        line = f"{row['file']} : {expected or UNKNOWN} → {got or UNKNOWN}"
        (fatal_pair if pair_hit else confused).append(line)

    return {
        "total": len(labels),
        "correct": correct,
        "unknown_total": unknown_total,
        "unknown_correct": unknown_correct,
        "fatal_not_needed": fatal_not_needed,
        "fatal_pair": fatal_pair,
        "confused": confused,
        "errors": errors,
    }


def score_judgement(adapter, scenarios: list[dict]) -> dict:
    caught = expected_total = 0
    fatal_missed: list[str] = []
    fatal_crash: list[str] = []
    over: list[str] = []
    failures: list[str] = []
    unmeasured: list[str] = []

    for row in scenarios:
        names = [n for n in row["files"].split(",") if n]
        paths = [SAMPLE_DIR / n for n in names]

        try:
            result = adapter.judge(paths)
        except Exception as exc:
            fatal_crash.append(f"{row['id']} — 예외 {type(exc).__name__}: {exc}")
            continue

        reported_missing = set(result.get("missing") or [])
        reported_expired = set(result.get("expired") or [])

        for expected in split(row["expect_missing"]):
            expected_total += 1
            if satisfies(expected, reported_missing):
                caught += 1
            else:
                fatal_missed.append(f"{row['id']} — {expected} 부족 미출력 ({row['note']})")

        # 기한 만료는 missing·expired 어느 쪽이든 검출 필요. 양쪽 다 없으면 통과시킨 것
        for expected in split(row["expect_expired"]):
            expected_total += 1
            if satisfies(expected, reported_missing | reported_expired):
                caught += 1
            else:
                fatal_missed.append(f"{row['id']} — {expected} 기한 만료 미검출")

        allowed = set(split(row["expect_missing"])) | set(split(row["expect_expired"]))
        for extra in sorted(reported_missing - allowed):
            if not any(extra in CHOICE_GROUPS.get(a, ()) for a in allowed):
                over.append(f"{row['id']} — {extra}를 추가로 요구 ({row['note']})")

        if row["kind"] == "중복":
            accepted = result.get("accepted")
            if accepted is None:
                unmeasured.append(f"{row['id']} — 어댑터에 accepted 없음, 중복 계수 확인 불가")
            else:
                dup = [d for d, n in Counter(accepted).items() if n > 1]
                if dup:
                    failures.append(f"{row['id']} — {dup} 2회 계수")

    return {
        "caught": caught,
        "expected_total": expected_total,
        "fatal_missed": fatal_missed,
        "fatal_crash": fatal_crash,
        "over": over,
        "failures": failures,
        "unmeasured": unmeasured,
    }


def score_coverage() -> dict:
    """규칙에 공식 출처·확인일이 붙은 비율. DB 미연결 시 100%로 표기 금지."""
    db_url = os.environ.get("EVAL_DB_URL")
    if not db_url:
        return {"connected": False, "reason": "EVAL_DB_URL 없음"}
    try:
        import psycopg2
    except ImportError:
        return {"connected": False, "reason": "psycopg2 없음"}

    rows: dict[str, tuple[int, int]] = {}
    try:
        with psycopg2.connect(db_url) as conn, conn.cursor() as cur:
            for table in COVERAGE_TABLES:
                cur.execute(COVERAGE_SQL.format(table=table))
                filled, total = cur.fetchone()
                rows[table] = (filled or 0, total or 0)
    except Exception as exc:
        return {"connected": False, "reason": str(exc)[:120]}
    return {"connected": True, "tables": rows}


# ─────────────────────────────────────────────────────────────────────────────
# 출력
# ─────────────────────────────────────────────────────────────────────────────


def render(cls: dict, judge: dict, coverage: dict, adapter_name: str) -> tuple[str, int]:
    lines: list[str] = []
    fatal = 0

    lines.append(f"어댑터: {adapter_name}")
    lines.append("")
    lines.append("[분류]")
    lines.append(f"  정확도             {cls['correct']}/{cls['total']}")
    lines.append(f"  판단불가 정답      {cls['unknown_correct']}/{cls['unknown_total']}")
    for label, items in (
        ("실패→불필요", cls["fatal_not_needed"]),
        ("유사쌍 혼동", cls["fatal_pair"]),
    ):
        fatal += len(items)
        lines.append(f"  [치명] {label}  {len(items)}건")
        lines.extend(f"    {item}" for item in items)
    for item in cls["confused"]:
        lines.append(f"  [혼동] {item}")
    for item in cls["errors"]:
        lines.append(f"  [오류] {item}")

    lines.append("")
    lines.append("[판정]")
    total = judge["expected_total"]
    rate = f" ({judge['caught'] / total:.0%})" if total else ""
    lines.append(f"  누락 탐지 재현율   {judge['caught']}/{total}{rate}")
    for label, items in (
        ("부족 미탐지", judge["fatal_missed"]),
        ("실행 중 예외", judge["fatal_crash"]),
    ):
        fatal += len(items)
        lines.append(f"  [치명] {label}  {len(items)}건")
        lines.extend(f"    {item}" for item in items)
    for item in judge["failures"]:
        lines.append(f"  [실패] {item}")
    for item in judge["over"]:
        lines.append(f"  [과잉] {item}")
    for item in judge["unmeasured"]:
        lines.append(f"  [미측정] {item}")

    lines.append("")
    lines.append("[규칙]")
    if coverage["connected"]:
        for table, (filled, total_rows) in coverage["tables"].items():
            pct = f"{filled / total_rows:.0%}" if total_rows else "—"
            lines.append(f"  {table:<24} {filled}/{total_rows} ({pct})")
    else:
        lines.append(f"  출처 커버리지      미측정 — {coverage['reason']}")

    lines.append("")
    lines.append(f"치명 {fatal}건")
    return "\n".join(lines), fatal


def main() -> int:
    parser = argparse.ArgumentParser(description="검증 채점기")
    parser.add_argument(
        "--adapter",
        default="auto",
        choices=["auto", "module", "cli", "http", "demo"],
        help="파이프라인 호출 방식. demo는 정답표를 되돌려주는 가짜",
    )
    parser.add_argument("--no-report", action="store_true", help="reports/ 저장 생략")
    args = parser.parse_args()

    for path in (LABELS_CSV, SCENARIOS_CSV):
        if not path.is_file():
            print(f"{path.name} 없음 — generate.py, make_scenarios.py 먼저 실행", file=sys.stderr)
            return 1

    labels = read_csv(LABELS_CSV)
    scenarios = read_csv(SCENARIOS_CSV)

    adapter = resolve_adapter(args.adapter, labels)
    if adapter is None:
        print("파이프라인 미탐지. 연결 대상이 없으면 --adapter demo로 채점기만 확인")
        print("  module : modules.doc_classify / modules.requirements 를 import")
        print("  cli    : python -m modules.doc_classify.cli")
        print("  http   : EVAL_API_BASE 환경변수")
        return 2

    if adapter.name == "demo":
        print("※ demo 어댑터 — 정답표를 되돌려주는 가짜. 파이프라인 성능 아님\n")

    cls = score_classification(adapter, labels)
    judge = score_judgement(adapter, scenarios)
    coverage = score_coverage()

    report, fatal = render(cls, judge, coverage, adapter.name)
    print(report)

    if not args.no_report:
        REPORT_DIR.mkdir(exist_ok=True)
        today = date.today().isoformat()
        out = REPORT_DIR / f"{today}.md"
        out.write_text(f"# 검증 결과 {today}\n\n```\n{report}\n```\n", encoding="utf-8")
        print(f"\n{out.relative_to(REPO_ROOT)}")

    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
