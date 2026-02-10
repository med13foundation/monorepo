"""
Kernel observation application service.

Validates observations against the dictionary, normalises units
via the transform registry, and writes typed facts.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
    from src.domain.repositories.kernel.observation_repository import (
        KernelObservationRepository,
    )
    from src.models.database.kernel.observations import ObservationModel
    from src.type_definitions.common import JSONValue

logger = logging.getLogger(__name__)


class _ObservationSlotKwargs(TypedDict, total=False):
    value_numeric: float
    value_text: str
    value_date: datetime | date
    value_coded: str
    value_boolean: bool
    value_json: JSONValue


class KernelObservationService:
    """
    Application service for kernel observations.

    Validates variable existence, normalizes units via the transform
    registry, and writes typed observations.
    """

    def __init__(
        self,
        observation_repo: KernelObservationRepository,
        entity_repo: KernelEntityRepository,
        dictionary_repo: DictionaryRepository,
    ) -> None:
        self._observations = observation_repo
        self._entities = entity_repo
        self._dictionary = dictionary_repo

    # ── Write ─────────────────────────────────────────────────────────

    def _ensure_subject_in_space(
        self,
        *,
        research_space_id: str,
        subject_id: str,
    ) -> None:
        subject = self._entities.get_by_id(subject_id)
        if subject is None:
            msg = f"Subject entity {subject_id} not found"
            raise ValueError(msg)
        if str(subject.research_space_id) != str(research_space_id):
            msg = f"Subject entity {subject_id} is not in research space {research_space_id}"
            raise ValueError(msg)

    def _normalise_value_date(
        self,
        value_date: datetime | date | None,
    ) -> datetime | None:
        if value_date is None:
            return None
        # datetime is a subclass of date, so check datetime first
        if isinstance(value_date, datetime):
            return value_date
        # Convert date to a UTC midnight timestamp
        return datetime(
            value_date.year,
            value_date.month,
            value_date.day,
            tzinfo=UTC,
        )

    def _expected_slot_for_data_type(self, data_type: str) -> str:
        if data_type in ("INTEGER", "FLOAT"):
            return "value_numeric"
        mapping = {
            "STRING": "value_text",
            "DATE": "value_date",
            "CODED": "value_coded",
            "BOOLEAN": "value_boolean",
            "JSON": "value_json",
        }
        if data_type not in mapping:
            msg = f"Unsupported variable data_type: {data_type}"
            raise ValueError(msg)
        return mapping[data_type]

    def _coerce_numeric_slot(
        self,
        *,
        variable_id: str,
        data_type: str,
        value: JSONValue | datetime | date,
    ) -> _ObservationSlotKwargs:
        if isinstance(value, bool) or not isinstance(value, int | float):
            msg = f"Variable {variable_id} expects a numeric value"
            raise TypeError(msg)
        numeric_value = float(value)
        if data_type == "INTEGER" and not numeric_value.is_integer():
            msg = f"Variable {variable_id} expects an integer numeric value"
            raise ValueError(msg)
        return {"value_numeric": numeric_value}

    def _coerce_boolean_slot(
        self,
        *,
        variable_id: str,
        value: JSONValue | datetime | date,
    ) -> _ObservationSlotKwargs:
        if not isinstance(value, bool):
            msg = f"Variable {variable_id} expects a boolean value"
            raise TypeError(msg)
        return {"value_boolean": value}

    def _coerce_date_slot(
        self,
        *,
        variable_id: str,
        value: JSONValue | datetime | date,
    ) -> _ObservationSlotKwargs:
        if not isinstance(value, datetime | date):
            msg = f"Variable {variable_id} expects a date/datetime value"
            raise TypeError(msg)
        return {"value_date": value}

    def _coerce_text_slot(
        self,
        *,
        variable_id: str,
        value: JSONValue | datetime | date,
    ) -> _ObservationSlotKwargs:
        if not isinstance(value, str):
            msg = f"Variable {variable_id} expects a string value"
            raise TypeError(msg)
        return {"value_text": value}

    def _coerce_coded_slot(
        self,
        *,
        variable_id: str,
        value: JSONValue | datetime | date,
    ) -> _ObservationSlotKwargs:
        if not isinstance(value, str):
            msg = f"Variable {variable_id} expects a coded (string) value"
            raise TypeError(msg)
        return {"value_coded": value}

    def _coerce_json_slot(
        self,
        *,
        variable_id: str,
        value: JSONValue | datetime | date,
    ) -> _ObservationSlotKwargs:
        # JSONB can store primitives/lists/dicts, but not Python date/datetime objects.
        if isinstance(value, datetime | date):
            msg = f"Variable {variable_id} expects a JSON value, not a date/datetime"
            raise TypeError(msg)
        return {"value_json": value}

    def _coerce_value_for_data_type(
        self,
        *,
        variable_id: str,
        data_type: str,
        value: JSONValue | datetime | date,
    ) -> _ObservationSlotKwargs:
        if value is None:
            msg = f"Observation value for variable {variable_id} cannot be null"
            raise ValueError(msg)

        if data_type in ("INTEGER", "FLOAT"):
            return self._coerce_numeric_slot(
                variable_id=variable_id,
                data_type=data_type,
                value=value,
            )

        handlers = {
            "BOOLEAN": self._coerce_boolean_slot,
            "DATE": self._coerce_date_slot,
            "STRING": self._coerce_text_slot,
            "CODED": self._coerce_coded_slot,
            "JSON": self._coerce_json_slot,
        }
        handler = handlers.get(data_type)
        if handler is None:
            msg = f"Unsupported variable data_type: {data_type}"
            raise ValueError(msg)

        return handler(variable_id=variable_id, value=value)

    def record_observation(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        subject_id: str,
        variable_id: str,
        value_numeric: float | None = None,
        value_text: str | None = None,
        value_date: datetime | date | None = None,
        value_coded: str | None = None,
        value_boolean: bool | None = None,
        value_json: JSONValue | None = None,
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
        # 0. Validate subject exists and is within the research space
        self._ensure_subject_in_space(
            research_space_id=research_space_id,
            subject_id=subject_id,
        )

        # 1. Validate variable exists
        variable = self._dictionary.get_variable(variable_id)
        if variable is None:
            msg = f"Unknown variable_id: {variable_id}"
            raise ValueError(msg)

        # 1b. Validate exactly one typed value slot is populated and matches the variable type
        data_type = variable.data_type

        normalised_value_date = self._normalise_value_date(value_date)
        expected_slot = self._expected_slot_for_data_type(data_type)

        slot_values: dict[str, object | None] = {
            "value_numeric": value_numeric,
            "value_text": value_text,
            "value_date": normalised_value_date,
            "value_coded": value_coded,
            "value_boolean": value_boolean,
            "value_json": value_json,
        }
        populated_slots = [k for k, v in slot_values.items() if v is not None]
        if len(populated_slots) != 1:
            msg = (
                "Observations must populate exactly one value slot "
                f"(got {len(populated_slots)})"
            )
            raise ValueError(msg)

        if populated_slots[0] != expected_slot:
            msg = (
                f"Variable {variable_id} expects {expected_slot} "
                f"but got {populated_slots[0]}"
            )
            raise ValueError(msg)

        if (
            data_type == "INTEGER"
            and value_numeric is not None
            and (
                isinstance(value_numeric, bool) or not float(value_numeric).is_integer()
            )
        ):
            msg = f"Variable {variable_id} expects an integer numeric value"
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
            research_space_id=research_space_id,
            subject_id=subject_id,
            variable_id=variable_id,
            value_numeric=value_numeric,
            value_text=value_text,
            value_date=normalised_value_date,
            value_coded=value_coded,
            value_boolean=value_boolean,
            value_json=value_json,
            unit=normalised_unit,
            observed_at=observed_at,
            provenance_id=provenance_id,
            confidence=confidence,
        )

    def record_observation_value(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        subject_id: str,
        variable_id: str,
        value: JSONValue | datetime | date,
        unit: str | None = None,
        observed_at: datetime | None = None,
        provenance_id: str | None = None,
        confidence: float = 1.0,
    ) -> ObservationModel:
        """
        Record an observation by providing a single value.

        The dictionary variable's ``data_type`` determines which typed
        value slot (numeric/text/date/coded/boolean/json) is used.
        """
        variable = self._dictionary.get_variable(variable_id)
        if variable is None:
            msg = f"Unknown variable_id: {variable_id}"
            raise ValueError(msg)

        data_type = variable.data_type
        slot_kwargs: _ObservationSlotKwargs = self._coerce_value_for_data_type(
            variable_id=variable_id,
            data_type=data_type,
            value=value,
        )
        return self.record_observation(
            research_space_id=research_space_id,
            subject_id=subject_id,
            variable_id=variable_id,
            unit=unit,
            observed_at=observed_at,
            provenance_id=provenance_id,
            confidence=confidence,
            **slot_kwargs,
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

    def get_research_space_observations(
        self,
        research_space_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ObservationModel]:
        """Paginated listing of all observations in a research space."""
        return self._observations.find_by_research_space(
            research_space_id,
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
