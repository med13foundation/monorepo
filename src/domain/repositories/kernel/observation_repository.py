"""
Kernel observation repository interface.

Defines the abstract contract for typed fact (EAV) reads and writes
against the ``observations`` table.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from src.models.database.kernel.observations import ObservationModel


class KernelObservationRepository(ABC):
    """
    Typed observation (fact) repository.

    Every observation links a subject entity to a variable definition
    with a typed value slot (numeric, text, date, coded, or JSON).
    """

    # ── Write ─────────────────────────────────────────────────────────

    @abstractmethod
    def create(  # noqa: PLR0913
        self,
        *,
        study_id: str,
        subject_id: str,
        variable_id: str,
        value_numeric: float | None = None,
        value_text: str | None = None,
        value_date: datetime | None = None,
        value_coded: str | None = None,
        value_json: dict[str, object] | None = None,
        unit: str | None = None,
        observed_at: datetime | None = None,
        provenance_id: str | None = None,
        confidence: float = 1.0,
    ) -> ObservationModel:
        """Create a single observation with the appropriate value slot."""

    @abstractmethod
    def create_batch(
        self,
        observations: list[dict[str, object]],
    ) -> int:
        """
        Bulk-insert observations.

        Each dict must contain the same keys as ``create()``.
        Returns the number of rows inserted.
        """

    # ── Read ──────────────────────────────────────────────────────────

    @abstractmethod
    def get_by_id(self, observation_id: str) -> ObservationModel | None:
        """Retrieve a single observation by primary key."""

    @abstractmethod
    def find_by_subject(
        self,
        subject_id: str,
        *,
        variable_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ObservationModel]:
        """All observations for a given entity, optionally filtered by variable."""

    @abstractmethod
    def find_by_variable(
        self,
        study_id: str,
        variable_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ObservationModel]:
        """All observations for a given variable across all entities in a study."""

    @abstractmethod
    def find_by_study(
        self,
        study_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ObservationModel]:
        """Paginated listing of all observations in a study."""

    # ── Delete ────────────────────────────────────────────────────────

    @abstractmethod
    def delete(self, observation_id: str) -> bool:
        """Delete a single observation."""

    @abstractmethod
    def delete_by_provenance(self, provenance_id: str) -> int:
        """
        Delete all observations linked to a provenance record.

        Useful for rolling back an entire ingestion batch.
        Returns the number of deleted rows.
        """


__all__ = ["KernelObservationRepository"]
