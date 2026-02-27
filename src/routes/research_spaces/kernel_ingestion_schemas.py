"""Pydantic schemas for space-scoped ingestion execution routes."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SpaceSourceIngestionRunResponse(BaseModel):
    """Result for a single source ingestion run."""

    model_config = ConfigDict(strict=True)

    source_id: UUID
    source_name: str = Field(..., min_length=1, max_length=200)
    status: Literal["completed", "skipped", "failed"]
    message: str | None = None
    fetched_records: int = 0
    parsed_publications: int = 0
    created_publications: int = 0
    updated_publications: int = 0
    executed_query: str | None = None


class SpaceRunActiveSourcesResponse(BaseModel):
    """Summary for running all active sources in a space."""

    model_config = ConfigDict(strict=True)

    total_sources: int
    active_sources: int
    runnable_sources: int
    completed_sources: int
    skipped_sources: int
    failed_sources: int
    runs: list[SpaceSourceIngestionRunResponse]


__all__ = [
    "SpaceRunActiveSourcesResponse",
    "SpaceSourceIngestionRunResponse",
]
