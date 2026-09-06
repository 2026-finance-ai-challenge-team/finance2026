"""Turn a pg_dump of the policy database into the catalog the web server reads.

The web app must run without a database connection, so the dump is flattened
into one JSON file at build time. Re-run this whenever the dump is refreshed.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

COPY_HEADER = re.compile(r'^COPY public\.(\w+) \(([^)]*)\) FROM stdin;$')
UNESCAPE = {"\\N": None, r"\t": "\t", r"\n": "\n", r"\r": "\r", r"\\": "\\"}


def _unescape(value: str) -> str | None:
    if value == r"\N":
        return None
    out: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            nxt = value[index + 1]
            mapped = {"t": "\t", "n": "\n", "r": "\r", "\\": "\\"}.get(nxt)
            if mapped is not None:
                out.append(mapped)
                index += 2
                continue
        out.append(char)
        index += 1
    return "".join(out)


def read_tables(dump: str) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {}
    lines = dump.splitlines()
    index = 0
    while index < len(lines):
        header = COPY_HEADER.match(lines[index])
        if header is None:
            index += 1
            continue
        table = header.group(1)
        columns = [name.strip() for name in header.group(2).split(",")]
        rows: list[dict[str, Any]] = []
        index += 1
        while index < len(lines) and lines[index] != r"\.":
            values = lines[index].split("\t")
            rows.append({name: _unescape(value) for name, value in zip(columns, values)})
            index += 1
        tables[table] = rows
        index += 1
    return tables


def _int(value: str | None) -> int | None:
    return None if value in (None, "") else int(value)


def _bool(value: str | None) -> bool | None:
    return None if value is None else value == "t"


def _json(value: str | None, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def build_catalog(tables: dict[str, list[dict[str, Any]]], source_name: str) -> dict[str, Any]:
    banks = {row["id"]: row for row in tables["banks"]}
    policies = {row["id"]: row for row in tables["policy_versions"]}
    documents = {row["id"]: row for row in tables["documents"]}
    sources = {row["id"]: row for row in tables["sources"]}

    documents_by_set: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in tables["requirement_documents"]:
        document = documents[row["document_id"]]
        documents_by_set[row["requirement_set_id"]].append({
            "doc_type": document["doc_type"],
            "label_ko": document["label_ko"],
            "issuer": document["issuer"],
            "submission_method": row["submission_method"],
            "issued_within_days": _int(row["issued_within_days"]),
            "validity_days": _int(document["validity_days"]),
            "original_required": _bool(row["original_required"]),
            "choice_group": row["choice_group"],
            "bundle_code": row["bundle_code"],
            "notes": row["notes"],
            "acquisition": _json(row["acquisition_json"], {}) or _json(document["acquisition_json"], {}),
            "source_url": document["source_url"],
            "sort_order": _int(row["sort_order"]) or 0,
        })

    preparations_by_set: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(tables["preparations"], key=lambda item: (_int(item["sort_order"]) or 0, _int(item["id"]) or 0)):
        preparations_by_set[row["requirement_set_id"]].append({
            "code": row["code"],
            "label_ko": row["name_ko"],
            "notes": row["notes"],
        })

    sets_by_policy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in tables["requirement_sets"]:
        source = sources[row["source_id"]]
        sets_by_policy[row["policy_version_id"]].append({
            "requirement_code": row["requirement_code"],
            "purpose_code": row["purpose_code"],
            "channel": row["channel"],
            "visitor_type": row["visitor_type"],
            "requirement_level": row["requirement_level"],
            "eligibility_notes": row["eligibility_notes"],
            "notes": row["notes"],
            "documents": sorted(documents_by_set[row["id"]], key=lambda item: item["sort_order"]),
            "preparations": preparations_by_set[row["id"]],
            "source": {
                "publisher": source["publisher"],
                "title": source["title"],
                "url": source["url"],
                "checked_at": source["checked_at"],
                "is_primary": _bool(source["is_primary"]),
            },
        })

    operations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in tables["policy_operations"]:
        policy = policies[row["policy_version_id"]]
        bank = banks[policy["bank_id"]]
        operation_id = f"{bank['slug']}.{row['operation_code']}"
        if operation_id in seen:
            raise SystemExit(f"operation_id 중복: {operation_id}")
        seen.add(operation_id)
        operations.append({
            "operation_id": operation_id,
            "operation_code": row["operation_code"],
            "label_ko": row["label_ko"],
            "bank_code": bank["code"],
            "bank_slug": bank["slug"],
            "bank_label_ko": bank["name_ko"],
            "policy_version_id": _int(policy["id"]),
            "policy_key": policy["policy_key"],
            "policy_label_ko": policy["label_ko"],
            "customer_type": policy["customer_type"],
            "account_type": policy["account_type"],
            "status": policy["status"],
            "verified_at": policy["verified_at"],
        })
    operations.sort(key=lambda item: (item["bank_slug"], item["operation_code"]))

    policy_entries = []
    for policy_id in sorted(sets_by_policy, key=lambda value: int(value)):
        policy_entries.append({
            "policy_version_id": _int(policy_id),
            "requirement_sets": sets_by_policy[policy_id],
        })

    return {
        "schema_version": "1.0",
        "source_file": source_name,
        "generated_on": date.today().isoformat(),
        "banks": [
            {"bank_code": bank["code"], "bank_slug": bank["slug"], "label_ko": bank["name_ko"]}
            for bank in sorted(banks.values(), key=lambda item: item["slug"])
        ],
        "operations": operations,
        "policies": policy_entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path, help="pg_dump 결과 .sql 파일")
    parser.add_argument("--out", type=Path, required=True, help="생성할 JSON 경로")
    args = parser.parse_args()

    tables = read_tables(args.dump.read_text(encoding="utf-8"))
    catalog = build_catalog(tables, args.dump.name)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"업무 {len(catalog['operations'])}건, 정책 {len(catalog['policies'])}건 → {args.out}")


if __name__ == "__main__":
    main()
