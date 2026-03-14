"""Shared test support for standalone graph-service flows."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from services.graph_api import database as graph_database
from services.graph_api.app import create_app
from src.database.seeds.seeder import (
    seed_entity_resolution_policies,
    seed_relation_constraints,
)
from src.domain.entities.user import UserRole
from src.infrastructure.security.jwt_provider import JWTProvider
from src.models.database.base import Base
from src.models.database.kernel.spaces import GraphSpaceModel, GraphSpaceStatusEnum
from tests.db_reset import reset_database

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def auth_headers(
    *,
    user_id: UUID,
    email: str,
    role: UserRole = UserRole.RESEARCHER,
    graph_admin: bool = False,
) -> dict[str, str]:
    secret = "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz"
    provider = JWTProvider(secret_key=secret)
    token = provider.create_access_token(
        user_id=user_id,
        role=role.value,
        extra_claims={"graph_admin": graph_admin},
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-TEST-USER-ID": str(user_id),
        "X-TEST-USER-EMAIL": email,
        "X-TEST-USER-ROLE": role.value,
        "X-TEST-GRAPH-ADMIN": "true" if graph_admin else "false",
    }


def admin_headers() -> dict[str, str]:
    admin_id = uuid4()
    return auth_headers(
        user_id=admin_id,
        email=f"graph-admin-{admin_id.hex[:8]}@example.org",
        role=UserRole.ADMIN,
        graph_admin=True,
    )


def seed_graph_space(
    session: Session,
    *,
    owner_id: UUID,
    space_id: UUID,
    slug: str,
    name: str,
    description: str,
) -> None:
    session.add(
        GraphSpaceModel(
            id=space_id,
            slug=slug,
            name=name,
            description=description,
            owner_id=owner_id,
            status=GraphSpaceStatusEnum.ACTIVE,
            settings={},
        ),
    )
    seed_entity_resolution_policies(session)
    seed_relation_constraints(session)


def build_seeded_space_fixture(
    *,
    slug_prefix: str = "graph-space",
) -> dict[str, object]:
    suffix = uuid4().hex[:8]
    owner_id = uuid4()
    space_id = uuid4()
    with graph_database.SessionLocal() as session:
        seed_graph_space(
            session,
            owner_id=owner_id,
            space_id=space_id,
            slug=f"{slug_prefix}-{suffix}",
            name="Graph Service Test Space",
            description="Standalone graph-service deterministic-resolution test space",
        )
        session.commit()
    return {
        "owner_id": owner_id,
        "space_id": space_id,
        "headers": auth_headers(
            user_id=owner_id,
            email=f"graph-owner-{suffix}@example.org",
        ),
    }


@pytest.fixture(scope="function")
def graph_client() -> TestClient:
    reset_database(graph_database.engine, Base.metadata)
    with TestClient(create_app()) as client:
        yield client
    reset_database(graph_database.engine, Base.metadata)


__all__ = [
    "admin_headers",
    "auth_headers",
    "build_seeded_space_fixture",
    "graph_client",
    "seed_graph_space",
]
