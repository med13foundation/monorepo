"""
Provenance repository interface.

Defines the abstract contract for tracking data origin and
extraction details in the ``provenance`` table.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.kernel.provenance import KernelProvenanceRecord
    from src.type_definitions.common import JSONObject


class ProvenanceRepository(ABC):
    """
    Provenance tracking repository.

    Every ingestion, extraction, or manual data entry creates a
    provenance record linking observations/relations to their origin.
    """

    @abstractmethod
    def create(  # noqa: PLR0913
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
    ) -> KernelProvenanceRecord:
        """Create a provenance record for a data ingestion batch."""

    @abstractmethod
    def get_by_id(self, provenance_id: str) -> KernelProvenanceRecord | None:
        """Retrieve a single provenance record."""

    @abstractmethod
    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        source_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelProvenanceRecord]:
        """List provenance records for a research space, optionally filtered by source type."""

    @abstractmethod
    def find_by_extraction_run(
        self,
        extraction_run_id: str,
    ) -> list[KernelProvenanceRecord]:
        """Find all provenance records for a given extraction/ingestion run."""


__all__ = ["ProvenanceRepository"]
