"""Build and seed the ProofBridge SQLite policy database."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "proofbridge.db"
DEFAULT_SEED_PATH = PROJECT_ROOT / "data" / "seeds" / "hana_corporate_account.json"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect_database(database_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open SQLite with foreign-key enforcement and row objects enabled."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create the eight policy tables and their indexes."""
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _required_id(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[Any, ...],
    label: str,
) -> int:
    row = connection.execute(query, parameters).fetchone()
    if row is None:
        raise ValueError(f"{label}의 데이터베이스 ID를 찾지 못했습니다")
    return int(row["id"])


def seed_database(
    connection: sqlite3.Connection,
    seed_path: Path | str = DEFAULT_SEED_PATH,
) -> None:
    """Load the curated Hana Bank case in one idempotent transaction."""
    payload = json.loads(Path(seed_path).read_text(encoding="utf-8"))
    bank = payload["bank"]
    policy = payload["policy"]

    with connection:
        connection.execute(
            """
            INSERT INTO banks (code, name_ko)
            VALUES (?, ?)
            ON CONFLICT(code) DO UPDATE SET name_ko = excluded.name_ko
            """,
            (bank["code"], bank["name_ko"]),
        )
        bank_id = _required_id(
            connection,
            "SELECT id FROM banks WHERE code = ?",
            (bank["code"],),
            bank["code"],
        )

        connection.execute(
            """
            INSERT INTO policy_versions (
                bank_id, policy_key, label_ko, customer_type, account_type,
                version, status, verified_at, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bank_id, policy_key, version) DO UPDATE SET
                label_ko = excluded.label_ko,
                customer_type = excluded.customer_type,
                account_type = excluded.account_type,
                status = excluded.status,
                verified_at = excluded.verified_at,
                notes = excluded.notes
            """,
            (
                bank_id,
                policy["policy_key"],
                policy["label_ko"],
                policy["customer_type"],
                policy["account_type"],
                policy["version"],
                policy["status"],
                policy["verified_at"],
                policy.get("notes"),
            ),
        )
        policy_version_id = _required_id(
            connection,
            """
            SELECT id
            FROM policy_versions
            WHERE bank_id = ? AND policy_key = ? AND version = ?
            """,
            (bank_id, policy["policy_key"], policy["version"]),
            policy["policy_key"],
        )

        for source in payload["sources"]:
            connection.execute(
                """
                INSERT INTO sources (
                    policy_version_id, source_key, scope, publisher, title,
                    url, checked_at, is_primary
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(policy_version_id, source_key) DO UPDATE SET
                    scope = excluded.scope,
                    publisher = excluded.publisher,
                    title = excluded.title,
                    url = excluded.url,
                    checked_at = excluded.checked_at,
                    is_primary = excluded.is_primary
                """,
                (
                    policy_version_id,
                    source["source_key"],
                    source["scope"],
                    source["publisher"],
                    source["title"],
                    source["url"],
                    source["checked_at"],
                    int(source["is_primary"]),
                ),
            )

        for document in payload["documents"]:
            connection.execute(
                """
                INSERT INTO documents (
                    code, name_ko, issuer, issuer_aliases_json,
                    title_patterns_json, required_anchors_json,
                    negative_anchors_json, doc_number_label,
                    issued_at_labels_json, validity_days, source_url,
                    as_of, last_checked, signature_verified, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name_ko = excluded.name_ko,
                    issuer = excluded.issuer,
                    issuer_aliases_json = excluded.issuer_aliases_json,
                    title_patterns_json = excluded.title_patterns_json,
                    required_anchors_json = excluded.required_anchors_json,
                    negative_anchors_json = excluded.negative_anchors_json,
                    doc_number_label = excluded.doc_number_label,
                    issued_at_labels_json = excluded.issued_at_labels_json,
                    validity_days = excluded.validity_days,
                    source_url = excluded.source_url,
                    as_of = excluded.as_of,
                    last_checked = excluded.last_checked,
                    signature_verified = excluded.signature_verified,
                    notes = excluded.notes
                """,
                (
                    document["code"],
                    document["name_ko"],
                    document.get("issuer"),
                    _json_text(document.get("issuer_aliases", [])),
                    _json_text(document.get("title_patterns", [])),
                    _json_text(document.get("required_anchors", [])),
                    _json_text(document.get("negative_anchors", [])),
                    document.get("doc_number_label"),
                    _json_text(document.get("issued_at_labels", [])),
                    document.get("validity_days"),
                    document.get("source_url"),
                    document["as_of"],
                    document["last_checked"],
                    int(document.get("verified", False)),
                    document.get("notes"),
                ),
            )

        # Each seed run replaces the child rules for this exact policy version.
        connection.execute(
            "DELETE FROM requirement_sets WHERE policy_version_id = ?",
            (policy_version_id,),
        )

        for requirement in payload["requirement_sets"]:
            source_id = _required_id(
                connection,
                """
                SELECT id FROM sources
                WHERE policy_version_id = ? AND source_key = ?
                """,
                (policy_version_id, requirement["source_key"]),
                requirement["source_key"],
            )
            cursor = connection.execute(
                """
                INSERT INTO requirement_sets (
                    policy_version_id, source_id, requirement_code, channel,
                    visitor_type, requirement_level, eligibility_notes, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    policy_version_id,
                    source_id,
                    requirement["requirement_code"],
                    requirement["channel"],
                    requirement["visitor_type"],
                    requirement["requirement_level"],
                    requirement.get("eligibility_notes"),
                    requirement.get("notes"),
                ),
            )
            requirement_set_id = int(cursor.lastrowid)

            for sort_order, document_rule in enumerate(requirement["documents"], start=1):
                document_id = _required_id(
                    connection,
                    "SELECT id FROM documents WHERE code = ?",
                    (document_rule["document_code"],),
                    document_rule["document_code"],
                )
                original_required = document_rule.get("original_required")
                connection.execute(
                    """
                    INSERT INTO requirement_documents (
                        requirement_set_id, document_id, original_required,
                        issued_within_days, submission_method, choice_group,
                        notes, sort_order
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        requirement_set_id,
                        document_id,
                        None if original_required is None else int(original_required),
                        document_rule.get("issued_within_days"),
                        document_rule["submission_method"],
                        document_rule.get("choice_group"),
                        document_rule.get("notes"),
                        sort_order,
                    ),
                )

            for sort_order, preparation in enumerate(
                requirement["preparations"],
                start=1,
            ):
                connection.execute(
                    """
                    INSERT INTO preparations (
                        requirement_set_id, code, name_ko, notes, sort_order
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        requirement_set_id,
                        preparation["code"],
                        preparation["name_ko"],
                        preparation.get("notes"),
                        sort_order,
                    ),
                )

        connection.execute(
            "DELETE FROM policy_conditions WHERE policy_version_id = ?",
            (policy_version_id,),
        )
        for condition in payload["policy_conditions"]:
            source_id = _required_id(
                connection,
                """
                SELECT id FROM sources
                WHERE policy_version_id = ? AND source_key = ?
                """,
                (policy_version_id, condition["source_key"]),
                condition["source_key"],
            )
            connection.execute(
                """
                INSERT INTO policy_conditions (
                    policy_version_id, source_id, condition_code, channel,
                    expression_json, result_code, description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    policy_version_id,
                    source_id,
                    condition["condition_code"],
                    condition["channel"],
                    _json_text(condition["expression"]),
                    condition["result_code"],
                    condition["description"],
                ),
            )


def database_summary(connection: sqlite3.Connection) -> dict[str, int]:
    """Return row counts used by CLI output and verification."""
    table_names = (
        "banks",
        "policy_versions",
        "requirement_sets",
        "documents",
        "requirement_documents",
        "preparations",
        "policy_conditions",
        "sources",
    )
    return {
        table_name: int(
            connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        )
        for table_name in table_names
    }


def build_database(
    database_path: Path | str = DEFAULT_DB_PATH,
    seed_path: Path | str = DEFAULT_SEED_PATH,
    *,
    replace: bool = False,
) -> dict[str, int]:
    """Create, seed, and close a complete SQLite database."""
    path = Path(database_path)
    if replace and path.exists():
        path.unlink()

    connection = connect_database(path)
    try:
        initialize_schema(connection)
        seed_database(connection, seed_path)
        return database_summary(connection)
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="하나은행 법인계좌 개설 정책 SQLite DB를 생성합니다."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED_PATH)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="기존 대상 DB 파일을 지운 뒤 다시 생성합니다.",
    )
    args = parser.parse_args()

    summary = build_database(args.db, args.seed, replace=args.replace)
    print(json.dumps({"database": str(args.db), "rows": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
