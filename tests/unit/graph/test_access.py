"""Unit tests for graph-core access abstractions."""

from __future__ import annotations

from src.graph.core.access import (
    GraphAccessRole,
    GraphPrincipal,
    evaluate_graph_admin_access,
    evaluate_graph_space_access,
)


def test_evaluate_graph_admin_access_allows_platform_admin() -> None:
    decision = evaluate_graph_admin_access(
        GraphPrincipal(subject_id="user-1", is_platform_admin=True),
    )

    assert decision.allowed is True
    assert decision.reason == "platform_admin"


def test_evaluate_graph_space_access_rejects_missing_membership() -> None:
    decision = evaluate_graph_space_access(
        principal=GraphPrincipal(subject_id="user-1"),
        membership_role=None,
    )

    assert decision.allowed is False
    assert decision.reason == "not_a_member"


def test_evaluate_graph_space_access_enforces_role_hierarchy() -> None:
    decision = evaluate_graph_space_access(
        principal=GraphPrincipal(subject_id="user-1"),
        membership_role=GraphAccessRole.RESEARCHER,
        required_role=GraphAccessRole.CURATOR,
    )

    assert decision.allowed is False
    assert decision.reason == "insufficient_role"


def test_evaluate_graph_space_access_allows_sufficient_role() -> None:
    decision = evaluate_graph_space_access(
        principal=GraphPrincipal(subject_id="user-1"),
        membership_role=GraphAccessRole.ADMIN,
        required_role=GraphAccessRole.CURATOR,
    )

    assert decision.allowed is True
    assert decision.reason == "role_satisfied"
