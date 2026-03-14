from __future__ import annotations

from uuid import UUID, uuid4

from services.graph_api import database as graph_database
from src.database.seeds.seeder import (
    seed_entity_resolution_policies,
    seed_relation_constraints,
)
from src.domain.entities.user import UserRole
from src.infrastructure.security.jwt_provider import JWTProvider
from src.models.database.base import Base
from tests.db_reset import reset_database


def build_graph_auth_headers(
    *,
    user_id: UUID,
    email: str,
    role: UserRole,
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


def build_graph_admin_headers() -> dict[str, str]:
    return build_graph_auth_headers(
        user_id=uuid4(),
        email=f"graph-admin-{uuid4().hex[:12]}@example.com",
        role=UserRole.VIEWER,
        graph_admin=True,
    )


def reset_graph_service_database() -> None:
    reset_database(graph_database.engine, Base.metadata)


def seed_graph_service_dictionary_primitives() -> None:
    with graph_database.SessionLocal() as session:
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        session.commit()
