"""Create and seed the ProofBridge PostgreSQL policy database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from modules.policy_db.runtime import connect_database

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEED_PATHS = (
    PROJECT_ROOT / "data" / "seeds" / "hana_corporate_account.json",
    PROJECT_ROOT / "data" / "seeds" / "kakaobank_limit_release.json",
    PROJECT_ROOT / "data" / "seeds" / "kb_financial_purpose.json",
    PROJECT_ROOT / "data" / "seeds" / "bank_operations_catalog.json",
)
SCHEMA_PATH = Path(__file__).with_name("schema.postgresql.sql")


def _expand_seed_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand the compact multi-bank operation catalog into normal seed cases."""
    if "banks" not in payload:
        return [payload]

    checked_at = payload["checked_at"]
    shared_documents = payload.get("documents", [])
    expanded: list[dict[str, Any]] = []
    for bank_entry in payload["banks"]:
        bank = bank_entry["bank"]
        sources = {
            source["source_key"]: source for source in bank_entry["sources"]
        }
        for operation in bank_entry["operations"]:
            source_key = operation["source_key"]
            source = sources.get(source_key)
            if source is None:
                raise ValueError(
                    f"{bank['code']} 업무의 출처가 없습니다: {source_key}"
                )
            policy_key = operation["policy_key"]
            expanded.append(
                {
                    "bank": bank,
                    "policy": {
                        "policy_key": policy_key,
                        "label_ko": operation["label_ko"],
                        "customer_type": operation.get("customer_type", "individual"),
                        "account_type": operation.get("account_type", "banking_service"),
                        "version": int(operation.get("version", 1)),
                        "status": operation.get("status", "draft"),
                        "verified_at": operation.get("verified_at", checked_at),
                        "notes": operation.get("notes"),
                    },
                    "operations": [
                        {
                            "operation_code": policy_key,
                            "label_ko": operation["label_ko"],
                            "notes": operation.get("notes"),
                        }
                    ],
                    "sources": [source],
                    "documents": shared_documents,
                    "requirement_sets": [
                        {
                            "requirement_code": f"{bank['slug']}.{policy_key}.official_guide",
                            "purpose_code": None,
                            "channel": operation["channel"],
                            "visitor_type": operation.get(
                                "visitor_type", "account_holder"
                            ),
                            "requirement_level": operation.get(
                                "requirement_level", "official_required"
                            ),
                            "eligibility_notes": operation.get("eligibility_notes"),
                            "notes": operation.get("requirement_notes"),
                            "source_key": source_key,
                            "documents": operation.get("documents", []),
                            "preparations": operation.get("preparations", []),
                        }
                    ],
                    "policy_conditions": operation.get("policy_conditions", []),
                }
            )
    return expanded


