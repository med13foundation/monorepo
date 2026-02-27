"""AI configuration testing endpoints for admin data sources."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.services import DataSourceAiTestService
from src.routes.admin_routes.dependencies import get_data_source_ai_test_service
from src.type_definitions.data_sources import DataSourceAiTestResult

router = APIRouter()


@router.post(
    "/{source_id}/ai/test",
    response_model=DataSourceAiTestResult,
    summary="Test AI configuration",
    description="Run a lightweight AI query test for the configured data source.",
)
async def test_ai_configuration(
    source_id: UUID,
    service: DataSourceAiTestService = Depends(get_data_source_ai_test_service),
) -> DataSourceAiTestResult:
    """Execute a non-destructive AI configuration test."""
    try:
        return await service.test_ai_configuration(source_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


__all__ = ["router"]
