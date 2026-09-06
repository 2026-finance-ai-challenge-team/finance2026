"""PostgreSQL runtime connection helpers for ProofBridge."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol


class ResultLike(Protocol):
    def fetchone(self) -> Any: ...

    def fetchall(self) -> list[Any]: ...


class ConnectionLike(Protocol):
    def execute(
        self,
        query: str,
        parameters: tuple[Any, ...] = (),
    ) -> ResultLike: ...

    def close(self) -> None: ...


def database_url_from_env() -> str:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dependency installation concern
        load_dotenv = None
    if load_dotenv is not None:
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    database_url = (
        os.getenv("PROOFBRIDGE_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()
    if not database_url:
        raise RuntimeError(
            "PROOFBRIDGE_DATABASE_URL 환경변수에 PostgreSQL 접속 주소를 설정해야 합니다."
        )
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("ProofBridge는 PostgreSQL 접속 주소만 지원합니다.")
    return database_url


def connect_database(database_url: str | None = None) -> Any:
    """Open PostgreSQL with dictionary-shaped rows and qmark compatibility."""
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:  # pragma: no cover - deployment dependency
        raise RuntimeError(
            "PostgreSQL을 사용하려면 `pip install psycopg[binary]`가 필요합니다."
        ) from error

    connection = psycopg.connect(
        database_url or database_url_from_env(),
        row_factory=dict_row,
    )
    return PostgresConnection(connection)


class PostgresConnection:
    """Small DB-API adapter used by the existing policy repositories."""

    def __init__(self, connection: Any) -> None:
        self.raw = connection

    @staticmethod
    def _query(query: str) -> str:
        return query.replace("?", "%s")

    def execute(self, query: str, parameters: tuple[Any, ...] = ()) -> Any:
        return self.raw.execute(self._query(query), parameters)

    def executemany(self, query: str, parameters: list[tuple[Any, ...]]) -> Any:
        cursor = self.raw.cursor()
        cursor.executemany(self._query(query), parameters)
        return cursor

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()

    def __enter__(self) -> "PostgresConnection":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
