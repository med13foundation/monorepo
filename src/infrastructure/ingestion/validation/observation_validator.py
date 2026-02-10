"""
Observation validator for the ingestion pipeline.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.ingestion.types import IngestedValue, NormalizedObservation

if TYPE_CHECKING:
    from src.domain.entities.kernel.dictionary import VariableDefinition
    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )

logger = logging.getLogger(__name__)


class ObservationValidator:
    """
    Validates normalized observations against dictionary constraints.
    """

    def __init__(self, dictionary_repository: DictionaryRepository) -> None:
        self.dictionary_repo = dictionary_repository

    def validate(self, observation: NormalizedObservation) -> bool:
        """
        Validate an observation against the variable definition constraints.
        """
        variable = self.dictionary_repo.get_variable(observation.variable_id)
        if not variable:
            logger.warning(
                "Variable %s not found in dictionary",
                observation.variable_id,
            )
            return False

        return self._validate_value_type(
            observation.value,
            variable,
        ) and self._validate_constraints(observation.value, variable)

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

    def _validate_constraints(
        self,
        value: IngestedValue,
        variable: VariableDefinition,
    ) -> bool:
        constraints = variable.constraints
        if not constraints:
            return True

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
                    return False
                if (
                    max_val is not None
                    and isinstance(max_val, int | float)
                    and isinstance(value, int | float)
                    and value > max_val
                ):
                    return False

            # Handle enums for CODED/STRING
            allowed_values_obj = constraints.get("allowed_values")
            if isinstance(allowed_values_obj, list) and value not in allowed_values_obj:
                return False

            # Handle regex pattern
            pattern = constraints.get("pattern")
            if pattern and variable.data_type == "STRING":
                # import re; if not re.match(pattern, value): return False
                pass

        except Exception:
            logger.exception("Error validating constraints for %s", variable.id)
            return False

        return True
