"""Environment-backed API configuration without secret disclosure."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _positive_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _probability(name: str, default: float) -> float:
    value = _positive_float(name, default)
    if value > 1.0:
        raise ValueError(f"{name} must be less than or equal to one")
    return value


def _origins(name: str) -> tuple[str, ...]:
    defaults = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    raw_value = os.getenv(name)
    if raw_value is None:
        return defaults
    return tuple(origin.strip().rstrip("/") for origin in raw_value.split(",") if origin.strip())


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded once by the app factory."""

    environment: str
    repo_root: Path
    max_upload_bytes: int
    max_upload_files: int
    session_temp_root: Path
    ocr_timeout_seconds: float
    ocr_invoke_url: str | None
    ocr_secret_key: str | None
    cors_allowed_origins: tuple[str, ...] = ()
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4-mini"
    llm_timeout_seconds: float = 20.0
    llm_min_confidence: float = 0.85
    database_url: str | None = None

    @property
    def ocr_configured(self) -> bool:
        return bool(self.ocr_invoke_url and self.ocr_secret_key)

    @property
    def llm_configured(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.strip())

    @classmethod
    def from_env(cls) -> "Settings":
        default_repo_root = Path(__file__).resolve().parents[4]
        repo_root = Path(
            os.getenv("PROOFBRIDGE_REPO_ROOT", str(default_repo_root))
        ).resolve()
        default_session_temp_root = Path(tempfile.gettempdir()) / "proofbridge-sessions"
        configured_session_temp_root = os.getenv("PROOFBRIDGE_SESSION_TEMP_ROOT", "")
        session_temp_root = Path(
            configured_session_temp_root.strip() or default_session_temp_root
        ).resolve()
        return cls(
            environment=os.getenv("PROOFBRIDGE_ENV", "development"),
            repo_root=repo_root,
            max_upload_bytes=_positive_int(
                "PROOFBRIDGE_MAX_UPLOAD_BYTES", 10 * 1024 * 1024
            ),
            max_upload_files=_positive_int("PROOFBRIDGE_MAX_UPLOAD_FILES", 10),
            session_temp_root=session_temp_root,
            ocr_timeout_seconds=_positive_float("PROOFBRIDGE_OCR_TIMEOUT_SECONDS", 30.0),
            ocr_invoke_url=os.getenv("NCP_OCR_INVOKE_URL"),
            ocr_secret_key=os.getenv("NCP_OCR_SECRET_KEY"),
            cors_allowed_origins=_origins("PROOFBRIDGE_CORS_ORIGINS"),
            openai_base_url=(os.getenv("OPENAI_BASE_URL") or "").strip() or None,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model=os.getenv("PROOFBRIDGE_OPENAI_MODEL", "gpt-5.4-mini"),
            llm_timeout_seconds=_positive_float(
                "PROOFBRIDGE_LLM_TIMEOUT_SECONDS", 20.0
            ),
            llm_min_confidence=_probability(
                "PROOFBRIDGE_LLM_MIN_CONFIDENCE", 0.85
            ),
            database_url=(
                os.getenv("PROOFBRIDGE_DATABASE_URL")
                or os.getenv("DATABASE_URL")
                or ""
            ).strip()
            or None,
        )