def _load_seed_payloads(seed_paths: tuple[Path, ...]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for path in seed_paths:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
        payloads.extend(_expand_seed_payload(raw_payload))
    return payloads


def validate_seed_catalog(
    seed_paths: tuple[Path, ...] = DEFAULT_SEED_PATHS,
) -> dict[str, int]:
    """Validate cross-seed references without contacting PostgreSQL."""
    payloads = _load_seed_payloads(seed_paths)
    document_types = {
        document["doc_type"]
        for payload in payloads
        for document in payload["documents"]
    }
    seen_policies: set[tuple[str, str, int]] = set()
    for payload in payloads:
        bank = payload["bank"]
        policy = payload["policy"]
        policy_identity = (
            bank["code"],
            policy["policy_key"],
            int(policy["version"]),
        )
        if policy_identity in seen_policies:
            raise ValueError(f"중복 정책 버전입니다: {policy_identity}")
        seen_policies.add(policy_identity)
        source_keys = {source["source_key"] for source in payload["sources"]}
        requirement_codes: set[str] = set()
        for requirement in payload["requirement_sets"]:
            code = requirement["requirement_code"]
            if code in requirement_codes:
                raise ValueError(f"중복 requirement_code입니다: {code}")
            requirement_codes.add(code)
            if requirement["source_key"] not in source_keys:
                raise ValueError(f"요건의 출처가 없습니다: {code}")
            for document in requirement["documents"]:
                if document["doc_type"] not in document_types:
                    raise ValueError(
                        f"문서 사전에 없는 doc_type입니다: {document['doc_type']}"
                    )
        for condition in payload["policy_conditions"]:
            if condition["source_key"] not in source_keys:
                raise ValueError(
                    f"조건의 출처가 없습니다: {condition['condition_code']}"
                )
    return {
        "seed_files": len(seed_paths),
        "seed_cases": len(payloads),
        "banks": len({payload["bank"]["code"] for payload in payloads}),
        "policies": len(seen_policies),
        "operations": sum(
            len(payload.get("operations", [payload["policy"]]))
            for payload in payloads
        ),
        "documents": len(document_types),
        "requirement_sets": sum(
            len(payload["requirement_sets"]) for payload in payloads
        ),
        "document_rules": sum(
            len(requirement["documents"])
            for payload in payloads
            for requirement in payload["requirement_sets"]
        ),
    }


def initialize_schema(connection: Any) -> None:
    """Create the PostgreSQL policy tables and indexes."""
    connection.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def _json_text(value: Any) -> Any:
    """Adapt Python structures explicitly for PostgreSQL JSONB columns."""
    from psycopg.types.json import Jsonb

    return Jsonb(value)


def _required_id(
    connection: Any,
    query: str,
    parameters: tuple[Any, ...],
    label: str,
) -> int:
    row = connection.execute(query, parameters).fetchone()
    if row is None:
        raise ValueError(f"{label}의 데이터베이스 ID를 찾지 못했습니다")
    return int(row["id"])


def seed_database(
    connection: Any,
    seed_path: Path | str | None = None,
) -> None:
    """Load all curated cases, or one explicitly selected case, idempotently."""
    if seed_path is None:
        for default_seed_path in DEFAULT_SEED_PATHS:
            seed_database(connection, default_seed_path)
        return

    raw_payload = json.loads(Path(seed_path).read_text(encoding="utf-8"))
    for payload in _expand_seed_payload(raw_payload):
        _seed_payload(connection, payload)


def _seed_payload(connection: Any, payload: dict[str, Any]) -> None:
    """Insert one normalized bank-operation policy payload."""
    bank = payload["bank"]
    policy = payload["policy"]

    with connection:
        connection.execute(
            """
            INSERT INTO banks (code, slug, name_ko)
            VALUES (?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                slug = excluded.slug,
                name_ko = excluded.name_ko
            """,
            (bank["code"], bank["slug"], bank["name_ko"]),
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

        operations = payload.get("operations") or [
            {
                "operation_code": policy["policy_key"],
                "label_ko": policy["label_ko"],
                "notes": policy.get("notes"),
            }
        ]
        connection.execute(
            "DELETE FROM policy_operations WHERE policy_version_id = ?",
            (policy_version_id,),
        )
        connection.executemany(
            """
            INSERT INTO policy_operations (
                policy_version_id, operation_code, label_ko, notes
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    policy_version_id,
                    operation["operation_code"],
                    operation["label_ko"],
                    operation.get("notes"),
                )
                for operation in operations
            ],
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
                    bool(source["is_primary"]),
                ),
            )

        for document in payload["documents"]:
            connection.execute(
                """
                INSERT INTO documents (
                    doc_type, label_ko, issuer, issuer_aliases,
                    title_patterns, required_anchors,
                    negative_anchors, doc_number_label,
                    issued_at_labels, validity_days, acquisition_json,
                    source_url, as_of, last_checked, verified, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_type) DO UPDATE SET
                    label_ko = excluded.label_ko,
                    issuer = excluded.issuer,
                    issuer_aliases = excluded.issuer_aliases,
                    title_patterns = excluded.title_patterns,
                    required_anchors = excluded.required_anchors,
                    negative_anchors = excluded.negative_anchors,
                    doc_number_label = excluded.doc_number_label,
                    issued_at_labels = excluded.issued_at_labels,
                    validity_days = excluded.validity_days,
                    acquisition_json = excluded.acquisition_json,
                    source_url = excluded.source_url,
                    as_of = excluded.as_of,
                    last_checked = excluded.last_checked,
                    verified = excluded.verified,
                    notes = excluded.notes
                """,
                (
                    document["doc_type"],
                    document["label_ko"],
                    document.get("issuer"),
                    _json_text(document.get("issuer_aliases", [])),
                    _json_text(document.get("title_patterns", [])),
                    _json_text(document.get("required_anchors", [])),
                    _json_text(document.get("negative_anchors", [])),
                    document.get("doc_number_label"),
                    _json_text(document.get("issued_at_labels", [])),
                    document.get("validity_days"),
                    _json_text(document.get("acquisition", {})),
                    document.get("source_url"),
                    document["as_of"],
                    document["last_checked"],
                    bool(document.get("verified", False)),
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
                    policy_version_id, source_id, requirement_code, purpose_code, channel,
                    visitor_type, requirement_level, eligibility_notes, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    policy_version_id,
                    source_id,
                    requirement["requirement_code"],
                    requirement.get("purpose_code"),
                    requirement["channel"],
                    requirement["visitor_type"],
                    requirement["requirement_level"],
                    requirement.get("eligibility_notes"),
                    requirement.get("notes"),
                ),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                raise RuntimeError("요건 묶음 ID를 생성하지 못했습니다")
            requirement_set_id = int(inserted["id"])

            for sort_order, document_rule in enumerate(requirement["documents"], start=1):
                document_id = _required_id(
                    connection,
                    "SELECT id FROM documents WHERE doc_type = ?",
                    (document_rule["doc_type"],),
                    document_rule["doc_type"],
                )
                original_required = document_rule.get("original_required")
                connection.execute(
                    """
                    INSERT INTO requirement_documents (
                        requirement_set_id, document_id, original_required,
                        issued_within_days, submission_method, choice_group,
                        bundle_code, acquisition_json, notes, sort_order
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        requirement_set_id,
                        document_id,
                        None if original_required is None else bool(original_required),
                        document_rule.get("issued_within_days"),
                        document_rule["submission_method"],
                        document_rule.get("choice_group"),
                        document_rule.get("bundle_code"),
                        _json_text(document_rule.get("acquisition", {})),
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


def database_summary(connection: Any) -> dict[str, int]:
    """Return row counts used by CLI output and verification."""
    table_names = (
        "banks",
        "policy_versions",
        "policy_operations",
        "requirement_sets",
        "documents",
        "requirement_documents",
        "preparations",
        "policy_conditions",
        "sources",
        "document_field_schema_versions",
    )
    return {
        table_name: int(
            connection.execute(
                f"SELECT COUNT(*) AS row_count FROM {table_name}"
            ).fetchone()["row_count"]
        )
        for table_name in table_names
    }


def build_database(
    database_url: str | None = None,
    seed_path: Path | str | None = None,
    *,
    replace: bool = False,
) -> dict[str, int]:
    """Create, seed, and close the PostgreSQL policy database."""
    connection = connect_database(database_url)
    try:
        initialize_schema(connection)
        if replace:
            connection.execute(
                """
                TRUNCATE TABLE
                    policy_conditions, preparations, requirement_documents,
                    requirement_sets, sources, policy_versions, documents, banks
                RESTART IDENTITY CASCADE
                """
            )
            connection.commit()
        seed_database(connection, seed_path)
        return database_summary(connection)
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="ProofBridge PostgreSQL 정책 DB를 생성합니다.")
    parser.add_argument(
        "--seed",
        type=Path,
        default=None,
        help="특정 시드만 넣을 때 지정합니다. 생략하면 모든 기본 시드를 넣습니다.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="ProofBridge 정책 테이블의 기존 행을 비운 뒤 다시 적재합니다.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="PostgreSQL에 연결하지 않고 모든 시드 참조만 검증합니다.",
    )
    args = parser.parse_args()

    if args.check:
        print(json.dumps(validate_seed_catalog(), ensure_ascii=False, indent=2))
        return
    summary = build_database(seed_path=args.seed, replace=args.replace)
    print(json.dumps({"database": "postgresql", "rows": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
