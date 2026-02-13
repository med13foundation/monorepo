"""Shared contracts for ingestion scheduling and orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID  # noqa: TCH003

from src.type_definitions.common import JSONObject  # noqa: TC001

if TYPE_CHECKING:
    from src.domain.entities.source_sync_state import SourceSyncState
    from src.domain.repositories.source_record_ledger_repository import (
        SourceRecordLedgerRepository,
    )


@dataclass(frozen=True)
class IngestionRunContext:
    """Context passed by scheduler to source ingestion services."""

    ingestion_job_id: UUID
    source_sync_state: SourceSyncState
    query_signature: str
    source_record_ledger_repository: SourceRecordLedgerRepository | None = None


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

    @property
    def query_signature(self) -> str | None:
        """Hash of normalized query/config used for this run."""

    @property
    def checkpoint_before(self) -> JSONObject | None:
        """Checkpoint payload before this run started."""

    @property
    def checkpoint_after(self) -> JSONObject | None:
        """Checkpoint payload after this run completed."""

    @property
    def checkpoint_kind(self) -> str | None:
        """Checkpoint mechanism used for this run (cursor/timestamp/etc)."""

    @property
    def new_records(self) -> int:
        """Number of new upstream records this run observed."""

    @property
    def updated_records(self) -> int:
        """Number of changed upstream records this run observed."""

    @property
    def unchanged_records(self) -> int:
        """Number of upstream records skipped as unchanged."""

    @property
    def skipped_records(self) -> int:
        """Number of skipped records for scheduling metrics."""
