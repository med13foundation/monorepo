"""Integration tests for database row-level security kernel policies."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from src.database import session as session_module
from src.database.session import set_session_rls_context
from src.domain.entities.user import UserRole, UserStatus
from src.models.database.base import Base
from src.models.database.kernel.dictionary import (
    DictionaryDomainContextModel,
    DictionaryEntityTypeModel,
)
from src.models.database.kernel.entities import EntityIdentifierModel, EntityModel
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from tests.db_reset import reset_database

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def reset_db(postgres_required) -> None:  # noqa: ARG001
    """Reset the database before and after each RLS integration test."""
    reset_database(session_module.engine, Base.metadata)
    yield
    reset_database(session_module.engine, Base.metadata)


@pytest.fixture
def rls_query_role(postgres_required) -> str:  # noqa: ARG001
    """Create a non-superuser role so PostgreSQL does not bypass RLS."""
    role_name = f"rls_query_{uuid4().hex[:12]}"
    admin_session = session_module.SessionLocal()
    try:
        set_session_rls_context(admin_session, bypass_rls=True)
        admin_session.execute(text(f'CREATE ROLE "{role_name}"'))
        admin_session.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role_name}"'))
        admin_session.execute(
            text(
                f"""
                GRANT SELECT ON TABLE
                    public.entities,
                    public.entity_identifiers,
                    public.observations,
                    public.relations,
                    public.relation_evidence,
                    public.provenance,
                    public.research_spaces,
                    public.research_space_memberships
                TO "{role_name}"
                """,
            ),
        )
        admin_session.commit()
    finally:
        admin_session.close()

    yield role_name

    cleanup_session = session_module.SessionLocal()
    try:
        set_session_rls_context(cleanup_session, bypass_rls=True)
        cleanup_session.execute(text("RESET ROLE"))
        cleanup_session.execute(text(f'DROP OWNED BY "{role_name}"'))
        cleanup_session.execute(text(f'DROP ROLE IF EXISTS "{role_name}"'))
        cleanup_session.commit()
    finally:
        cleanup_session.close()


def _create_user(session: Session, label: str) -> UserModel:
    suffix = uuid4().hex[:8]
    user = UserModel(
        id=uuid4(),
        email=f"{label}-{suffix}@example.com",
        username=f"{label}-{suffix}",
        full_name=f"{label.title()} User",
        hashed_password="test-hash",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    session.add(user)
    session.flush()
    return user


def _create_space(session: Session, *, owner_id: UUID, slug: str) -> ResearchSpaceModel:
    space = ResearchSpaceModel(
        id=uuid4(),
        slug=slug,
        name=f"Space {slug}",
        description=f"Space {slug}",
        owner_id=owner_id,
        status="active",
    )
    session.add(space)
    session.flush()
    return space


def _seed_required_entity_types(
    session: Session,
    *,
    entity_type_ids: tuple[str, ...],
) -> None:
    domain_context_id = "biomedical"
    if session.get(DictionaryDomainContextModel, domain_context_id) is None:
        session.add(
            DictionaryDomainContextModel(
                id=domain_context_id,
                display_name="Biomedical",
                description="Biomedical domain context for integration tests",
                is_active=True,
            ),
        )
        session.flush()

    for entity_type_id in entity_type_ids:
        if session.get(DictionaryEntityTypeModel, entity_type_id) is not None:
            continue
        session.add(
            DictionaryEntityTypeModel(
                id=entity_type_id,
                display_name=entity_type_id.title(),
                description=f"{entity_type_id} entity type for integration tests",
                domain_context=domain_context_id,
                expected_properties={},
                is_active=True,
                review_status="ACTIVE",
                created_by="test-seed",
            ),
        )
    session.flush()


def _seed_two_space_entities() -> tuple[UUID, UUID, UUID, UUID]:
    seed_session = session_module.SessionLocal()
    try:
        set_session_rls_context(seed_session, bypass_rls=True)
        _seed_required_entity_types(seed_session, entity_type_ids=("GENE",))
        user_a = _create_user(seed_session, "rls-a")
        user_b = _create_user(seed_session, "rls-b")

        space_a = _create_space(
            seed_session,
            owner_id=user_a.id,
            slug=f"rls-space-a-{uuid4().hex[:8]}",
        )
        space_b = _create_space(
            seed_session,
            owner_id=user_b.id,
            slug=f"rls-space-b-{uuid4().hex[:8]}",
        )

        entity_a = EntityModel(
            id=uuid4(),
            research_space_id=space_a.id,
            entity_type="GENE",
            display_label="MED13",
            metadata_payload={},
        )
        entity_b = EntityModel(
            id=uuid4(),
            research_space_id=space_b.id,
            entity_type="GENE",
            display_label="OTHER",
            metadata_payload={},
        )
        seed_session.add_all([entity_a, entity_b])
        seed_session.commit()
        return user_a.id, user_b.id, entity_a.id, entity_b.id
    finally:
        seed_session.close()


def test_rls_filters_entities_by_current_user_scope(rls_query_role: str) -> None:
    user_a_id, _user_b_id, entity_a_id, entity_b_id = _seed_two_space_entities()

    query_session = session_module.SessionLocal()
    try:
        query_session.execute(text(f'SET ROLE "{rls_query_role}"'))
        set_session_rls_context(
            query_session,
            current_user_id=user_a_id,
            is_admin=False,
            has_phi_access=False,
            bypass_rls=False,
        )
        visible_ids = set(
            query_session.execute(select(EntityModel.id)).scalars().all(),
        )
    finally:
        query_session.close()

    assert entity_a_id in visible_ids
    assert entity_b_id not in visible_ids


def test_rls_hides_phi_identifiers_without_phi_access(rls_query_role: str) -> None:
    seed_session = session_module.SessionLocal()
    try:
        set_session_rls_context(seed_session, bypass_rls=True)
        _seed_required_entity_types(seed_session, entity_type_ids=("PATIENT",))
        user = _create_user(seed_session, "rls-phi")
        space = _create_space(
            seed_session,
            owner_id=user.id,
            slug=f"rls-space-phi-{uuid4().hex[:8]}",
        )
        entity = EntityModel(
            id=uuid4(),
            research_space_id=space.id,
            entity_type="PATIENT",
            display_label="Patient A",
            metadata_payload={},
        )
        seed_session.add(entity)
        seed_session.flush()
        seed_session.add_all(
            [
                EntityIdentifierModel(
                    entity_id=entity.id,
                    namespace="INTERNAL_ID",
                    identifier_value="internal-1",
                    sensitivity="INTERNAL",
                ),
                EntityIdentifierModel(
                    entity_id=entity.id,
                    namespace="MRN",
                    identifier_value="mrn-phi-1",
                    sensitivity="PHI",
                ),
            ],
        )
        seed_session.commit()
        user_id = user.id
    finally:
        seed_session.close()

    non_phi_session = session_module.SessionLocal()
    try:
        non_phi_session.execute(text(f'SET ROLE "{rls_query_role}"'))
        set_session_rls_context(
            non_phi_session,
            current_user_id=user_id,
            has_phi_access=False,
            is_admin=False,
            bypass_rls=False,
        )
        visible_non_phi = set(
            non_phi_session.execute(
                select(EntityIdentifierModel.identifier_value),
            )
            .scalars()
            .all(),
        )
    finally:
        non_phi_session.close()

    phi_session = session_module.SessionLocal()
    try:
        phi_session.execute(text(f'SET ROLE "{rls_query_role}"'))
        set_session_rls_context(
            phi_session,
            current_user_id=user_id,
            has_phi_access=True,
            is_admin=False,
            bypass_rls=False,
        )
        visible_with_phi = set(
            phi_session.execute(
                select(EntityIdentifierModel.identifier_value),
            )
            .scalars()
            .all(),
        )
    finally:
        phi_session.close()

    assert visible_non_phi == {"internal-1"}
    assert visible_with_phi == {"internal-1", "mrn-phi-1"}


def test_rls_bypass_context_allows_cross_space_visibility(rls_query_role: str) -> None:
    _user_a_id, _user_b_id, entity_a_id, entity_b_id = _seed_two_space_entities()

    restricted_session = session_module.SessionLocal()
    try:
        restricted_session.execute(text(f'SET ROLE "{rls_query_role}"'))
        set_session_rls_context(
            restricted_session,
            current_user_id=None,
            is_admin=False,
            has_phi_access=False,
            bypass_rls=False,
        )
        restricted_count = len(
            restricted_session.execute(select(EntityModel.id)).scalars().all(),
        )
    finally:
        restricted_session.close()

    bypass_session = session_module.SessionLocal()
    try:
        bypass_session.execute(text(f'SET ROLE "{rls_query_role}"'))
        set_session_rls_context(
            bypass_session,
            current_user_id=None,
            is_admin=False,
            has_phi_access=False,
            bypass_rls=True,
        )
        bypass_ids = set(bypass_session.execute(select(EntityModel.id)).scalars().all())
    finally:
        bypass_session.close()

    assert restricted_count == 0
    assert bypass_ids == {entity_a_id, entity_b_id}
