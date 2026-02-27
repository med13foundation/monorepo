"""Integration tests for space-scoped discovery workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from src.database.session import SessionLocal, engine
from src.domain.entities.user import User, UserRole, UserStatus
from src.infrastructure.security.password_hasher import PasswordHasher
from src.main import create_app
from src.middleware import jwt_auth as jwt_auth_module
from src.models.database import Base
from src.models.database.data_discovery import (
    DataDiscoverySessionModel,
    SourceCatalogEntryModel,
)
from src.models.database.data_source_activation import (
    ActivationScopeEnum,
    DataSourceActivationModel,
    PermissionLevelEnum,
)
from src.models.database.research_space import (
    MembershipRoleEnum,
    ResearchSpaceMembershipModel,
    ResearchSpaceModel,
)
from src.models.database.user import UserModel
from src.routes.auth import get_current_active_user
from tests.db_reset import reset_database

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _reset_database() -> None:
    reset_database(engine, Base.metadata)


def _create_user(session: Session) -> UUID:
    user_id = uuid4()
    user = UserModel(
        id=user_id,
        email="space-user@example.com",
        username="space-user",
        full_name="Space Researcher",
        hashed_password=PasswordHasher().hash_password("StrongPassword!123"),
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    session.add(user)
    session.commit()
    return user_id


def _create_space(session: Session, owner_id: UUID, slug: str, name: str) -> UUID:
    space_id = uuid4()
    space = ResearchSpaceModel(
        id=space_id,
        slug=slug,
        name=name,
        description=f"{name} description",
        owner_id=owner_id,
        status="active",
    )
    session.add(space)
    session.commit()
    return space_id


def _add_membership(session: Session, space_id: UUID, user_id: UUID) -> None:
    membership = ResearchSpaceMembershipModel(
        space_id=space_id,
        user_id=user_id,
        role=MembershipRoleEnum.RESEARCHER,
        is_active=True,
    )
    session.add(membership)
    session.commit()


def _add_catalog_entries(session: Session) -> None:
    session.add_all(
        [
            SourceCatalogEntryModel(
                id="clinvar",
                name="ClinVar",
                description="ClinVar archive",
                category="Variants",
                subcategory=None,
                tags=["variant"],
                param_type="gene",
                source_type="api",
                url_template=None,
                data_format="json",
                api_endpoint=None,
                is_active=True,
                requires_auth=False,
                usage_count=10,
                success_rate=0.9,
                query_capabilities={},
            ),
            SourceCatalogEntryModel(
                id="hpo",
                name="HPO",
                description="Human Phenotype Ontology",
                category="Phenotypes",
                subcategory=None,
                tags=["phenotype"],
                param_type="term",
                source_type="api",
                url_template=None,
                data_format="json",
                api_endpoint=None,
                is_active=True,
                requires_auth=False,
                usage_count=5,
                success_rate=0.95,
                query_capabilities={},
            ),
        ],
    )
    session.commit()


def _set_permission(
    session: Session,
    *,
    catalog_entry_id: str,
    scope: ActivationScopeEnum,
    permission: PermissionLevelEnum,
    updated_by: UUID,
    space_id: UUID | None = None,
) -> None:
    rule = DataSourceActivationModel(
        catalog_entry_id=catalog_entry_id,
        scope=scope,
        research_space_id=str(space_id) if space_id else None,
        permission_level=permission,
        is_active=permission != PermissionLevelEnum.BLOCKED,
        updated_by=str(updated_by),
    )
    session.add(rule)
    session.commit()


def _build_active_user(user_id: UUID) -> User:
    return User(
        id=user_id,
        email="space-user@example.com",
        username="space-user",
        full_name="Space Researcher",
        hashed_password="",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )


def test_space_catalog_enforces_permissions() -> None:
    _reset_database()
    session = SessionLocal()
    user_id = _create_user(session)
    allowed_space = _create_space(session, user_id, "space-allowed", "Allowed Space")
    blocked_space = _create_space(session, user_id, "space-blocked", "Blocked Space")
    _add_membership(session, allowed_space, user_id)
    _add_membership(session, blocked_space, user_id)
    _add_catalog_entries(session)
    _set_permission(
        session,
        catalog_entry_id="clinvar",
        scope=ActivationScopeEnum.GLOBAL,
        permission=PermissionLevelEnum.AVAILABLE,
        updated_by=user_id,
    )
    _set_permission(
        session,
        catalog_entry_id="clinvar",
        scope=ActivationScopeEnum.RESEARCH_SPACE,
        permission=PermissionLevelEnum.BLOCKED,
        updated_by=user_id,
        space_id=blocked_space,
    )
    session.close()

    app = create_app()
    app.dependency_overrides[get_current_active_user] = lambda: _build_active_user(
        user_id,
    )
    client = TestClient(app)
    jwt_auth_module.SKIP_JWT_VALIDATION = True
    try:
        allowed_response = client.get(
            f"/research-spaces/{allowed_space}/discovery/catalog",
            headers={"Authorization": "Bearer test-token"},
        )
        blocked_response = client.get(
            f"/research-spaces/{blocked_space}/discovery/catalog",
            headers={"Authorization": "Bearer test-token"},
        )
    finally:
        jwt_auth_module.SKIP_JWT_VALIDATION = False
        app.dependency_overrides.pop(get_current_active_user, None)

    assert allowed_response.status_code == 200
    allowed_ids = {entry["id"] for entry in allowed_response.json()}
    assert "clinvar" in allowed_ids

    assert blocked_response.status_code == 200
    blocked_ids = {entry["id"] for entry in blocked_response.json()}
    assert "clinvar" not in blocked_ids


def test_space_session_creation_persists_space_context() -> None:
    _reset_database()
    session = SessionLocal()
    user_id = _create_user(session)
    space_id = _create_space(session, user_id, "space-lab", "Lab Space")
    _add_membership(session, space_id, user_id)
    _add_catalog_entries(session)
    _set_permission(
        session,
        catalog_entry_id="clinvar",
        scope=ActivationScopeEnum.GLOBAL,
        permission=PermissionLevelEnum.AVAILABLE,
        updated_by=user_id,
    )
    session.close()

    app = create_app()
    app.dependency_overrides[get_current_active_user] = lambda: _build_active_user(
        user_id,
    )
    client = TestClient(app)
    jwt_auth_module.SKIP_JWT_VALIDATION = True
    try:
        response = client.post(
            f"/research-spaces/{space_id}/discovery/sessions",
            json={
                "name": "Cardiac Sweep",
                "initial_parameters": {
                    "gene_symbol": "MED13L",
                    "search_term": "cardiac",
                },
            },
            headers={"Authorization": "Bearer test-token"},
        )
    finally:
        jwt_auth_module.SKIP_JWT_VALIDATION = False
        app.dependency_overrides.pop(get_current_active_user, None)

    assert response.status_code == 201
    payload = response.json()
    assert payload["research_space_id"] == str(space_id)

    session = SessionLocal()
    persisted = session.get(DataDiscoverySessionModel, payload["id"])
    session.close()
    assert persisted is not None
    assert persisted.research_space_id == str(space_id)

    # GET sessions to ensure only the scoped session is returned
    app = create_app()
    app.dependency_overrides[get_current_active_user] = lambda: _build_active_user(
        user_id,
    )
    client = TestClient(app)
    jwt_auth_module.SKIP_JWT_VALIDATION = True
    try:
        list_response = client.get(
            f"/research-spaces/{space_id}/discovery/sessions",
            headers={"Authorization": "Bearer test-token"},
        )
    finally:
        jwt_auth_module.SKIP_JWT_VALIDATION = False
        app.dependency_overrides.pop(get_current_active_user, None)

    assert list_response.status_code == 200
    sessions_payload = list_response.json()
    assert any(item["id"] == payload["id"] for item in sessions_payload)
