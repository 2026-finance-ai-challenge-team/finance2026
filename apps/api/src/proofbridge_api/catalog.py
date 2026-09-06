"""Read-only task catalog backed by versioned repository data."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError
from modules.policy_db.repository import list_task_descriptors
from modules.policy_db.runtime import connect_database

from .contracts import TaskSummary


class TaskCatalogError(RuntimeError):
    """Raised when checked-in task metadata violates the API contract."""


class TaskCatalog:
    def __init__(self, repo_root: Path, database_url: str | None = None) -> None:
        self._tasks_dir = repo_root / "modules" / "doc_classify" / "tasks"
        self._database_url = database_url

    def list_tasks(self) -> list[TaskSummary]:
        tasks = {
            task.task_id: task
            for task in (
                self._load_task(path)
                for path in sorted(self._tasks_dir.glob("*.json"))
            )
        }
        if self._database_url:
            try:
                connection = connect_database(self._database_url)
                try:
                    rows = list_task_descriptors(connection)
                finally:
                    connection.close()
                for row in rows:
                    if not row.get("channel") or not row.get("visitor_type"):
                        continue
                    tasks[row["task_id"]] = TaskSummary(
                        task_id=row["task_id"],
                        label_ko=row["label_ko"],
                        bank_code=row["bank_code"],
                        bank_name_ko=row["bank_name_ko"],
                        policy_key=row["policy_key"],
                        operation_code=row["operation_code"],
                        channel=row["channel"],
                        visitor_type=row["visitor_type"],
                        verified=row["policy_status"] == "published",
                        source_url=row.get("source_url"),
                        as_of=row.get("last_checked"),
                        last_checked=row.get("last_checked"),
                        demo_available=row["task_id"]
                        == "kakaobank.limit_account_release",
                    )
            except Exception:
                # The checked-in demo remains available during DB maintenance.
                pass
        return sorted(tasks.values(), key=lambda task: task.task_id)

    def get_task(self, task_id: str, *, purpose_code: str | None = None) -> TaskSummary:
        for task in self.list_tasks():
            if task.task_id == task_id:
                return task.model_copy(update={"purpose_code": purpose_code})
        raise LookupError(task_id)

    def _load_task(self, path: Path) -> TaskSummary:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            task_id = str(payload["task_id"])
            return TaskSummary(
                task_id=task_id,
                label_ko=payload["label_ko"],
                bank_code=payload["bank_code"],
                bank_name_ko=payload.get("bank_name_ko"),
                policy_key=payload["policy_key"],
                operation_code=payload.get("operation_code") or payload["policy_key"],
                channel=payload["channel"],
                visitor_type=payload["visitor_type"],
                verified=bool(payload.get("verified", False)),
                source_url=payload.get("source_url"),
                as_of=payload.get("as_of"),
                last_checked=payload.get("last_checked"),
                demo_available=(task_id == "kakaobank.limit_account_release"),
            )
        except (OSError, KeyError, json.JSONDecodeError, ValidationError) as error:
            raise TaskCatalogError(f"invalid task catalog file: {path.name}") from error
