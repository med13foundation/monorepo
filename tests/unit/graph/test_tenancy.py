"""Unit coverage for graph-core tenancy abstractions."""

from __future__ import annotations

from src.graph.core.access import GraphAccessRole, GraphPrincipal
from src.graph.core.tenancy import (
    GraphTenant,
    GraphTenantMembership,
    create_graph_rls_session_context,
    evaluate_graph_tenant_access,
)


def test_evaluate_graph_tenant_access_allows_sufficient_role() -> None:
    decision = evaluate_graph_tenant_access(
        principal=GraphPrincipal(subject_id="user-1"),
        tenant_membership=GraphTenantMembership(
            tenant=GraphTenant(tenant_id="tenant-1"),
            membership_role=GraphAccessRole.CURATOR,
        ),
        required_role=GraphAccessRole.RESEARCHER,
    )

    assert decision.allowed is True
    assert decision.reason == "role_satisfied"


def test_evaluate_graph_tenant_access_rejects_missing_membership() -> None:
    decision = evaluate_graph_tenant_access(
        principal=GraphPrincipal(subject_id="user-1"),
        tenant_membership=GraphTenantMembership(
            tenant=GraphTenant(tenant_id="tenant-1"),
            membership_role=None,
        ),
    )

    assert decision.allowed is False
    assert decision.reason == "not_a_member"


def test_create_graph_rls_session_context_for_platform_admin() -> None:
    context = create_graph_rls_session_context(
        principal=GraphPrincipal(subject_id="admin-1", is_platform_admin=True),
        bypass_rls=True,
    )

    assert context.current_user_id == "admin-1"
    assert context.has_phi_access is True
    assert context.is_admin is True
    assert context.bypass_rls is True
