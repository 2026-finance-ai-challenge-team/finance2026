from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status

from ..analysis_service import (
    AnalysisPipeline,
    UploadBoundaryError,
    apply_user_classification,
)
from ..catalog import TaskCatalog
from ..config import Settings
from ..contracts import (
    AnalysisResponse,
    DeleteSessionResponse,
    DocumentClassificationUpdate,
)
from ..demo import build_demo_result
from ..dependencies import (
    get_analysis_pipeline,
    get_catalog,
    get_session_store,
    get_settings,
)
from ..errors import ApiError
from ..policy_service import PolicyDataError, PolicySelectionRequired
from ..preparation_kit import build_preparation_kit
from ..sessions import SessionStore


router = APIRouter(tags=["analysis"])

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
}


async def _close_uploads(files: list[UploadFile]) -> None:
    for upload in files:
        await upload.close()


@router.post("/demo", response_model=AnalysisResponse)
def create_demo(
    catalog: Annotated[TaskCatalog, Depends(get_catalog)],
    sessions: Annotated[SessionStore, Depends(get_session_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalysisResponse:
    task = catalog.get_task("kakaobank.limit_account_release")
    result = build_demo_result(settings.repo_root, task)
    sessions.put(result)
    return result


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Pipeline unavailable"}},
)
async def analyze(
    task_id: Annotated[str, Form(min_length=1)],
    files: Annotated[list[UploadFile], File(min_length=1)],
    settings: Annotated[Settings, Depends(get_settings)],
    catalog: Annotated[TaskCatalog, Depends(get_catalog)],
    pipeline: Annotated[AnalysisPipeline, Depends(get_analysis_pipeline)],
    sessions: Annotated[SessionStore, Depends(get_session_store)],
    owner_name: Annotated[str | None, Form(max_length=100)] = None,
    purpose_code: Annotated[str | None, Form(max_length=100)] = None,
) -> AnalysisResponse:
    try:
        task = catalog.get_task(task_id, purpose_code=purpose_code)
    except LookupError as error:
        await _close_uploads(files)
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="TASK_NOT_FOUND",
            message="지원 작업을 찾을 수 없습니다.",
        ) from error

    if len(files) > settings.max_upload_files:
        await _close_uploads(files)
        raise ApiError(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            code="TOO_MANY_FILES",
            message="한 번에 업로드할 수 있는 파일 수를 초과했습니다.",
            recovery=f"파일을 {settings.max_upload_files}개 이하로 줄여주세요.",
        )

    try:
        oversized = [
            upload.filename or "unnamed"
            for upload in files
            if upload.size is not None and upload.size > settings.max_upload_bytes
        ]
        if oversized:
            raise ApiError(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                code="FILE_TOO_LARGE",
                message="업로드 파일의 허용 크기를 초과했습니다.",
                recovery=f"각 파일을 {settings.max_upload_bytes}바이트 이하로 줄여주세요.",
            )
        unsupported = [
            upload.filename or "unnamed"
            for upload in files
            if upload.content_type not in _ALLOWED_CONTENT_TYPES
        ]
        if unsupported:
            raise ApiError(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                code="UNSUPPORTED_MEDIA_TYPE",
                message="지원하지 않는 파일 형식입니다.",
                recovery="PDF, JPG 또는 PNG 파일을 사용해주세요.",
            )

        try:
            result = await pipeline.analyze(
                task=task,
                files=files,
                expected_owner_name=owner_name,
            )
            sessions.put(result)
            return result
        except UploadBoundaryError as error:
            raise ApiError(
                status_code=(
                    status.HTTP_413_CONTENT_TOO_LARGE
                    if error.code == "FILE_TOO_LARGE"
                    else status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
                ),
                code=error.code,
                message=error.message,
                recovery=error.recovery,
            ) from error
        except PolicySelectionRequired as error:
            raise ApiError(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="PURPOSE_REQUIRED",
                message="이 업무는 거래 목적을 먼저 선택해야 합니다.",
                recovery="급여·생활비·사업 등 해당하는 거래 목적을 선택해주세요.",
            ) from error
        except PolicyDataError as error:
            raise ApiError(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="POLICY_DATA_UNAVAILABLE",
                message="현재 업무의 검증된 정책 데이터를 읽을 수 없습니다.",
                recovery="잠시 후 다시 시도해주세요.",
            ) from error
    finally:
        await _close_uploads(files)


@router.get("/sessions/{session_id}", response_model=AnalysisResponse)
def get_session(
    session_id: UUID,
    sessions: Annotated[SessionStore, Depends(get_session_store)],
) -> AnalysisResponse:
    result = sessions.get(session_id)
    if result is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="SESSION_NOT_FOUND",
            message="분석 세션을 찾을 수 없습니다.",
        )
    return result


@router.patch(
    "/sessions/{session_id}/documents/{document_id}/classification",
    response_model=AnalysisResponse,
)
def update_document_classification(
    session_id: UUID,
    document_id: str,
    update: DocumentClassificationUpdate,
    sessions: Annotated[SessionStore, Depends(get_session_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalysisResponse:
    current = sessions.get(session_id)
    if current is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="SESSION_NOT_FOUND",
            message="분석 세션을 찾을 수 없습니다.",
        )
    try:
        result = apply_user_classification(
            current=current,
            document_id=document_id,
            doc_type=update.doc_type,
            settings=settings,
        )
    except KeyError as error:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="DOCUMENT_NOT_FOUND",
            message="확인할 문서를 찾을 수 없습니다.",
        ) from error
    except LookupError as error:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="DOCUMENT_TYPE_NOT_ALLOWED",
            message="현재 정책에서 지원하지 않는 문서 종류입니다.",
            recovery="목록에 있는 문서 종류를 선택해주세요.",
        ) from error
    sessions.put(result)
    return result


@router.get("/sessions/{session_id}/preparation-kit")
def download_preparation_kit(
    session_id: UUID,
    sessions: Annotated[SessionStore, Depends(get_session_store)],
) -> Response:
    result = sessions.get(session_id)
    if result is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="SESSION_NOT_FOUND",
            message="준비 키트를 만들 분석 세션을 찾을 수 없습니다.",
        )
    filename = f"proofbridge-preparation-kit-{session_id}.zip"
    return Response(
        content=build_preparation_kit(result),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/sessions/{session_id}", response_model=DeleteSessionResponse)
def delete_session(
    session_id: UUID,
    sessions: Annotated[SessionStore, Depends(get_session_store)],
) -> DeleteSessionResponse:
    return DeleteSessionResponse(session_id=session_id, deleted=sessions.delete(session_id))
