"""Read-only policy queries used by the classifier and future rule engine."""

from __future__ import annotations

import json
from typing import Any

from .runtime import ConnectionLike


def _json_value(value: Any) -> Any:
    if isinstance(value, (str, bytes, bytearray)):
        return json.loads(value)
    return value


def _date_text(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _published_policy_id(
    connection: ConnectionLike,
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


def list_task_descriptors(connection: ConnectionLike) -> list[dict[str, Any]]:
    """List latest registered operations with their safest available route.

    A policy may expose several named operations. Requirements are still scoped
    by policy/channel/visitor and, where applicable, a separately selected
    purpose code.
    """
    rows = connection.execute(
        """
        WITH latest AS (
            SELECT pv.*, ROW_NUMBER() OVER (
                PARTITION BY pv.bank_id, pv.policy_key
                ORDER BY pv.version DESC
            ) AS version_rank
            FROM policy_versions AS pv
            WHERE pv.status <> 'retired'
        )
        SELECT
            b.slug || '.' || latest.policy_key ||
                CASE WHEN po.operation_code = latest.policy_key THEN ''
                     ELSE '.' || po.operation_code END AS task_id,
            b.code AS bank_code,
            b.name_ko AS bank_name_ko,
            latest.policy_key,
            po.operation_code,
            po.label_ko,
            latest.status AS policy_status,
            route.channel,
            route.visitor_type,
            source.url AS source_url,
            source.checked_at AS last_checked
        FROM latest
        JOIN banks AS b ON b.id = latest.bank_id
        JOIN policy_operations AS po ON po.policy_version_id = latest.id
        LEFT JOIN LATERAL (
            SELECT rs.channel, rs.visitor_type
            FROM requirement_sets AS rs
            WHERE rs.policy_version_id = latest.id
            ORDER BY
                CASE rs.requirement_level
                    WHEN 'official_minimum' THEN 1
                    WHEN 'official_required' THEN 1
                    ELSE 2
                END,
                rs.id
            LIMIT 1
        ) AS route ON TRUE
        LEFT JOIN LATERAL (
            SELECT s.url, s.checked_at
            FROM sources AS s
            WHERE s.policy_version_id = latest.id
            ORDER BY s.is_primary DESC, s.id
            LIMIT 1
        ) AS source ON TRUE
        WHERE latest.version_rank = 1
        ORDER BY b.name_ko, po.label_ko, task_id
        """
    ).fetchall()
    return [
        {
            **dict(row),
            "last_checked": (
                _date_text(row["last_checked"])
                if row["last_checked"] is not None
                else None
            ),
        }
        for row in rows
    ]


def find_requirements(
    connection: ConnectionLike,
    *,
    channel: str,
    visitor_type: str,
    purpose_code: str | None = None,
    bank_code: str = "KEB_HANA",
    policy_key: str = "corporate_account_opening",
    operation_code: str | None = None,
) -> dict[str, Any]:
    """Return exact and shared requirement sets for one user path."""
    policy_version_id = _published_policy_id(connection, bank_code, policy_key)
    policy = connection.execute(
        """
        SELECT
            pv.policy_key, pv.label_ko, pv.customer_type, pv.account_type,
            pv.version, pv.status, pv.verified_at, b.code AS bank_code,
            b.slug AS bank_slug, b.name_ko AS bank_name_ko
        FROM policy_versions AS pv
        JOIN banks AS b ON b.id = pv.bank_id
        WHERE pv.id = ?
        """,
        (policy_version_id,),
    ).fetchone()
    assert policy is not None

    configured_purposes = connection.execute(
        """
        SELECT DISTINCT purpose_code
        FROM requirement_sets
        WHERE policy_version_id = ? AND purpose_code IS NOT NULL
        ORDER BY purpose_code
        """,
        (policy_version_id,),
    ).fetchall()
    if configured_purposes and purpose_code is None:
        raise ValueError("이 정책은 purpose_code를 선택해야 조회할 수 있습니다")

    purpose_clause = " AND rs.purpose_code = ?" if purpose_code else ""
    parameters: tuple[Any, ...] = (policy_version_id, channel, visitor_type)
    if purpose_code:
        parameters += (purpose_code,)
    requirement_rows = connection.execute(
        f"""
        SELECT
            rs.*, s.title AS source_title, s.url AS source_url,
            s.checked_at AS source_checked_at
        FROM requirement_sets AS rs
        JOIN sources AS s ON s.id = rs.source_id
        WHERE rs.policy_version_id = ?
          AND rs.channel = ?
          AND rs.visitor_type IN (?, 'representative_or_agent')
          {purpose_clause}
        ORDER BY
            CASE rs.requirement_level
                WHEN 'official_minimum' THEN 1
                WHEN 'official_required' THEN 1
                ELSE 2
            END,
            rs.id
        """,
        parameters,
    ).fetchall()

    requirement_sets: list[dict[str, Any]] = []
    for requirement in requirement_rows:
        document_rows = connection.execute(
            """
            SELECT
                d.doc_type, d.label_ko,
                rd.original_required, rd.issued_within_days,
                rd.submission_method, rd.choice_group, rd.bundle_code,
                rd.acquisition_json, rd.notes
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
            item["acquisition"] = _json_value(item.pop("acquisition_json"))
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
                    "checked_at": _date_text(requirement["source_checked_at"]),
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
        item["expression"] = _json_value(item.pop("expression_json"))
        conditions.append(item)

    task_id = f"{policy['bank_slug']}.{policy['policy_key']}"
    if operation_code and operation_code != policy["policy_key"]:
        task_id = f"{task_id}.{operation_code}"
    return {
        "task_id": task_id,
        "label_ko": policy["label_ko"],
        "bank_code": policy["bank_code"],
        "bank_name_ko": policy["bank_name_ko"],
        "customer_type": policy["customer_type"],
        "account_type": policy["account_type"],
        "policy_version": policy["version"],
        "policy_status": policy["status"],
        "verified_at": _date_text(policy["verified_at"]),
        "purpose_code": purpose_code,
        "requirement_sets": requirement_sets,
        "policy_conditions": conditions,
    }


def list_document_signatures(connection: ConnectionLike) -> list[dict[str, Any]]:
    """Return document signatures in the classifier's requested JSON shape."""
    rows = connection.execute(
        """
        SELECT *
        FROM documents
        ORDER BY doc_type
        """
    ).fetchall()

    signatures = []
    for row in rows:
        signatures.append(
            {
                "doc_type": row["doc_type"],
                "label_ko": row["label_ko"],
                "issuer": row["issuer"],
                "issuer_aliases": _json_value(row["issuer_aliases"]),
                "title_patterns": _json_value(row["title_patterns"]),
                "required_anchors": _json_value(row["required_anchors"]),
                "negative_anchors": _json_value(row["negative_anchors"]),
                "doc_number_label": row["doc_number_label"],
                "issued_at_labels": _json_value(row["issued_at_labels"]),
                "validity_days": row["validity_days"],
                "acquisition": _json_value(row["acquisition_json"]),
                "source_url": row["source_url"],
                "as_of": _date_text(row["as_of"]),
                "last_checked": _date_text(row["last_checked"]),
                "verified": bool(row["verified"]),
                "notes": row["notes"],
            }
        )
    return signatures
