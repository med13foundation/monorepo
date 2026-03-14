"""Health endpoints for the standalone harness service."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from services.graph_harness_api.config import get_settings

router = APIRouter(tags=["health"])


class HarnessHealthResponse(BaseModel):
    """Basic service health response."""

    model_config = ConfigDict(strict=True)

    status: str
    service: str
    version: str


@router.get("/health", response_model=HarnessHealthResponse, summary="Health check")
def health_check() -> HarnessHealthResponse:
    """Return liveness information for the harness service."""
    settings = get_settings()
    return HarnessHealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.version,
    )


__all__ = ["HarnessHealthResponse", "health_check", "router"]
