"""
Value type caster for the ingestion pipeline.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.infrastructure.ingestion.types import (
        IngestedValue,
        MappedObservation,
        NormalizedObservation,
    )


class ValueCaster:
    """Casts raw values to target types based on dictionary definitions."""

    def __init__(self, dictionary_repository: DictionaryPort) -> None:
        self.dictionary_repo = dictionary_repository

    def cast(  # noqa: C901, PLR0911, PLR0912
        self,
        observation: MappedObservation | NormalizedObservation,
    ) -> IngestedValue:
        """
        Cast the value of an observation to the target data type.

        Complexity ignored for this method as it's a central dispatch for types.
        """
        variable_id = observation.variable_id
        definition = self.dictionary_repo.get_variable(variable_id)
        if not definition:
            # If no definition, return as is (or maybe str?)
            return observation.value

        value = observation.value
        target_type = definition.data_type

        try:
            if target_type == "INTEGER":
                return int(float(value)) if value is not None else None  # type: ignore[arg-type]
            if target_type == "FLOAT":
                return float(value) if value is not None else None  # type: ignore[arg-type]
            if target_type == "BOOLEAN":
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes", "t")
                return bool(value)
            if target_type == "STRING":
                return str(value) if value is not None else None
            if target_type == "DATE":
                # Naive date parsing
                if isinstance(value, datetime):
                    return value.date()
                return datetime.fromisoformat(str(value)).date()
            if target_type == "DATETIME":
                if isinstance(value, datetime):
                    return value
                return datetime.fromisoformat(str(value))
            if target_type == "CODED":
                return str(value)  # Coded values are usually strings

            return value  # noqa: TRY300, PLR1711
        except (ValueError, TypeError, json.JSONDecodeError):
            # Casting failed

            # We could return None, raise an error, or keep original
            # For now, let's log/raise or return None to indicate failure
            # returning None might be safest for pipeline
            return None
