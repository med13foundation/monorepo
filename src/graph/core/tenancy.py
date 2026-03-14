"""Domain-neutral tenancy abstractions for graph platform integrations."""

from __future__ import annotations

from dataclasses import dataclass

from src.graph.core.access import (
    GraphAccessDecision,
    GraphAccessRole,
    GraphPrincipal,
    evaluate_graph_space_access,
)


@dataclass(frozen=True)
class GraphTenant:
    """Tenant or space scope evaluated by graph-core policies."""

    tenant_id: str


@dataclass(frozen=True)
class GraphTenantMembership:
    """One principal's membership context inside a tenant or space scope."""

    tenant: GraphTenant
    membership_role: GraphAccessRole | None = None


@dataclass(frozen=True)
class GraphRlsSessionContext:
    """Portable RLS session settings derived from graph-core auth decisions."""

    current_user_id: str | None
    has_phi_access: bool = False
    is_admin: bool = False
    bypass_rls: bool = False


def evaluate_graph_tenant_access(
    *,
    principal: GraphPrincipal,
    tenant_membership: GraphTenantMembership,
    required_role: GraphAccessRole = GraphAccessRole.VIEWER,
) -> GraphAccessDecision:
    """Evaluate access for one principal inside one tenant or space scope."""
    return evaluate_graph_space_access(
        principal=principal,
        membership_role=tenant_membership.membership_role,
        required_role=required_role,
    )


def create_graph_rls_session_context(
    *,
    principal: GraphPrincipal,
    bypass_rls: bool = False,
) -> GraphRlsSessionContext:
    """Build the RLS session settings implied by one authenticated principal."""
    return GraphRlsSessionContext(
        current_user_id=principal.subject_id,
        has_phi_access=principal.is_platform_admin,
        is_admin=principal.is_platform_admin,
        bypass_rls=bypass_rls,
    )
