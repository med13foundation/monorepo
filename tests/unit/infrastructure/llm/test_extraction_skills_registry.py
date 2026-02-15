"""Tests for extraction skill registration and tool building."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import Mock

from src.domain.entities.kernel.dictionary import VariableDefinition
from src.infrastructure.llm.skills.registry import (
    build_extraction_validation_tools,
    get_skill_registry,
    register_all_skills,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _build_variable() -> VariableDefinition:
    now = datetime.now(UTC)
    return VariableDefinition(
        id="VAR_TEST",
        canonical_name="test",
        display_name="Test",
        data_type="STRING",
        preferred_unit=None,
        constraints={},
        domain_context="general",
        sensitivity="INTERNAL",
        description="Test variable",
        created_by="seed",
        source_ref=None,
        review_status="ACTIVE",
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        created_at=now,
        updated_at=now,
    )


def _tool_by_name(tools: list[object], name: str) -> Callable[..., object]:
    for tool in tools:
        tool_name = getattr(tool, "__name__", "")
        if tool_name == name and callable(tool):
            return tool
    msg = f"Tool '{name}' not found"
    raise AssertionError(msg)


def test_register_all_skills_includes_extraction_skills() -> None:
    register_all_skills()
    registry = get_skill_registry()
    available = set(registry.list_skills())
    assert "validate_observation" in available
    assert "validate_triple" in available
    assert "lookup_transform" in available


def test_build_extraction_tools_calls_dictionary_service() -> None:
    dictionary_service = Mock()
    dictionary_service.get_variable.return_value = _build_variable()
    dictionary_service.list_value_sets.return_value = []
    dictionary_service.is_relation_allowed.return_value = True
    dictionary_service.requires_evidence.return_value = True
    dictionary_service.get_transform.return_value = None

    tools = build_extraction_validation_tools(
        dictionary_service=dictionary_service,
    )

    validate_observation = _tool_by_name(tools, "validate_observation")
    validate_triple = _tool_by_name(tools, "validate_triple")
    lookup_transform = _tool_by_name(tools, "lookup_transform")

    observation_result = validate_observation("VAR_TEST", "pathogenic")
    assert observation_result["valid"] is True
    dictionary_service.get_variable.assert_called()

    triple_result = validate_triple("VARIANT", "ASSOCIATED_WITH", "PHENOTYPE")
    assert triple_result["allowed"] is True
    assert triple_result["requires_evidence"] is True

    transform_result = lookup_transform("mg", "g")
    assert transform_result["found"] is False
