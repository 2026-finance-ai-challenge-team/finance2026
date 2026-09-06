from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ..config import Settings
from ..contracts import HealthResponse
from ..dependencies import get_settings


router = APIRouter(tags=["operations"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(
        version="0.1.0",
        environment=settings.environment,
        ocr_configured=settings.ocr_configured,
        llm_configured=settings.llm_configured,
    )
