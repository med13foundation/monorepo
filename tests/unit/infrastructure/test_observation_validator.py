"""Unit tests for value-set-aware observation validation."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from unittest.mock import Mock

from src.domain.entities.kernel.dictionary import (
    ValueSet,
    ValueSetItem,
    VariableDefinition,
)
from src.infrastructure.ingestion.types import NormalizedObservation
from src.infrastructure.ingestion.validation.observation_validator import (
    ObservationValidator,
)

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject


def _build_variable(
    *,
    data_type: str = "CODED",
    constraints: JSONObject | None = None,
) -> VariableDefinition:
    now = datetime.now(UTC)
    return VariableDefinition(
        id="VAR_CODED_STATUS",
        canonical_name="coded_status",
        display_name="Coded Status",
        data_type=data_type,
        preferred_unit=None,
        constraints=constraints or {},
        domain_context="general",
        sensitivity="INTERNAL",
        description=None,
        created_by="seed",
        source_ref=None,
        review_status="ACTIVE",
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        created_at=now,
        updated_at=now,
    )


def _build_value_set(*, value_set_id: str = "VS_CODED_STATUS") -> ValueSet:
    now = datetime.now(UTC)
    return ValueSet(
        id=value_set_id,
        variable_id="VAR_CODED_STATUS",
        variable_data_type="CODED",
        name="Coded statuses",
        description=None,
        external_ref=None,
        is_extensible=True,
        created_by="seed",
        source_ref=None,
        review_status="ACTIVE",
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        created_at=now,
        updated_at=now,
    )


def _build_value_set_item(
    *,
    code: str = "APPROVED",
    synonyms: list[str] | None = None,
) -> ValueSetItem:
    now = datetime.now(UTC)
    return ValueSetItem(
        id=1,
        value_set_id="VS_CODED_STATUS",
        code=code,
        display_label=code.title(),
        synonyms=synonyms or [],
        external_ref=None,
        sort_order=0,
        is_active=True,
        created_by="seed",
        source_ref=None,
        review_status="ACTIVE",
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        created_at=now,
        updated_at=now,
    )


def _build_observation(*, value: str) -> NormalizedObservation:
    return NormalizedObservation(
        subject_anchor={"hgnc_id": "HGNC:1234"},
        variable_id="VAR_CODED_STATUS",
        value=value,
        unit=None,
        observed_at=None,
        provenance={},
    )


def test_validate_accepts_canonical_code_with_value_set() -> None:
    dictionary_port = Mock()
    dictionary_port.get_variable.return_value = _build_variable(data_type="CODED")
    dictionary_port.list_value_sets.return_value = [_build_value_set()]
    dictionary_port.list_value_set_items.return_value = [_build_value_set_item()]

    validator = ObservationValidator(dictionary_port)
    validated = validator.validate(_build_observation(value="APPROVED"))

    assert validated is not None
    assert validated.value == "APPROVED"
    dictionary_port.list_value_set_items.assert_called_once_with(
        value_set_id="VS_CODED_STATUS",
        include_inactive=False,
    )


def test_validate_normalizes_synonym_to_canonical_code() -> None:
    dictionary_port = Mock()
    dictionary_port.get_variable.return_value = _build_variable(data_type="CODED")
    dictionary_port.list_value_sets.return_value = [_build_value_set()]
    dictionary_port.list_value_set_items.return_value = [
        _build_value_set_item(synonyms=["approved", "ok_to_use"]),
    ]

    validator = ObservationValidator(dictionary_port)
    validated = validator.validate(_build_observation(value="ok_to_use"))

    assert validated is not None
    assert validated.value == "APPROVED"


def test_validate_rejects_unknown_code_when_value_set_exists() -> None:
    dictionary_port = Mock()
    dictionary_port.get_variable.return_value = _build_variable(data_type="CODED")
    dictionary_port.list_value_sets.return_value = [_build_value_set()]
    dictionary_port.list_value_set_items.return_value = [_build_value_set_item()]

    validator = ObservationValidator(dictionary_port)
    validated = validator.validate(_build_observation(value="UNKNOWN"))

    assert validated is None


def test_validate_falls_back_to_allowed_values_without_value_set() -> None:
    dictionary_port = Mock()
    dictionary_port.get_variable.return_value = _build_variable(
        data_type="CODED",
        constraints={"allowed_values": ["A", "B"]},
    )
    dictionary_port.list_value_sets.return_value = []

    validator = ObservationValidator(dictionary_port)
    accepted = validator.validate(_build_observation(value="A"))
    rejected = validator.validate(_build_observation(value="C"))

    assert accepted is not None
    assert accepted.value == "A"
    assert rejected is None


def test_validate_enforces_string_pattern_and_length_constraints() -> None:
    dictionary_port = Mock()
    dictionary_port.get_variable.return_value = _build_variable(
        data_type="STRING",
        constraints={"min_length": 3, "max_length": 6, "pattern": r"^[A-Z]+$"},
    )

    validator = ObservationValidator(dictionary_port)
    accepted = validator.validate(_build_observation(value="VALID"))
    rejected_short = validator.validate(_build_observation(value="ab"))
    rejected_pattern = validator.validate(_build_observation(value="abcDEF"))

    assert accepted is not None
    assert rejected_short is None
    assert rejected_pattern is None


def test_validate_enforces_date_constraints() -> None:
    dictionary_port = Mock()
    dictionary_port.get_variable.return_value = _build_variable(
        data_type="DATE",
        constraints={"min_date": "2025-01-01", "max_date": "2025-12-31"},
    )

    validator = ObservationValidator(dictionary_port)
    accepted = validator.validate(
        NormalizedObservation(
            subject_anchor={"hgnc_id": "HGNC:1234"},
            variable_id="VAR_CODED_STATUS",
            value=date(2025, 6, 1),
            unit=None,
            observed_at=None,
            provenance={},
        ),
    )
    rejected = validator.validate(
        NormalizedObservation(
            subject_anchor={"hgnc_id": "HGNC:1234"},
            variable_id="VAR_CODED_STATUS",
            value=date(2024, 12, 1),
            unit=None,
            observed_at=None,
            provenance={},
        ),
    )

    assert accepted is not None
    assert rejected is None


def test_validate_allows_other_coded_values_when_allow_other_enabled() -> None:
    dictionary_port = Mock()
    dictionary_port.get_variable.return_value = _build_variable(
        data_type="CODED",
        constraints={"allow_other": True},
    )
    dictionary_port.list_value_sets.return_value = [_build_value_set()]
    dictionary_port.list_value_set_items.return_value = [_build_value_set_item()]

    validator = ObservationValidator(dictionary_port)
    validated = validator.validate(_build_observation(value="UNLISTED"))

    assert validated is not None
    assert validated.value == "UNLISTED"


def test_validate_uses_configured_value_set_id_for_coded_constraints() -> None:
    dictionary_port = Mock()
    dictionary_port.get_variable.return_value = _build_variable(
        data_type="CODED",
        constraints={"value_set_id": "VS_SECONDARY"},
    )
    dictionary_port.list_value_sets.return_value = [
        _build_value_set(value_set_id="VS_PRIMARY"),
        _build_value_set(value_set_id="VS_SECONDARY"),
    ]
    dictionary_port.list_value_set_items.return_value = [
        _build_value_set_item(code="APPROVED"),
    ]

    validator = ObservationValidator(dictionary_port)
    validated = validator.validate(_build_observation(value="APPROVED"))

    assert validated is not None
    assert validated.value == "APPROVED"
    dictionary_port.list_value_set_items.assert_called_once_with(
        value_set_id="VS_SECONDARY",
        include_inactive=False,
    )
