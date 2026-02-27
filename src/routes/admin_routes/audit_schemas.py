"""Pydantic schemas for admin audit log APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.type_definitions.common import JSONValue


class AuditLogResponse(BaseModel):
    """Serialized audit log entry."""

    id: int
    action: str
    entity_type: str
    entity_id: str
    user: str | None = None
    request_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    success: bool | None = None
    details: JSONValue | None = None
    created_at: str | None = None


class AuditLogListResponse(BaseModel):
    """Paginated audit log response."""

    logs: list[AuditLogResponse]
    total: int
    page: int
    per_page: int


class AuditLogRetentionRunRequest(BaseModel):
    """Manual retention cleanup request."""

    retention_days: int = Field(default=2190, ge=1)
    batch_size: int = Field(default=1000, ge=1, le=10000)


class AuditLogRetentionRunResponse(BaseModel):
    """Manual retention cleanup response."""

    deleted_rows: int
    retention_days: int
    batch_size: int


class AuditLogQueryParams(BaseModel):
    """Validated query filters for list/export endpoints."""

    action: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    actor_id: str | None = None
    request_id: str | None = None
    ip_address: str | None = None
    success: bool | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=50, ge=1, le=500)
    export_limit: int = Field(default=10000, ge=1, le=50000)
    export_format: Literal["json", "csv"] = "json"
