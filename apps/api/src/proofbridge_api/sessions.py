"""Process-local session metadata for the synthetic MVP path.

Uploaded source files are deliberately not stored here. A durable or multi-worker
deployment will replace this class with a repository that has the same operations.
"""

from __future__ import annotations

from threading import Lock
from uuid import UUID

from .contracts import AnalysisResponse


class SessionStore:
    def __init__(self) -> None:
        self._items: dict[UUID, AnalysisResponse] = {}
        self._lock = Lock()

    def put(self, result: AnalysisResponse) -> None:
        with self._lock:
            self._items[result.session_id] = result

    def get(self, session_id: UUID) -> AnalysisResponse | None:
        with self._lock:
            return self._items.get(session_id)

    def delete(self, session_id: UUID) -> bool:
        with self._lock:
            return self._items.pop(session_id, None) is not None
