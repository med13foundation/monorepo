"""
Provenance application service.

Provides a clean API for creating and querying provenance records
that link observations/relations to their data origin.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.repositories.kernel.provenance_repository import (
        ProvenanceRepository,
    )
    from src.models.database.kernel.provenance import ProvenanceModel
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


class ProvenanceService:
    """
    Application service for provenance tracking.

    Every ingestion or manual data entry should create a provenance
    record before writing observations/relations.
    """

    def __init__(self, provenance_repo: ProvenanceRepository) -> None:
        self._provenance = provenance_repo

    def create_provenance(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_type: str,
        source_ref: str | None = None,
        extraction_run_id: str | None = None,
        mapping_method: str | None = None,
        mapping_confidence: float | None = None,
        agent_model: str | None = None,
        raw_input: JSONObject | None = None,
    ) -> ProvenanceModel:
        """Create a provenance record for a data ingestion batch."""
        return self._provenance.create(
            research_space_id=research_space_id,
            source_type=source_type,
            source_ref=source_ref,
            extraction_run_id=extraction_run_id,
            mapping_method=mapping_method,
            mapping_confidence=mapping_confidence,
            agent_model=agent_model,
            raw_input=raw_input,
        )

    def get_provenance(self, provenance_id: str) -> ProvenanceModel | None:
        """Retrieve a single provenance record."""
        return self._provenance.get_by_id(provenance_id)

    def list_by_research_space(
        self,
        research_space_id: str,
        *,
        source_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ProvenanceModel]:
        """List provenance records for a research space."""
        return self._provenance.find_by_research_space(
            research_space_id,
            source_type=source_type,
            limit=limit,
            offset=offset,
        )

    def find_by_extraction_run(
        self,
        extraction_run_id: str,
    ) -> list[ProvenanceModel]:
        """Find provenance records for an extraction run."""
        return self._provenance.find_by_extraction_run(extraction_run_id)


__all__ = ["ProvenanceService"]
