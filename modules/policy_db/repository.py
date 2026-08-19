"""Read-only policy queries used by the classifier and future rule engine."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def _published_policy_id(
    connection: sqlite3.Connection,
    bank_code: str,
    policy_key: str,
) -> int:
    row = connection.execute(
        """
        SELECT pv.id
        FROM policy_versions AS pv
        JOIN banks AS b ON b.id = pv.bank_id
        WHERE b.code = ?
          AND pv.policy_key = ?
          AND pv.status = 'published'
        ORDER BY pv.version DESC
        LIMIT 1
        """,
        (bank_code, policy_key),
    ).fetchone()
    if row is None:
        raise LookupError(f"공개된 정책을 찾을 수 없습니다: {bank_code}/{policy_key}")
    return int(row["id"])


def find_requirements(
    connection: sqlite3.Connection,
    *,
    channel: str,
    visitor_type: str,
    bank_code: str = "KEB_HANA",
    policy_key: str = "corporate_account_opening",
) -> dict[str, Any]:
    """Return exact and shared requirement sets for one user path."""
    policy_version_id = _published_policy_id(connection, bank_code, policy_key)
    policy = connection.execute(
        """
        SELECT
            pv.policy_key, pv.label_ko, pv.customer_type, pv.account_type,
            pv.version, pv.verified_at, b.code AS bank_code, b.name_ko AS bank_name_ko
        FROM policy_versions AS pv
        JOIN banks AS b ON b.id = pv.bank_id
        WHERE pv.id = ?
        """,
        (policy_version_id,),
    ).fetchone()
    assert policy is not None

    requirement_rows = connection.execute(
        """
        SELECT
            rs.*, s.title AS source_title, s.url AS source_url,
            s.checked_at AS source_checked_at
        FROM requirement_sets AS rs
        JOIN sources AS s ON s.id = rs.source_id
        WHERE rs.policy_version_id = ?
          AND rs.channel = ?
          AND rs.visitor_type IN (?, 'representative_or_agent')
        ORDER BY
            CASE rs.requirement_level
                WHEN 'official_minimum' THEN 1
                WHEN 'official_required' THEN 1
                ELSE 2
            END,
            rs.id
        """,
        (policy_version_id, channel, visitor_type),
    ).fetchall()

    requirement_sets: list[dict[str, Any]] = []
    for requirement in requirement_rows:
        document_rows = connection.execute(
            """
            SELECT
                d.code AS doc_type, d.name_ko AS label_ko,
                rd.original_required, rd.issued_within_days,
                rd.submission_method, rd.choice_group, rd.notes
            FROM requirement_documents AS rd
            JOIN documents AS d ON d.id = rd.document_id
            WHERE rd.requirement_set_id = ?
            ORDER BY rd.sort_order, d.id
            """,
            (requirement["id"],),
        ).fetchall()
        preparation_rows = connection.execute(
            """
            SELECT code, name_ko AS label_ko, notes
            FROM preparations
            WHERE requirement_set_id = ?
            ORDER BY sort_order, id
            """,
            (requirement["id"],),
        ).fetchall()

        documents = []
        for row in document_rows:
            item = dict(row)
            if item["original_required"] is not None:
                item["original_required"] = bool(item["original_required"])
            documents.append(item)

        requirement_sets.append(
            {
                "requirement_code": requirement["requirement_code"],
                "channel": requirement["channel"],
                "visitor_type": requirement["visitor_type"],
                "requirement_level": requirement["requirement_level"],
                "eligibility_notes": requirement["eligibility_notes"],
                "notes": requirement["notes"],
                "documents": documents,
                "preparations": [dict(row) for row in preparation_rows],
                "source": {
                    "title": requirement["source_title"],
                    "url": requirement["source_url"],
                    "checked_at": requirement["source_checked_at"],
                },
            }
        )

    condition_rows = connection.execute(
        """
        SELECT
            pc.condition_code, pc.channel, pc.expression_json,
            pc.result_code, pc.description, s.url AS source_url
        FROM policy_conditions AS pc
        JOIN sources AS s ON s.id = pc.source_id
        WHERE pc.policy_version_id = ?
          AND pc.channel IN (?, 'all')
        ORDER BY pc.id
        """,
        (policy_version_id, channel),
    ).fetchall()
    conditions = []
    for row in condition_rows:
        item = dict(row)
        item["expression"] = json.loads(item.pop("expression_json"))
        conditions.append(item)

    return {
        "task_id": f"hana.{policy['policy_key']}",
        "label_ko": policy["label_ko"],
        "bank_code": policy["bank_code"],
        "bank_name_ko": policy["bank_name_ko"],
        "customer_type": policy["customer_type"],
        "account_type": policy["account_type"],
        "policy_version": policy["version"],
        "verified_at": policy["verified_at"],
        "requirement_sets": requirement_sets,
        "policy_conditions": conditions,
    }


def list_document_signatures(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return document signatures in the classifier's requested JSON shape."""
    rows = connection.execute(
        """
        SELECT *
        FROM documents
        ORDER BY code
        """
    ).fetchall()

    signatures = []
    for row in rows:
        signatures.append(
            {
                "doc_type": row["code"],
                "label_ko": row["name_ko"],
                "issuer": row["issuer"],
                "issuer_aliases": json.loads(row["issuer_aliases_json"]),
                "title_patterns": json.loads(row["title_patterns_json"]),
                "required_anchors": json.loads(row["required_anchors_json"]),
                "negative_anchors": json.loads(row["negative_anchors_json"]),
                "doc_number_label": row["doc_number_label"],
                "issued_at_labels": json.loads(row["issued_at_labels_json"]),
                "validity_days": row["validity_days"],
                "source_url": row["source_url"],
                "as_of": row["as_of"],
                "last_checked": row["last_checked"],
                "verified": bool(row["signature_verified"]),
                "notes": row["notes"],
            }
        )
    return signatures
