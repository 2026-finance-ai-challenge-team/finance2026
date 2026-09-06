"""ProofBridge FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .analysis_service import DocumentClassificationPipeline
from .catalog import TaskCatalog
from .config import Settings
from .contracts import ErrorDetail, ErrorResponse
from .errors import ApiError
from .routers import analysis, health, tasks
from .sessions import SessionStore
from .task_resolution import TaskResolver


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    app = FastAPI(
        title="FORM:E API",
        version="0.1.0",
        description=(
            "공식 출처 기반 규칙으로 금융업무 증빙 준비 상태를 점검하는 "
            "FORM:E의 HTTP 경계입니다."
        ),
    )
    app.state.settings = runtime_settings
    app.state.catalog = TaskCatalog(
        runtime_settings.repo_root,
        runtime_settings.database_url,
    )
    app.state.sessions = SessionStore()
    app.state.analysis_pipeline = DocumentClassificationPipeline(runtime_settings)
    app.state.task_resolver = TaskResolver(
        settings=runtime_settings,
        supported_task_ids={task.task_id for task in app.state.catalog.list_tasks()},
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime_settings.cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition"],
    )

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, error: ApiError) -> JSONResponse:
        payload = ErrorResponse(
            error=ErrorDetail(
                code=error.code,
                message=error.message,
                recovery=error.recovery,
            )
        )
        return JSONResponse(status_code=error.status_code, content=payload.model_dump())

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(tasks.router, prefix="/api/v1")
    app.include_router(analysis.router, prefix="/api/v1")
    return app


app = create_app()
