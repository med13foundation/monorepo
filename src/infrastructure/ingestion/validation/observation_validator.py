"""
Observation validator for the ingestion pipeline.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.ingestion.types import IngestedValue, NormalizedObservation

if TYPE_CHECKING:
    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )
    from src.models.database.kernel.dictionary import VariableDefinitionModel

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
        _variable: VariableDefinitionModel,
    ) -> bool:
        # Basic type checks are done by ValueCaster, but we can double check
        # or check specific requirements (e.g. non-null)

        # Check if variable allows nulls?
        # For observations, usually a value is required.
        return value is not None

    def _validate_constraints(
        self,
        value: IngestedValue,
        variable: VariableDefinitionModel,
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
            allowed_values: list[IngestedValue] | None = constraints.get(
                "allowed_values",
            )  # type: ignore[assignment]
            if allowed_values and value not in allowed_values:
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
