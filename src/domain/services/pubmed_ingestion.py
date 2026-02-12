"""Domain contracts for PubMed ingestion orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID  # noqa: TCH003

from src.domain.entities.data_source_configs import PubMedQueryConfig  # noqa: TCH001
from src.type_definitions.common import RawRecord  # noqa: TCH001


class PubMedGateway(Protocol):
    """Protocol describing infrastructure responsibilities for PubMed ingestion."""

    async def fetch_records(self, config: PubMedQueryConfig) -> list[RawRecord]:
        """Fetch raw PubMed records according to per-source configuration."""


@dataclass(frozen=True)
class PubMedIngestionSummary:
    """Aggregate statistics about a PubMed ingestion run."""

    source_id: UUID
    fetched_records: int
    parsed_publications: int
    created_publications: int
    updated_publications: int
    created_publication_ids: tuple[int, ...] = ()
    updated_publication_ids: tuple[int, ...] = ()
    executed_query: str | None = None
    query_generation_run_id: str | None = None
    query_generation_model: str | None = None
    query_generation_decision: str | None = None
    query_generation_confidence: float | None = None
