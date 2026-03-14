"""Health endpoints for the standalone graph API service."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from services.graph_api.config import get_settings
from src.graph.product_contract import GRAPH_SERVICE_VERSION

router = APIRouter(tags=["health"])


class GraphHealthResponse(BaseModel):
    """Basic service health response."""

    model_config = ConfigDict(strict=True)

    status: str
    service: str
    version: str


@router.get("/health", response_model=GraphHealthResponse, summary="Health check")
def health_check() -> GraphHealthResponse:
    """Return liveness information for the graph service."""
    settings = get_settings()
    return GraphHealthResponse(
        status="ok",
        service=settings.app_name,
        version=GRAPH_SERVICE_VERSION,
    )


__all__ = ["GraphHealthResponse", "health_check", "router"]
