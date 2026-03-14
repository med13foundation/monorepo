"""Unit coverage for standalone graph-service auth helpers."""

from __future__ import annotations

from uuid import UUID

from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from services.graph_api.auth import (
    GraphServiceUser,
    get_current_user,
    to_graph_rls_session_context,
    to_graph_tenant_membership,
)
from src.domain.entities.research_space_membership import MembershipRole
from src.domain.entities.user import UserRole, UserStatus
from src.graph.core.access import GraphAccessRole
from src.infrastructure.security.jwt_provider import JWTProvider


async def test_get_current_user_accepts_jwt_subject_as_valid_email(monkeypatch) -> None:
    monkeypatch.setenv(
        "GRAPH_JWT_SECRET",
        "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz",
    )
    token = JWTProvider(
        secret_key="test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz",
    ).create_access_token(
        user_id="11111111-1111-1111-1111-111111111111",
        role=UserRole.RESEARCHER.value,
        extra_claims={"graph_admin": True},
    )
    request = Request({"type": "http", "headers": []})

    user = await get_current_user(
        request,
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
    )

    assert (
        user.email == "11111111-1111-1111-1111-111111111111@graph-service.example.com"
    )
    assert user.role == UserRole.RESEARCHER
    assert user.is_graph_admin is True


def test_to_graph_tenant_membership_maps_space_role() -> None:
    membership = to_graph_tenant_membership(
        space_id=UUID("11111111-1111-1111-1111-111111111111"),
        membership_role=MembershipRole.CURATOR,
    )

    assert membership.tenant.tenant_id == "11111111-1111-1111-1111-111111111111"
    assert membership.membership_role == GraphAccessRole.CURATOR


def test_to_graph_rls_session_context_maps_graph_admin() -> None:
    current_user = GraphServiceUser(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        email="graph-admin@example.com",
        username="graph-admin",
        full_name="Graph Admin",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        hashed_password="hashed",
        is_graph_admin=True,
    )

    context = to_graph_rls_session_context(current_user, bypass_rls=True)

    assert context.current_user_id == "11111111-1111-1111-1111-111111111111"
    assert context.has_phi_access is True
    assert context.is_admin is True
    assert context.bypass_rls is True
