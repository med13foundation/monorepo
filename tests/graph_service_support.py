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


def build_graph_auth_headers(
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


def auth_headers(
    *,
    user_id: UUID,
    email: str,
    role: UserRole = UserRole.RESEARCHER,
    graph_admin: bool = False,
) -> dict[str, str]:
    return build_graph_auth_headers(
        user_id=user_id,
        email=email,
        role=role,
        graph_admin=graph_admin,
    )


def build_graph_admin_headers() -> dict[str, str]:
    return build_graph_auth_headers(
        user_id=uuid4(),
        email=f"graph-admin-{uuid4().hex[:12]}@example.com",
        role=UserRole.VIEWER,
        graph_admin=True,
    )


def admin_headers() -> dict[str, str]:
    return build_graph_admin_headers()


def reset_graph_service_database() -> None:
    reset_database(graph_database.engine, Base.metadata)


def seed_graph_service_dictionary_primitives() -> None:
    with graph_database.SessionLocal() as session:
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        session.commit()


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
    reset_graph_service_database()
    with TestClient(create_app()) as client:
        yield client
    reset_graph_service_database()


__all__ = [
    "admin_headers",
    "auth_headers",
    "build_graph_admin_headers",
    "build_graph_auth_headers",
    "build_seeded_space_fixture",
    "graph_client",
    "reset_graph_service_database",
    "seed_graph_service_dictionary_primitives",
    "seed_graph_space",
]
