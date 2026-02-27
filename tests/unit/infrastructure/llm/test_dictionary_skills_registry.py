"""Tests for dictionary skill registration and tool building."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import Mock

from src.domain.entities.kernel.dictionary import (
    DictionarySearchResult,
    RelationConstraint,
    VariableDefinition,
)
from src.infrastructure.llm.skills.registry import (
    build_entity_recognition_dictionary_tools,
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
        description="test variable",
        created_by="seed",
        source_ref=None,
        review_status="ACTIVE",
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        created_at=now,
        updated_at=now,
    )


def _build_search_result() -> DictionarySearchResult:
    return DictionarySearchResult(
        dimension="variables",
        entry_id="VAR_TEST",
        display_name="Test",
        description="test variable",
        domain_context="general",
        match_method="exact",
        similarity_score=1.0,
        metadata={"canonical_name": "test"},
    )


def _build_relation_constraint() -> RelationConstraint:
    now = datetime.now(UTC)
    return RelationConstraint(
        id=10,
        source_type="VARIANT",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        is_allowed=True,
        requires_evidence=True,
        created_by="seed",
        source_ref=None,
        review_status="ACTIVE",
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        created_at=now,
        updated_at=now,
    )


def _tool_by_name(
    tools: list[object],
    name: str,
) -> Callable[..., object]:
    for tool in tools:
        tool_name = getattr(tool, "__name__", "")
        if tool_name == name and callable(tool):
            return tool
    msg = f"Tool '{name}' not found"
    raise AssertionError(msg)


def test_register_all_skills_includes_dictionary_skills() -> None:
    register_all_skills()
    registry = get_skill_registry()
    available = set(registry.list_skills())
    assert "dictionary_search" in available
    assert "dictionary_search_by_domain" in available
    assert "create_variable" in available
    assert "create_synonym" in available
    assert "create_entity_type" in available
    assert "create_relation_type" in available
    assert "create_relation_constraint" in available


def test_build_entity_recognition_dictionary_tools_calls_dictionary_service() -> None:
    dictionary_service = Mock()
    dictionary_service.dictionary_search.return_value = [_build_search_result()]
    dictionary_service.create_variable.return_value = _build_variable()
    dictionary_service.create_relation_constraint.return_value = (
        _build_relation_constraint()
    )

    tools = build_entity_recognition_dictionary_tools(
        dictionary_service=dictionary_service,
        created_by="agent:test",
    )

    search_tool = _tool_by_name(tools, "dictionary_search")
    create_variable_tool = _tool_by_name(tools, "create_variable")
    create_constraint_tool = _tool_by_name(tools, "create_relation_constraint")

    search_results = search_tool(["clinical significance"])
    assert isinstance(search_results, list)
    assert search_results[0]["entry_id"] == "VAR_TEST"
    dictionary_service.dictionary_search.assert_called_once()

    created_variable = create_variable_tool(
        "VAR_NEW",
        "new_var",
        "New Var",
        "STRING",
    )
    assert created_variable["id"] == "VAR_TEST"
    create_call = dictionary_service.create_variable.call_args.kwargs
    assert create_call["created_by"] == "agent:test"

    created_constraint = create_constraint_tool(
        "VARIANT",
        "ASSOCIATED_WITH",
        "PHENOTYPE",
    )
    assert created_constraint["relation_type"] == "ASSOCIATED_WITH"
    constraint_call = dictionary_service.create_relation_constraint.call_args.kwargs
    assert constraint_call["created_by"] == "agent:test"
