"""
Dictionary constraint schemas and validators.

Phase 5 introduces typed constraint validation for variable definitions.
This module centralizes:
1) Pydantic models for each supported dictionary data type.
2) JSON Schema payloads stored in dictionary_data_types.constraint_schema.
3) Write-time constraint normalization/validation helpers.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from src.type_definitions.common import JSONObject  # noqa: TC001
from src.type_definitions.json_utils import to_json_value

_SUPPORTED_DATA_TYPES: Final[frozenset[str]] = frozenset(
    {
        "INTEGER",
        "FLOAT",
        "STRING",
        "DATE",
        "CODED",
        "BOOLEAN",
        "JSON",
    },
)
_DATA_TYPE_ALIASES: Final[dict[str, str]] = {
    "TEXT": "STRING",
    "STR": "STRING",
    "INT": "INTEGER",
    "LONG": "INTEGER",
    "DOUBLE": "FLOAT",
    "DECIMAL": "FLOAT",
    "NUMBER": "FLOAT",
    "BOOL": "BOOLEAN",
    "OBJECT": "JSON",
    "MAP": "JSON",
    "DICT": "JSON",
    "STRUCT": "JSON",
    "ARRAY": "JSON",
    "LIST": "JSON",
}


class _BaseConstraints(BaseModel):
    """Base model for dictionary constraints with strict key enforcement."""

    model_config = ConfigDict(extra="forbid")


class NumericConstraints(_BaseConstraints):
    """Constraints for INTEGER/FLOAT variables."""

    min: float | None = None
    max: float | None = None
    precision: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> NumericConstraints:
        if (
            self.min is not None
            and self.max is not None
            and float(self.min) > float(self.max)
        ):
            msg = "min must be less than or equal to max"
            raise ValueError(msg)
        return self


class StringConstraints(_BaseConstraints):
    """Constraints for STRING variables."""

    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, ge=0)
    pattern: str | None = None

    @model_validator(mode="after")
    def validate_lengths(self) -> StringConstraints:
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            msg = "min_length must be less than or equal to max_length"
            raise ValueError(msg)
        return self


class CodedConstraints(_BaseConstraints):
    """Constraints for CODED variables."""

    value_set_id: str | None = Field(default=None, min_length=1, max_length=64)
    allow_other: bool = False


def _parse_iso_temporal(value: str) -> datetime:
    normalized = value.strip()
    if not normalized:
        msg = "ISO-8601 value cannot be empty"
        raise ValueError(msg)

    with_offset = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(with_offset)
    except ValueError:
        parsed_date = date.fromisoformat(normalized)
        parsed = datetime.combine(parsed_date, datetime.min.time())

    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


class DateConstraints(_BaseConstraints):
    """Constraints for DATE variables."""

    min_date: str | None = None
    max_date: str | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> DateConstraints:
        parsed_min = (
            _parse_iso_temporal(self.min_date) if self.min_date is not None else None
        )
        parsed_max = (
            _parse_iso_temporal(self.max_date) if self.max_date is not None else None
        )
        if (
            parsed_min is not None
            and parsed_max is not None
            and parsed_min > parsed_max
        ):
            msg = "min_date must be less than or equal to max_date"
            raise ValueError(msg)
        return self


class BooleanConstraints(_BaseConstraints):
    """Constraints for BOOLEAN variables (no extra fields)."""


class JsonConstraints(_BaseConstraints):
    """Constraints for JSON variables."""

    json_schema: JSONObject | None = None


_CONSTRAINT_SCHEMA_BY_DATA_TYPE: Final[dict[str, JSONObject]] = {
    "INTEGER": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "min": {"type": "number"},
            "max": {"type": "number"},
            "precision": {"type": "integer", "minimum": 0},
        },
    },
    "FLOAT": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "min": {"type": "number"},
            "max": {"type": "number"},
            "precision": {"type": "integer", "minimum": 0},
        },
    },
    "STRING": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "min_length": {"type": "integer", "minimum": 0},
            "max_length": {"type": "integer", "minimum": 0},
            "pattern": {"type": "string"},
        },
    },
    "DATE": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "min_date": {"type": "string"},
            "max_date": {"type": "string"},
        },
    },
    "CODED": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "value_set_id": {"type": "string"},
            "allow_other": {"type": "boolean"},
        },
    },
    "BOOLEAN": {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
    },
    "JSON": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "json_schema": {"type": "object"},
        },
    },
}

_CONSTRAINT_MODEL_BY_DATA_TYPE: Final[dict[str, type[_BaseConstraints]]] = {
    "INTEGER": NumericConstraints,
    "FLOAT": NumericConstraints,
    "STRING": StringConstraints,
    "DATE": DateConstraints,
    "CODED": CodedConstraints,
    "BOOLEAN": BooleanConstraints,
    "JSON": JsonConstraints,
}


def normalize_dictionary_data_type(data_type: str) -> str:
    """Normalize a dictionary data type identifier."""
    normalized = data_type.strip().upper()
    if normalized in _SUPPORTED_DATA_TYPES:
        return normalized
    alias = _DATA_TYPE_ALIASES.get(normalized)
    if alias is not None:
        return alias
    if normalized.endswith(("_LIST", "_ARRAY")):
        return "JSON"
    return normalized


def get_constraint_schema_for_data_type(data_type: str) -> JSONObject:
    """Return the JSON schema payload for a dictionary data type."""
    normalized = normalize_dictionary_data_type(data_type)
    schema = _CONSTRAINT_SCHEMA_BY_DATA_TYPE.get(normalized)
    if schema is None:
        return {}
    return deepcopy(schema)


def validate_constraints_for_data_type(
    *,
    data_type: str,
    constraints: JSONObject | None,
) -> JSONObject:
    """
    Validate and normalize dictionary variable constraints by data type.

    Returns a JSON-safe normalized payload suitable for persistence.
    """
    normalized_data_type = normalize_dictionary_data_type(data_type)
    if normalized_data_type not in _SUPPORTED_DATA_TYPES:
        msg = f"Unsupported data_type '{data_type}'"
        raise ValueError(msg)

    payload = constraints or {}
    model_type = _CONSTRAINT_MODEL_BY_DATA_TYPE.get(normalized_data_type)
    if model_type is None:
        return payload

    try:
        validated = model_type.model_validate(payload)
    except ValidationError as exc:
        msg = f"Invalid constraints for data_type '{normalized_data_type}': {exc}"
        raise ValueError(msg) from exc

    dumped = validated.model_dump(mode="json", exclude_none=True)
    return {str(key): to_json_value(value) for key, value in dumped.items()}


__all__ = [
    "BooleanConstraints",
    "CodedConstraints",
    "DateConstraints",
    "JsonConstraints",
    "NumericConstraints",
    "StringConstraints",
    "get_constraint_schema_for_data_type",
    "normalize_dictionary_data_type",
    "validate_constraints_for_data_type",
]
