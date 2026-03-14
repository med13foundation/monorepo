"""Domain-neutral access abstractions for graph platform integrations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GraphAccessRole(str, Enum):
    """Ordered access roles understood by graph-core."""

    VIEWER = "viewer"
    RESEARCHER = "researcher"
    CURATOR = "curator"
    ADMIN = "admin"
    OWNER = "owner"


_GRAPH_ACCESS_ROLE_HIERARCHY = {
    GraphAccessRole.VIEWER: 1,
    GraphAccessRole.RESEARCHER: 2,
    GraphAccessRole.CURATOR: 3,
    GraphAccessRole.ADMIN: 4,
    GraphAccessRole.OWNER: 5,
}


@dataclass(frozen=True)
class GraphPrincipal:
    """Authenticated principal evaluated by graph-core access policies."""

    subject_id: str
    is_platform_admin: bool = False


@dataclass(frozen=True)
class GraphAccessDecision:
    """Outcome of a graph-core access evaluation."""

    allowed: bool
    reason: str


def evaluate_graph_admin_access(principal: GraphPrincipal) -> GraphAccessDecision:
    """Evaluate whether one principal can access graph control-plane operations."""
    if principal.is_platform_admin:
        return GraphAccessDecision(allowed=True, reason="platform_admin")
    return GraphAccessDecision(allowed=False, reason="platform_admin_required")


def evaluate_graph_space_access(
    *,
    principal: GraphPrincipal,
    membership_role: GraphAccessRole | None,
    required_role: GraphAccessRole = GraphAccessRole.VIEWER,
) -> GraphAccessDecision:
    """Evaluate graph-space access for one principal and required role."""
    admin_decision = evaluate_graph_admin_access(principal)
    if admin_decision.allowed:
        return admin_decision

    if membership_role is None:
        return GraphAccessDecision(allowed=False, reason="not_a_member")

    if (
        _GRAPH_ACCESS_ROLE_HIERARCHY[membership_role]
        < _GRAPH_ACCESS_ROLE_HIERARCHY[required_role]
    ):
        return GraphAccessDecision(allowed=False, reason="insufficient_role")

    return GraphAccessDecision(allowed=True, reason="role_satisfied")
