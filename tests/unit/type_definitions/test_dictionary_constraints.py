"""Unit tests for dictionary constraint models and helper functions."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from src.type_definitions.dictionary import (
    BooleanConstraints,
    CodedConstraints,
    DateConstraints,
    JsonConstraints,
    NumericConstraints,
    StringConstraints,
    get_constraint_schema_for_data_type,
    is_value_compatible_with_data_type,
    normalize_dictionary_data_type,
    validate_constraints_for_data_type,
    value_satisfies_dictionary_constraints,
)
from src.type_definitions.json_utils import to_json_value

_SUPPORTED_DATA_TYPES: tuple[str, ...] = (
    "INTEGER",
    "FLOAT",
    "STRING",
    "DATE",
    "CODED",
    "BOOLEAN",
    "JSON",
)

_EMPTY_CONSTRAINTS_BY_TYPE: dict[str, dict[str, object]] = {
    "INTEGER": {},
    "FLOAT": {},
    "STRING": {},
    "DATE": {},
    "CODED": {"allow_other": False},
    "BOOLEAN": {},
    "JSON": {},
}


def test_numeric_constraints_model_accepts_valid_payload() -> None:
    model = NumericConstraints(min=0, max=10, precision=2)
    assert model.min == 0
    assert model.max == 10
    assert model.precision == 2


def test_numeric_constraints_model_rejects_invalid_range() -> None:
    with pytest.raises(ValidationError, match="min must be less than or equal to max"):
        NumericConstraints(min=10, max=1)


def test_string_constraints_model_accepts_pattern_and_bounds() -> None:
    model = StringConstraints(min_length=1, max_length=64, pattern=r"^MED13$")
    assert model.min_length == 1
    assert model.max_length == 64
    assert model.pattern == r"^MED13$"


def test_string_constraints_model_rejects_invalid_length_range() -> None:
    with pytest.raises(
        ValidationError,
        match="min_length must be less than or equal to max_length",
    ):
        StringConstraints(min_length=10, max_length=2)


def test_coded_constraints_model_accepts_value_set_and_allow_other() -> None:
    model = CodedConstraints(value_set_id="VS_CLINVAR_CLASS", allow_other=True)
    assert model.value_set_id == "VS_CLINVAR_CLASS"
    assert model.allow_other is True


def test_date_constraints_model_accepts_date_only_and_z_suffix() -> None:
    model = DateConstraints(
        min_date="2025-01-01",
        max_date="2025-01-01T00:00:00Z",
    )
    assert model.min_date == "2025-01-01"
    assert model.max_date == "2025-01-01T00:00:00Z"


def test_date_constraints_model_rejects_range_after_timezone_normalization() -> None:
    with pytest.raises(
        ValidationError,
        match="min_date must be less than or equal to max_date",
    ):
        DateConstraints(
            min_date="2025-01-01T02:00:00+00:00",
            max_date="2024-12-31T23:30:00-02:00",
        )


def test_boolean_constraints_model_accepts_empty_payload() -> None:
    model = BooleanConstraints()
    assert model.model_dump(mode="json", exclude_none=True) == {}


def test_json_constraints_model_accepts_json_schema() -> None:
    model = JsonConstraints(
        json_schema={
            "type": "object",
            "properties": {"score": {"type": "number"}},
            "required": ["score"],
        },
    )
    assert model.json_schema is not None
    assert model.json_schema["type"] == "object"


@pytest.mark.parametrize(
    ("model_type", "payload"),
    [
        (NumericConstraints, {"unexpected": 1}),
        (StringConstraints, {"unexpected": 1}),
        (CodedConstraints, {"unexpected": 1}),
        (DateConstraints, {"unexpected": 1}),
        (BooleanConstraints, {"unexpected": 1}),
        (JsonConstraints, {"unexpected": 1}),
    ],
)
def test_constraint_models_forbid_extra_fields(
    model_type: type[
        NumericConstraints
        | StringConstraints
        | CodedConstraints
        | DateConstraints
        | BooleanConstraints
        | JsonConstraints
    ],
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        model_type.model_validate(payload)


@pytest.mark.parametrize(
    ("data_type", "constraints", "expected"),
    [
        (
            "INTEGER",
            {"min": 0, "max": 10, "precision": 2},
            {"min": 0.0, "max": 10.0, "precision": 2},
        ),
        (
            "FLOAT",
            {"min": 0.1, "max": 0.2, "precision": 3},
            {"min": 0.1, "max": 0.2, "precision": 3},
        ),
        (
            "STRING",
            {"min_length": 1, "max_length": 32, "pattern": r"^abc$"},
            {"min_length": 1, "max_length": 32, "pattern": r"^abc$"},
        ),
        (
            "DATE",
            {"min_date": "2025-01-01", "max_date": "2025-12-31T00:00:00Z"},
            {"min_date": "2025-01-01", "max_date": "2025-12-31T00:00:00Z"},
        ),
        (
            "CODED",
            {"value_set_id": "VS_TEST", "allow_other": True},
            {"value_set_id": "VS_TEST", "allow_other": True},
        ),
        ("BOOLEAN", {}, {}),
        (
            "JSON",
            {"json_schema": {"type": "object"}},
            {"json_schema": {"type": "object"}},
        ),
    ],
)
def test_validate_constraints_for_all_supported_data_types(
    data_type: str,
    constraints: dict[str, object],
    expected: dict[str, object],
) -> None:
    validated = validate_constraints_for_data_type(
        data_type=data_type,
        constraints={
            str(key): to_json_value(value) for key, value in constraints.items()
        },
    )
    assert validated == {
        str(key): to_json_value(value) for key, value in expected.items()
    }


@pytest.mark.parametrize("data_type", _SUPPORTED_DATA_TYPES)
@pytest.mark.parametrize("constraints", [{}, None])
def test_validate_constraints_allows_empty_or_none_for_all_data_types(
    data_type: str,
    constraints: dict[str, object] | None,
) -> None:
    payload = (
        {str(key): to_json_value(value) for key, value in constraints.items()}
        if constraints is not None
        else None
    )
    validated = validate_constraints_for_data_type(
        data_type=data_type,
        constraints=payload,
    )
    assert validated == _EMPTY_CONSTRAINTS_BY_TYPE[data_type]


@pytest.mark.parametrize(
    ("data_type", "constraints"),
    [
        ("INTEGER", {"unexpected": True}),
        ("FLOAT", {"unexpected": True}),
        ("STRING", {"unexpected": True}),
        ("DATE", {"unexpected": True}),
        ("CODED", {"unexpected": True}),
        ("BOOLEAN", {"unexpected": True}),
        ("JSON", {"unexpected": True}),
    ],
)
def test_validate_constraints_rejects_extra_fields_for_all_data_types(
    data_type: str,
    constraints: dict[str, object],
) -> None:
    with pytest.raises(
        ValueError,
        match=f"Invalid constraints for data_type '{data_type}'",
    ):
        validate_constraints_for_data_type(
            data_type=data_type,
            constraints={
                str(key): to_json_value(value) for key, value in constraints.items()
            },
        )


def test_validate_constraints_accepts_date_comparison_with_timezone_equivalence() -> (
    None
):
    validated = validate_constraints_for_data_type(
        data_type="DATE",
        constraints={
            "min_date": "2025-01-01T00:00:00Z",
            "max_date": "2024-12-31T19:00:00-05:00",
        },
    )
    assert validated == {
        "min_date": "2025-01-01T00:00:00Z",
        "max_date": "2024-12-31T19:00:00-05:00",
    }


def test_validate_constraints_rejects_unsupported_data_type() -> None:
    with pytest.raises(ValueError, match="Unsupported data_type"):
        validate_constraints_for_data_type(
            data_type="VECTOR",
            constraints={},
        )


@pytest.mark.parametrize(
    ("raw_data_type", "expected"),
    [
        ("integer", "INTEGER"),
        (" FLOAT ", "FLOAT"),
        ("sTrInG", "STRING"),
        ("date", "DATE"),
        ("coded", "CODED"),
        ("boolean", "BOOLEAN"),
        ("json", "JSON"),
    ],
)
def test_normalize_dictionary_data_type(
    raw_data_type: str,
    expected: str,
) -> None:
    assert normalize_dictionary_data_type(raw_data_type) == expected


@pytest.mark.parametrize(
    ("data_type", "expected_properties"),
    [
        ("INTEGER", {"min", "max", "precision"}),
        ("FLOAT", {"min", "max", "precision"}),
        ("STRING", {"min_length", "max_length", "pattern"}),
        ("DATE", {"min_date", "max_date"}),
        ("CODED", {"value_set_id", "allow_other"}),
        ("BOOLEAN", set()),
        ("JSON", {"json_schema"}),
    ],
)
def test_get_constraint_schema_for_data_type(
    data_type: str,
    expected_properties: set[str],
) -> None:
    schema = get_constraint_schema_for_data_type(data_type)
    assert schema.get("type") == "object"
    assert schema.get("additionalProperties") is False
    properties = schema.get("properties")
    assert isinstance(properties, dict)
    assert set(properties.keys()) == expected_properties


def test_get_constraint_schema_returns_deep_copy() -> None:
    first = get_constraint_schema_for_data_type("INTEGER")
    second = get_constraint_schema_for_data_type("INTEGER")
    assert first == second

    first_properties = first.get("properties")
    assert isinstance(first_properties, dict)
    first_properties["new_field"] = {"type": "string"}

    refreshed = get_constraint_schema_for_data_type("INTEGER")
    refreshed_properties = refreshed.get("properties")
    assert isinstance(refreshed_properties, dict)
    assert "new_field" not in refreshed_properties


def test_get_constraint_schema_unknown_type_returns_empty_dict() -> None:
    assert get_constraint_schema_for_data_type("VECTOR") == {}


def test_is_value_compatible_with_data_type_supports_all_core_types() -> None:
    assert is_value_compatible_with_data_type(data_type="INTEGER", value=3)
    assert not is_value_compatible_with_data_type(data_type="INTEGER", value=3.2)
    assert is_value_compatible_with_data_type(data_type="FLOAT", value=3.2)
    assert is_value_compatible_with_data_type(data_type="BOOLEAN", value=True)
    assert is_value_compatible_with_data_type(data_type="STRING", value="abc")
    assert is_value_compatible_with_data_type(data_type="DATE", value=date(2025, 1, 1))
    assert is_value_compatible_with_data_type(
        data_type="JSON",
        value={"score": 0.8, "labels": ["a", "b"]},
    )


def test_value_satisfies_dictionary_constraints_enforces_numeric_bounds_and_precision() -> (
    None
):
    assert value_satisfies_dictionary_constraints(
        data_type="FLOAT",
        constraints={"min": 0.0, "max": 1.0, "precision": 2},
        value=0.75,
    )
    assert not value_satisfies_dictionary_constraints(
        data_type="FLOAT",
        constraints={"min": 0.0, "max": 1.0, "precision": 2},
        value=1.5,
    )
    assert not value_satisfies_dictionary_constraints(
        data_type="FLOAT",
        constraints={"min": 0.0, "max": 1.0, "precision": 2},
        value=0.123,
    )


def test_value_satisfies_dictionary_constraints_enforces_string_pattern_and_length() -> (
    None
):
    constraints = {"min_length": 3, "max_length": 5, "pattern": r"^[A-Z]+$"}
    assert value_satisfies_dictionary_constraints(
        data_type="STRING",
        constraints=constraints,
        value="ABCD",
    )
    assert not value_satisfies_dictionary_constraints(
        data_type="STRING",
        constraints=constraints,
        value="ab",
    )
    assert not value_satisfies_dictionary_constraints(
        data_type="STRING",
        constraints=constraints,
        value="abcdef",
    )


def test_value_satisfies_dictionary_constraints_enforces_date_window() -> None:
    constraints = {"min_date": "2025-01-01", "max_date": "2025-12-31"}
    assert value_satisfies_dictionary_constraints(
        data_type="DATE",
        constraints=constraints,
        value=datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC),
    )
    assert not value_satisfies_dictionary_constraints(
        data_type="DATE",
        constraints=constraints,
        value=date(2024, 12, 31),
    )


def test_value_satisfies_dictionary_constraints_applies_json_schema() -> None:
    constraints = {
        "json_schema": {
            "type": "object",
            "properties": {"score": {"type": "number"}},
            "required": ["score"],
        },
    }
    assert value_satisfies_dictionary_constraints(
        data_type="JSON",
        constraints=constraints,
        value={"score": 0.2},
    )
    assert not value_satisfies_dictionary_constraints(
        data_type="JSON",
        constraints=constraints,
        value={"missing": True},
    )


def test_value_satisfies_dictionary_constraints_supports_legacy_allowed_values() -> (
    None
):
    constraints = {"allowed_values": ["A", "B"]}
    assert value_satisfies_dictionary_constraints(
        data_type="STRING",
        constraints=constraints,
        value="A",
    )
    assert not value_satisfies_dictionary_constraints(
        data_type="STRING",
        constraints=constraints,
        value="C",
    )
    assert not value_satisfies_dictionary_constraints(
        data_type="STRING",
        constraints=constraints,
        value="A",
        allow_legacy_allowed_values=False,
    )
