"""Tests for content-enrichment skill registration and tool building."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from src.infrastructure.llm.skills.registry import (
    build_content_enrichment_tools,
    get_skill_registry,
    register_all_skills,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _tool_by_name(tools: list[object], name: str) -> Callable[..., object]:
    for tool in tools:
        tool_name = getattr(tool, "__name__", "")
        if tool_name == name and callable(tool):
            return tool
    msg = f"Tool '{name}' not found"
    raise AssertionError(msg)


def test_register_all_skills_includes_content_enrichment_skills() -> None:
    register_all_skills()
    registry = get_skill_registry()
    available = set(registry.list_skills())
    assert "fetch_pmc_oa" in available
    assert "fetch_europe_pmc" in available
    assert "check_open_access" in available
    assert "pass_through" in available


def test_build_content_enrichment_tools_invokes_registered_toolset() -> None:
    tools = build_content_enrichment_tools()
    check_open_access = _tool_by_name(tools, "check_open_access")
    pass_through = _tool_by_name(tools, "pass_through")

    open_access_result = check_open_access("PMC12345", None)
    assert open_access_result["is_open_access"] is True

    pass_through_result = pass_through({"field": "value"}, None)
    assert pass_through_result["decision"] == "enriched"
    assert pass_through_result["content_format"] == "structured_json"


def test_fetch_tools_return_not_found_when_http_fetch_fails() -> None:
    tools = build_content_enrichment_tools()
    fetch_pmc_oa = _tool_by_name(tools, "fetch_pmc_oa")
    fetch_europe_pmc = _tool_by_name(tools, "fetch_europe_pmc")

    with patch(
        "src.infrastructure.llm.skills.enrichment_tools._http_get_text",
        side_effect=OSError("network unavailable"),
    ):
        pmc_result = fetch_pmc_oa("PMC123")
        europe_result = fetch_europe_pmc("PMC123")

    assert pmc_result["found"] is False
    assert europe_result["found"] is False
