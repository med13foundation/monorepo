"""Infrastructure adapter for ClinVar record retrieval."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.services.clinvar_ingestion import ClinVarGateway
from src.infrastructure.ingest import ClinVarIngestor

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.domain.entities.data_source_configs import ClinVarQueryConfig
    from src.type_definitions.common import RawRecord


class ClinVarSourceGateway(ClinVarGateway):
    """ClinVar gateway backed by the infrastructure ClinVar ingestor."""

    def __init__(
        self,
        ingestor_factory: Callable[[], ClinVarIngestor] | None = None,
    ) -> None:
        self._ingestor_factory = ingestor_factory or ClinVarIngestor

    async def fetch_records(self, config: ClinVarQueryConfig) -> list[RawRecord]:
        """Fetch ClinVar records using normalized query configuration."""
        query_kwargs: dict[str, str | int] = {
            "gene_symbol": config.gene_symbol,
            "max_results": config.max_results,
        }
        if config.variation_types:
            # ClinVar ingestor accepts a single variation_type filter.
            query_kwargs["variation_type"] = config.variation_types[0]
        if config.clinical_significance:
            # ClinVar ingestor accepts a single clinical_significance filter.
            query_kwargs["clinical_significance"] = config.clinical_significance[0]

        ingestor = self._ingestor_factory()
        async with ingestor:
            return await ingestor.fetch_data(**query_kwargs)
