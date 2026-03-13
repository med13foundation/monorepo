"""Unit coverage for standalone graph-service auth helpers."""

from __future__ import annotations

from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from services.graph_api.auth import get_current_user
from src.domain.entities.user import UserRole
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
