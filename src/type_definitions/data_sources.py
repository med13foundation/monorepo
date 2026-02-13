"""
Data source type definitions for MED13 Resource Library.

Provides typed contracts for data source testing results.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import TypedDict
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject  # noqa: TC001


class DataSourceAiTestLink(BaseModel):
    """Reference link to a finding surfaced during AI testing."""

    model_config = ConfigDict(extra="forbid")

    label: str
    url: str


class DataSourceAiTestFinding(BaseModel):
    """Lightweight finding record surfaced during AI test execution."""

    model_config = ConfigDict(extra="forbid")

    title: str
    pubmed_id: str | None = None
    doi: str | None = None
    pmc_id: str | None = None
    publication_date: str | None = None
    journal: str | None = None
    links: list[DataSourceAiTestLink] = Field(default_factory=list)


class FlujoTableSummary(BaseModel):
    """Summary of Flujo table rows recorded during a run."""

    model_config = ConfigDict(extra="forbid")

    table_name: str
    row_count: int = Field(ge=0)
    latest_created_at: datetime | None = None
    sample_rows: list[JSONObject] = Field(default_factory=list)


class DataSourceAiTestResult(BaseModel):
    """Result payload from testing an AI-managed data source configuration."""

    model_config = ConfigDict(extra="forbid")

    source_id: UUID
    model: str | None = None
    success: bool
    message: str
    executed_query: str | None = None
    search_terms: list[str] = Field(default_factory=list)
    fetched_records: int = Field(ge=0)
    sample_size: int = Field(ge=1)
    findings: list[DataSourceAiTestFinding] = Field(default_factory=list)
    checked_at: datetime
    flujo_run_id: str | None = None
    flujo_tables: list[FlujoTableSummary] = Field(default_factory=list)


class SourceCatalogEntrySeed(TypedDict, total=False):
    """Typed seed data for source catalog entries."""

    id: str
    name: str
    description: str
    category: str
    param_type: str
    url_template: str
    api_endpoint: str
    tags: list[str]
    is_active: bool
    requires_auth: bool
    source_type: str
    query_capabilities: JSONObject


__all__ = [
    "DataSourceAiTestFinding",
    "DataSourceAiTestLink",
    "DataSourceAiTestResult",
    "FlujoTableSummary",
    "SourceCatalogEntrySeed",
]
