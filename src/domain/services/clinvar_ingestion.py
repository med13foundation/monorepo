"""Domain contracts for ClinVar ingestion orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID  # noqa: TCH003

from src.domain.entities.data_source_configs import ClinVarQueryConfig  # noqa: TCH001
from src.type_definitions.common import RawRecord  # noqa: TCH001


class ClinVarGateway(Protocol):
    """Protocol describing infrastructure responsibilities for ClinVar ingestion."""

    async def fetch_records(self, config: ClinVarQueryConfig) -> list[RawRecord]:
        """Fetch raw ClinVar records according to per-source configuration."""


@dataclass(frozen=True)
class ClinVarIngestionSummary:
    """Aggregate statistics about a ClinVar ingestion run."""

    source_id: UUID
    fetched_records: int
    parsed_publications: int
    created_publications: int
    updated_publications: int
    created_publication_ids: tuple[int, ...] = ()
    updated_publication_ids: tuple[int, ...] = ()
    executed_query: str | None = None
