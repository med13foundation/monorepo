"""Skill builders for extraction validation and transform lookup."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.value_objects.relation_types import normalize_relation_type
from src.infrastructure.ingestion.types import NormalizedObservation
from src.infrastructure.ingestion.validation.observation_validator import (
    ObservationValidator,
)
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.domain.ports.dictionary_port import DictionaryPort
    from src.type_definitions.common import JSONObject, JSONValue
else:
    type JSONObject = dict[str, object]
    type JSONValue = object


def _to_json_payload(value: object) -> JSONObject:
    dump_method = getattr(value, "model_dump", None)
    if callable(dump_method):
        dumped = dump_method(mode="json")
        if isinstance(dumped, dict):
            return {
                str(key): to_json_value(payload_value)
                for key, payload_value in dumped.items()
            }
    return {"value": to_json_value(value)}


def make_validate_observation_tool(
    *,
    dictionary_service: DictionaryPort,
    **_: object,
) -> Callable[[str, JSONValue, str | None], JSONObject]:
    """Build a tool callable for observation validation."""
    validator = ObservationValidator(dictionary_service)

    def validate_observation(
        variable_id: str,
        value: JSONValue,
        unit: str | None = None,
    ) -> JSONObject:
        """
        Validate one observation candidate against dictionary constraints.

        Returns validity plus canonical normalization details when available.
        """
        normalized = validator.validate(
            NormalizedObservation(
                subject_anchor={},
                variable_id=variable_id,
                value=value,
                unit=unit,
                observed_at=None,
                provenance={},
            ),
        )
        if normalized is None:
            return {
                "valid": False,
                "variable_id": variable_id,
                "reason": "Observation failed dictionary validation",
            }

        return {
            "valid": True,
            "variable_id": variable_id,
            "value": to_json_value(normalized.value),
            "unit": normalized.unit,
        }

    return validate_observation


def make_validate_triple_tool(
    *,
    dictionary_service: DictionaryPort,
    **_: object,
) -> Callable[[str, str, str], JSONObject]:
    """Build a tool callable for relation-triple validation."""

    def validate_triple(
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> JSONObject:
        """
        Validate a relation triple against dictionary relation constraints.
        """
        normalized_source_type = source_type.strip().upper()
        normalized_relation_type = normalize_relation_type(relation_type)
        normalized_target_type = target_type.strip().upper()
        if (
            not normalized_source_type
            or not normalized_relation_type
            or not normalized_target_type
        ):
            return {
                "allowed": False,
                "requires_evidence": True,
                "reason": "source_type, relation_type, and target_type are required",
            }
        allowed = dictionary_service.is_relation_allowed(
            source_type=normalized_source_type,
            relation_type=normalized_relation_type,
            target_type=normalized_target_type,
        )
        requires_evidence = dictionary_service.requires_evidence(
            source_type=normalized_source_type,
            relation_type=normalized_relation_type,
            target_type=normalized_target_type,
        )
        return {
            "allowed": allowed,
            "requires_evidence": requires_evidence,
            "source_type": normalized_source_type,
            "relation_type": normalized_relation_type,
            "target_type": normalized_target_type,
        }

    return validate_triple


def make_lookup_transform_tool(
    *,
    dictionary_service: DictionaryPort,
    **_: object,
) -> Callable[[str, str], JSONObject]:
    """Build a tool callable for transform lookup."""

    def lookup_transform(
        input_unit: str,
        output_unit: str,
    ) -> JSONObject:
        """
        Look up a registered transform between two units.
        """
        transform = dictionary_service.get_transform(
            input_unit,
            output_unit,
            require_production=True,
        )
        if transform is None:
            return {
                "found": False,
                "input_unit": input_unit,
                "output_unit": output_unit,
            }
        payload = _to_json_payload(transform)
        payload["found"] = True
        return payload

    return lookup_transform


__all__ = [
    "make_lookup_transform_tool",
    "make_validate_observation_tool",
    "make_validate_triple_tool",
]
