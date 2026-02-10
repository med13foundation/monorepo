"""
Kernel observation application service.

Validates observations against the dictionary, normalises units
via the transform registry, and writes typed facts.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )
    from src.domain.repositories.kernel.observation_repository import (
        KernelObservationRepository,
    )
    from src.models.database.kernel.observations import ObservationModel

logger = logging.getLogger(__name__)


class KernelObservationService:
    """
    Application service for kernel observations.

    Validates variable existence, normalizes units via the transform
    registry, and writes typed observations.
    """

    def __init__(
        self,
        observation_repo: KernelObservationRepository,
        dictionary_repo: DictionaryRepository,
    ) -> None:
        self._observations = observation_repo
        self._dictionary = dictionary_repo

    # ── Write ─────────────────────────────────────────────────────────

    def record_observation(  # noqa: PLR0913
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
        """
        Record a single observation with validation.

        1. Validates that the variable_id exists in the dictionary
        2. Normalises the unit via the transform registry (if applicable)
        3. Writes the observation
        """
        # 1. Validate variable exists
        variable = self._dictionary.get_variable(variable_id)
        if variable is None:
            msg = f"Unknown variable_id: {variable_id}"
            raise ValueError(msg)

        # 2. Normalise unit via transform registry
        normalised_unit = unit
        if unit and variable.preferred_unit and unit != variable.preferred_unit:
            transform = self._dictionary.get_transform(unit, variable.preferred_unit)
            if transform:
                normalised_unit = variable.preferred_unit
                logger.debug(
                    "Normalised unit %s → %s for variable %s",
                    unit,
                    normalised_unit,
                    variable_id,
                )

        return self._observations.create(
            study_id=study_id,
            subject_id=subject_id,
            variable_id=variable_id,
            value_numeric=value_numeric,
            value_text=value_text,
            value_date=value_date,
            value_coded=value_coded,
            value_json=value_json,
            unit=normalised_unit,
            observed_at=observed_at,
            provenance_id=provenance_id,
            confidence=confidence,
        )

    def record_batch(
        self,
        observations: list[dict[str, object]],
    ) -> int:
        """
        Bulk-insert observations.

        Each dict follows the same schema as ``record_observation()``.
        Skips full validation for batch performance — use for trusted ingestion.
        """
        return self._observations.create_batch(observations)

    # ── Read ──────────────────────────────────────────────────────────

    def get_observation(self, observation_id: str) -> ObservationModel | None:
        """Retrieve a single observation."""
        return self._observations.get_by_id(observation_id)

    def get_subject_observations(
        self,
        subject_id: str,
        *,
        variable_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ObservationModel]:
        """All observations for a given entity."""
        return self._observations.find_by_subject(
            subject_id,
            variable_id=variable_id,
            limit=limit,
            offset=offset,
        )

    def get_study_observations(
        self,
        study_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ObservationModel]:
        """Paginated listing of all observations in a study."""
        return self._observations.find_by_study(
            study_id,
            limit=limit,
            offset=offset,
        )

    # ── Delete ────────────────────────────────────────────────────────

    def delete_observation(self, observation_id: str) -> bool:
        """Delete a single observation."""
        return self._observations.delete(observation_id)

    def rollback_provenance(self, provenance_id: str) -> int:
        """Delete all observations linked to a provenance record."""
        return self._observations.delete_by_provenance(provenance_id)


__all__ = ["KernelObservationService"]
