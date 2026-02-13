"""Shared contracts for ingestion scheduling and orchestration."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID  # noqa: TCH003


class IngestionRunSummary(Protocol):
    """Protocol describing the summary returned by source ingestion services."""

    @property
    def source_id(self) -> UUID:
        """Source identifier for the ingestion run."""

    @property
    def fetched_records(self) -> int:
        """Number of raw records fetched from upstream."""

    @property
    def parsed_publications(self) -> int:
        """Number of publications parsed by the ingestion pipeline."""

    @property
    def created_publications(self) -> int:
        """Number of publication records created."""

    @property
    def updated_publications(self) -> int:
        """Number of publication records updated."""

    @property
    def created_publication_ids(self) -> tuple[int, ...]:
        """Publication IDs created during ingestion."""

    @property
    def updated_publication_ids(self) -> tuple[int, ...]:
        """Publication IDs updated during ingestion."""

    @property
    def executed_query(self) -> str | None:
        """Source query string when available."""
