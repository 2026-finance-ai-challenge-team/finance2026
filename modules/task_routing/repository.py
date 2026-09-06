"""PostgreSQL catalog reader for the natural-language routing feature."""

from __future__ import annotations

from typing import Protocol

from modules.policy_db.runtime import connect_database

from .models import BankTask


class TaskCatalog(Protocol):
    def list_tasks(self) -> list[BankTask]: ...


class PostgreSQLTaskCatalog:
    """Return the latest non-retired operation rows registered in PostgreSQL."""

    def __init__(self, database_url: str) -> None:
        if not database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("PostgreSQL connection URL is required")
        self._database_url = database_url

    def list_tasks(self) -> list[BankTask]:
        connection = connect_database(self._database_url)
        try:
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
                        CASE
                            WHEN po.operation_code = latest.policy_key THEN ''
                            ELSE '.' || po.operation_code
                        END AS task_id,
                    b.code AS bank_code,
                    b.name_ko AS bank_name_ko,
                    latest.policy_key,
                    po.operation_code,
                    po.label_ko AS operation_name_ko,
                    latest.status AS policy_status,
                    source.title AS source_title,
                    source.url AS source_url,
                    source.checked_at AS source_checked_at
                FROM latest
                JOIN banks AS b ON b.id = latest.bank_id
                JOIN policy_operations AS po ON po.policy_version_id = latest.id
                LEFT JOIN LATERAL (
                    SELECT s.title, s.url, s.checked_at
                    FROM sources AS s
                    WHERE s.policy_version_id = latest.id
                    ORDER BY s.is_primary DESC, s.id
                    LIMIT 1
                ) AS source ON TRUE
                WHERE latest.version_rank = 1
                ORDER BY b.name_ko, po.label_ko, task_id
                """
            ).fetchall()
        finally:
            connection.close()

        tasks: list[BankTask] = []
        for row in rows:
            checked_at = row["source_checked_at"]
            tasks.append(
                BankTask(
                    task_id=row["task_id"],
                    bank_code=row["bank_code"],
                    bank_name_ko=row["bank_name_ko"],
                    policy_key=row["policy_key"],
                    operation_code=row["operation_code"],
                    operation_name_ko=row["operation_name_ko"],
                    policy_status=row["policy_status"],
                    source_title=row["source_title"],
                    source_url=row["source_url"],
                    source_checked_at=(
                        checked_at.isoformat()
                        if checked_at is not None and hasattr(checked_at, "isoformat")
                        else checked_at
                    ),
                )
            )
        return tasks
