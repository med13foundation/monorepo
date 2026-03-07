"""Query parameter schemas for admin Artana run explorer routes."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ArtanaRunListQueryParams(BaseModel):
    """Supported admin Artana run explorer filters."""

    model_config = ConfigDict(strict=True)

    q: str | None = None
    status: str | None = None
    space_id: str | None = None
    source_type: str | None = None
    alert_code: str | None = None
    since_hours: int | None = Field(default=None, ge=1, le=24 * 365)
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1, le=200)


__all__ = ["ArtanaRunListQueryParams"]
