from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ..catalog import TaskCatalog
from ..contracts import (
    TaskResolutionRequest,
    TaskResolutionResponse,
    TaskRequirementsResponse,
    TaskSummary,
)
from ..dependencies import get_catalog, get_settings, get_task_resolver
from ..errors import ApiError
from ..config import Settings
from ..policy_service import (
    PolicyDataError,
    PolicySelectionRequired,
    PostgreSQLPolicyService,
)
from ..task_resolution import TaskResolver, TaskResolverUnavailable


router = APIRouter(tags=["tasks"])


@router.get("/tasks", response_model=list[TaskSummary])
def list_tasks(catalog: Annotated[TaskCatalog, Depends(get_catalog)]) -> list[TaskSummary]:
    return catalog.list_tasks()


@router.post("/tasks/resolve", response_model=TaskResolutionResponse)
def resolve_task(
    request: TaskResolutionRequest,
    resolver: Annotated[TaskResolver, Depends(get_task_resolver)],
) -> TaskResolutionResponse:
    try:
        return resolver.resolve(request.query)
    except TaskResolverUnavailable as error:
        raise ApiError(
            status_code=503,
            code="TASK_INDEX_UNAVAILABLE",
            message="업무 검색을 잠시 사용할 수 없어요.",
            recovery="잠시 후 다시 시도하거나 지원 업무 목록에서 직접 선택해주세요.",
        ) from error


@router.get("/tasks/{task_id}/requirements", response_model=TaskRequirementsResponse)
def get_task_requirements(
    task_id: str,
    catalog: Annotated[TaskCatalog, Depends(get_catalog)],
    settings: Annotated[Settings, Depends(get_settings)],
    purpose_code: Annotated[str | None, Query(max_length=100)] = None,
) -> TaskRequirementsResponse:
    """Return deadlines, acquisition links and preparations without uploads."""
    try:
        task = catalog.get_task(task_id, purpose_code=purpose_code)
    except LookupError as error:
        raise ApiError(
            status_code=404,
            code="TASK_NOT_FOUND",
            message="지원 작업을 찾을 수 없습니다.",
        ) from error

    service = PostgreSQLPolicyService(settings.database_url)
    try:
        context = service.load(task)
    except PolicySelectionRequired as error:
        raise ApiError(
            status_code=422,
            code="PURPOSE_REQUIRED",
            message="이 업무는 거래 목적을 먼저 선택해야 합니다.",
            recovery="급여·생활비·사업 등 해당하는 거래 목적을 선택해주세요.",
        ) from error
    except PolicyDataError as error:
        raise ApiError(
            status_code=503,
            code="POLICY_DATA_UNAVAILABLE",
            message="현재 업무의 검증된 정책 데이터를 읽을 수 없습니다.",
            recovery="잠시 후 다시 시도해주세요.",
        ) from error
    return service.describe(context=context, task=task)
