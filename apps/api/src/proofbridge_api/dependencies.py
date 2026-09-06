"""FastAPI dependency accessors."""

from __future__ import annotations

from typing import cast

from fastapi import Request

from .analysis_service import AnalysisPipeline
from .catalog import TaskCatalog
from .config import Settings
from .sessions import SessionStore
from .task_resolution import TaskResolver


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_catalog(request: Request) -> TaskCatalog:
    return cast(TaskCatalog, request.app.state.catalog)


def get_session_store(request: Request) -> SessionStore:
    return cast(SessionStore, request.app.state.sessions)


def get_analysis_pipeline(request: Request) -> AnalysisPipeline:
    return cast(AnalysisPipeline, request.app.state.analysis_pipeline)


def get_task_resolver(request: Request) -> TaskResolver:
    return cast(TaskResolver, request.app.state.task_resolver)
