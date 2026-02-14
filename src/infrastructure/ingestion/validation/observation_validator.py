"""
Observation validator for the ingestion pipeline.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

from src.infrastructure.ingestion.types import NormalizedObservation

if TYPE_CHECKING:
    from src.domain.entities.kernel.dictionary import VariableDefinition
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.infrastructure.ingestion.types import IngestedValue

logger = logging.getLogger(__name__)


class ObservationValidator:
    """
    Validates normalized observations against dictionary constraints.
    """

    def __init__(self, dictionary_repository: DictionaryPort) -> None:
        self.dictionary_repo = dictionary_repository

    def validate(
        self,
        observation: NormalizedObservation,
    ) -> NormalizedObservation | None:
        """
        Validate an observation against the variable definition constraints.
        """
        variable = self.dictionary_repo.get_variable(observation.variable_id)
        if not variable:
            logger.warning(
                "Variable %s not found in dictionary",
                observation.variable_id,
            )
            return None

        if not self._validate_value_type(
            observation.value,
            variable,
        ):
            return None

        is_valid, normalized_coded_value = self._validate_constraints(
            observation.value,
            variable,
        )
        if not is_valid:
            return None

        if normalized_coded_value is None:
            return observation

        return NormalizedObservation(
            subject_anchor=observation.subject_anchor,
            variable_id=observation.variable_id,
            value=normalized_coded_value,
            unit=observation.unit,
            observed_at=observation.observed_at,
            provenance=observation.provenance,
        )

    def _validate_value_type(
        self,
        value: IngestedValue,
        variable: VariableDefinition,
    ) -> bool:
        # ValueCaster should already cast based on dictionary definitions, but we
        # validate again to ensure we never persist an invalid type.
        if value is None:
            return False

        data_type = variable.data_type

        is_valid = True
        if data_type in ("INTEGER", "FLOAT"):
            # bool is an int subclass; reject it explicitly.
            is_valid = isinstance(value, int | float) and not isinstance(value, bool)
        elif data_type == "BOOLEAN":
            is_valid = isinstance(value, bool)
        elif data_type in ("STRING", "CODED"):
            is_valid = isinstance(value, str)
        elif data_type == "DATE":
            is_valid = isinstance(value, date | datetime)
        elif data_type == "JSON":
            # JSON values may be primitives, lists, or dicts; we rely on the mapper
            # and dictionary for shape constraints.
            is_valid = True
        else:
            # Unknown types are treated permissively for now.
            is_valid = True

        return is_valid

    def _validate_constraints(  # noqa: C901, PLR0911
        self,
        value: IngestedValue,
        variable: VariableDefinition,
    ) -> tuple[bool, str | None]:
        constraints = variable.constraints
        normalized_coded_value: str | None = None

        if variable.data_type == "CODED":
            coded_valid, normalized_coded_value = self._validate_coded_value_set(
                value=value,
                variable_id=variable.id,
            )
            if not coded_valid:
                return False, None

        if not constraints:
            return True, normalized_coded_value

        try:
            # Handle min/max for numbers
            if variable.data_type in ("INTEGER", "FLOAT"):
                min_val = constraints.get("min")
                max_val = constraints.get("max")

                if (
                    min_val is not None
                    and isinstance(min_val, int | float)
                    and isinstance(value, int | float)
                    and value < min_val
                ):
                    return False, None
                if (
                    max_val is not None
                    and isinstance(max_val, int | float)
                    and isinstance(value, int | float)
                    and value > max_val
                ):
                    return False, None

            # Handle legacy enums for STRING and CODED variables without value sets.
            if variable.data_type == "STRING" or (
                variable.data_type == "CODED" and normalized_coded_value is None
            ):
                allowed_values_obj = constraints.get("allowed_values")
                if (
                    isinstance(allowed_values_obj, list)
                    and value not in allowed_values_obj
                ):
                    return False, None

            # Handle regex pattern
            pattern = constraints.get("pattern")
            if pattern and variable.data_type == "STRING":
                # import re; if not re.match(pattern, value): return False
                pass

        except Exception:
            logger.exception("Error validating constraints for %s", variable.id)
            return False, None

        return True, normalized_coded_value

    def _validate_coded_value_set(
        self,
        *,
        value: IngestedValue,
        variable_id: str,
    ) -> tuple[bool, str | None]:
        """
        Validate CODED values against active value-set items when configured.

        Returns:
            - (True, canonical_code) when matched by canonical code or synonym.
            - (True, None) when no value set exists for the variable.
            - (False, None) when value sets exist but no active match is found.
        """
        value_sets = self.dictionary_repo.list_value_sets(variable_id=variable_id)
        if not value_sets:
            return True, None

        active_value_sets = [
            value_set for value_set in value_sets if value_set.review_status == "ACTIVE"
        ]
        if not active_value_sets:
            logger.warning(
                "Variable %s has no active value set available for CODED validation",
                variable_id,
            )
            return False, None

        if not isinstance(value, str) or not value.strip():
            return False, None

        lookup_value = value.strip().casefold()
        for value_set in active_value_sets:
            items = self.dictionary_repo.list_value_set_items(
                value_set_id=value_set.id,
                include_inactive=False,
            )
            for item in items:
                if item.review_status != "ACTIVE":
                    continue
                if lookup_value == item.code.casefold():
                    return True, item.code
                for synonym in item.synonyms:
                    if lookup_value == synonym.casefold():
                        return True, item.code

        return False, None
