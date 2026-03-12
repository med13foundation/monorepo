"""Integration coverage for hard DB dictionary guarantees on graph writes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.database import session as session_module
from src.domain.entities.user import UserRole, UserStatus
from src.models.database.base import Base
from src.models.database.kernel.dictionary import (
    DictionaryDomainContextModel,
    DictionaryEntityTypeModel,
    DictionaryRelationSynonymModel,
    DictionaryRelationTypeModel,
    RelationConstraintModel,
)
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.relation_claims import RelationClaimModel
from src.models.database.kernel.relation_projection_sources import (
    RelationProjectionSourceModel,
)
from src.models.database.kernel.relations import RelationModel
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from tests.db_reset import reset_database

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


_MIGRATION_025_REQUIRED_TRIGGERS: tuple[tuple[str, str], ...] = (
    ("entities", "trg_entities_normalize_validate"),
    ("relations", "trg_relations_normalize_validate"),
    ("relations", "trg_relations_requires_evidence"),
)


@pytest.fixture(autouse=True)
def reset_db(postgres_required: None) -> None:  # noqa: ARG001
    """Reset database contents before and after each hard-guarantee test."""
    reset_database(session_module.engine, Base.metadata)
    session = session_module.SessionLocal()
    try:
        _require_hard_guarantee_schema(session)
    finally:
        session.close()
    yield
    reset_database(session_module.engine, Base.metadata)


def _require_hard_guarantee_schema(session: Session) -> None:
    relation_synonym_table = session.execute(
        text("SELECT to_regclass('public.dictionary_relation_synonyms')"),
    ).scalar_one()
    if relation_synonym_table is None:
        pytest.skip(
            "Migration 025 hard-guarantee table is missing: dictionary_relation_synonyms",
        )

    for table_name, trigger_name in _MIGRATION_025_REQUIRED_TRIGGERS:
        trigger_exists = bool(
            session.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_trigger AS trg
                        JOIN pg_class AS cls ON cls.oid = trg.tgrelid
                        JOIN pg_namespace AS ns ON ns.oid = cls.relnamespace
                        WHERE ns.nspname = 'public'
                          AND cls.relname = :table_name
                          AND trg.tgname = :trigger_name
                          AND trg.tgisinternal IS FALSE
                    )
                    """,
                ),
                {
                    "table_name": table_name,
                    "trigger_name": trigger_name,
                },
            ).scalar_one(),
        )
        if not trigger_exists:
            pytest.skip(
                "Migration 025 hard-guarantee trigger is missing: "
                f"{table_name}.{trigger_name}",
            )


def _create_user(session: Session, *, label: str) -> UserModel:
    suffix = uuid4().hex[:12]
    user = UserModel(
        email=f"{label}-{suffix}@example.com",
        username=f"{label}-{suffix}",
        full_name=f"{label.title()} Tester",
        hashed_password="hashed-password",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    session.add(user)
    session.flush()
    return user


def _create_space(
    session: Session,
    *,
    owner_id: UUID,
    slug_prefix: str,
) -> ResearchSpaceModel:
    slug = f"{slug_prefix}-{uuid4().hex[:12]}"
    space = ResearchSpaceModel(
        slug=slug,
        name=f"Space {slug_prefix}",
        description="Graph hard guarantee integration test space",
        owner_id=owner_id,
        status="active",
    )
    session.add(space)
    session.flush()
    return space


def _ensure_domain_context(
    session: Session,
    *,
    domain_context: str = "general",
) -> None:
    existing = session.get(DictionaryDomainContextModel, domain_context)
    if existing is not None:
        return
    session.add(
        DictionaryDomainContextModel(
            id=domain_context,
            display_name=domain_context.replace("_", " ").title(),
            description="Hard-guarantee integration test domain context",
        ),
    )
    session.flush()


def _create_entity_type(
    session: Session,
    *,
    entity_type: str,
    is_active: bool = True,
) -> None:
    _ensure_domain_context(session)
    now = datetime.now(UTC)
    model = DictionaryEntityTypeModel(
        id=entity_type,
        display_name=entity_type.replace("_", " ").title(),
        description=f"{entity_type} entity type",
        domain_context="general",
        created_by="manual:test",
        is_active=is_active,
        valid_to=None if is_active else now,
        review_status="ACTIVE" if is_active else "REVOKED",
        revocation_reason=None if is_active else "Revoked in test setup",
    )
    session.add(model)
    session.flush()


def _create_relation_type(
    session: Session,
    *,
    relation_type: str,
    is_active: bool = True,
) -> None:
    _ensure_domain_context(session)
    now = datetime.now(UTC)
    model = DictionaryRelationTypeModel(
        id=relation_type,
        display_name=relation_type.replace("_", " ").title(),
        description=f"{relation_type} relation type",
        domain_context="general",
        is_directional=True,
        created_by="manual:test",
        is_active=is_active,
        valid_to=None if is_active else now,
        review_status="ACTIVE" if is_active else "REVOKED",
        revocation_reason=None if is_active else "Revoked in test setup",
    )
    session.add(model)
    session.flush()


def _create_constraint(
    session: Session,
    *,
    source_type: str,
    relation_type: str,
    target_type: str,
    is_allowed: bool,
    requires_evidence: bool,
) -> None:
    session.add(
        RelationConstraintModel(
            source_type=source_type,
            relation_type=relation_type,
            target_type=target_type,
            is_allowed=is_allowed,
            requires_evidence=requires_evidence,
            created_by="manual:test",
            is_active=True,
            review_status="ACTIVE",
        ),
    )
    session.flush()


def _create_entity(
    session: Session,
    *,
    research_space_id: UUID,
    entity_type: str,
    label: str,
) -> EntityModel:
    entity = EntityModel(
        research_space_id=research_space_id,
        entity_type=entity_type,
        display_label=label,
        metadata_payload={},
    )
    session.add(entity)
    session.flush()
    return entity


def _insert_entity_and_commit(
    session: Session,
    *,
    research_space_id: UUID,
    entity_type: str,
    display_label: str,
) -> None:
    session.add(
        EntityModel(
            research_space_id=research_space_id,
            entity_type=entity_type,
            display_label=display_label,
            metadata_payload={},
        ),
    )
    session.commit()


def _insert_relation_and_commit(
    session: Session,
    *,
    research_space_id: UUID,
    source_id: UUID,
    relation_type: str,
    target_id: UUID,
    source_type: str = "GENE",
    target_type: str = "PHENOTYPE",
    claim_backed: bool = False,
) -> None:
    relation = RelationModel(
        research_space_id=research_space_id,
        source_id=source_id,
        relation_type=relation_type,
        target_id=target_id,
    )
    session.add(relation)
    session.flush()
    if claim_backed:
        claim = RelationClaimModel(
            research_space_id=research_space_id,
            source_document_id=None,
            agent_run_id="hard-guarantee-test",
            source_type=source_type,
            relation_type=relation_type.strip().upper(),
            target_type=target_type,
            source_label=None,
            target_label=None,
            confidence=0.5,
            validation_state="ALLOWED",
            validation_reason="Hard guarantee integration test",
            persistability="PERSISTABLE",
            claim_status="RESOLVED",
            polarity="SUPPORT",
            claim_text="Hard guarantee integration test projection",
            claim_section=None,
            linked_relation_id=relation.id,
            metadata_payload={"origin": "hard_guarantee_test"},
            triaged_by=None,
            triaged_at=None,
        )
        session.add(claim)
        session.flush()
        session.add(
            RelationProjectionSourceModel(
                research_space_id=research_space_id,
                relation_id=relation.id,
                claim_id=claim.id,
                projection_origin="MANUAL_RELATION",
                source_document_id=None,
                agent_run_id="hard-guarantee-test",
                metadata_payload={"origin": "hard_guarantee_test"},
            ),
        )
    session.commit()


def test_invalid_and_revoked_entity_type_rejected() -> None:
    session = session_module.SessionLocal()
    try:
        user = _create_user(session, label="hard-entity-type")
        space = _create_space(session, owner_id=user.id, slug_prefix="hard-entity")
        _create_entity_type(session, entity_type="GENE", is_active=False)
        session.commit()

        with pytest.raises(SQLAlchemyError):
            _insert_entity_and_commit(
                session,
                research_space_id=space.id,
                entity_type="UNKNOWN_ENTITY_TYPE",
                display_label="Unknown Type",
            )
        session.rollback()

        with pytest.raises(SQLAlchemyError) as exc_info:
            _insert_entity_and_commit(
                session,
                research_space_id=space.id,
                entity_type="GENE",
                display_label="Revoked Type",
            )
        session.rollback()
        assert "active dictionary_entity_type" in str(exc_info.value).lower()
    finally:
        session.close()


def test_invalid_and_revoked_relation_type_rejected() -> None:
    session = session_module.SessionLocal()
    try:
        user = _create_user(session, label="hard-relation-type")
        space = _create_space(session, owner_id=user.id, slug_prefix="hard-rel")
        _create_entity_type(session, entity_type="GENE")
        _create_entity_type(session, entity_type="PHENOTYPE")
        _create_relation_type(session, relation_type="CAUSES", is_active=False)
        _create_constraint(
            session,
            source_type="GENE",
            relation_type="CAUSES",
            target_type="PHENOTYPE",
            is_allowed=True,
            requires_evidence=False,
        )
        source_entity = _create_entity(
            session,
            research_space_id=space.id,
            entity_type="GENE",
            label="MED13",
        )
        target_entity = _create_entity(
            session,
            research_space_id=space.id,
            entity_type="PHENOTYPE",
            label="Cardiomyopathy",
        )
        session.commit()

        with pytest.raises(SQLAlchemyError):
            _insert_relation_and_commit(
                session,
                research_space_id=space.id,
                source_id=source_entity.id,
                relation_type="UNKNOWN_RELATION_TYPE",
                target_id=target_entity.id,
            )
        session.rollback()

        with pytest.raises(SQLAlchemyError) as exc_info:
            _insert_relation_and_commit(
                session,
                research_space_id=space.id,
                source_id=source_entity.id,
                relation_type="CAUSES",
                target_id=target_entity.id,
                claim_backed=True,
            )
        session.rollback()
        assert "active dictionary_relation_type" in str(exc_info.value).lower()
    finally:
        session.close()


def test_alias_relation_type_is_canonicalized_on_write() -> None:
    session = session_module.SessionLocal()
    try:
        user = _create_user(session, label="hard-alias")
        space = _create_space(session, owner_id=user.id, slug_prefix="hard-alias")
        _create_entity_type(session, entity_type="GENE")
        _create_entity_type(session, entity_type="PHENOTYPE")
        _create_relation_type(session, relation_type="CAUSES")
        _create_constraint(
            session,
            source_type="GENE",
            relation_type="CAUSES",
            target_type="PHENOTYPE",
            is_allowed=True,
            requires_evidence=False,
        )
        session.add(
            DictionaryRelationSynonymModel(
                relation_type="CAUSES",
                synonym="DRIVES",
                source="manual",
                created_by="manual:test",
                review_status="ACTIVE",
            ),
        )
        source_entity = _create_entity(
            session,
            research_space_id=space.id,
            entity_type="GENE",
            label="MED13",
        )
        target_entity = _create_entity(
            session,
            research_space_id=space.id,
            entity_type="PHENOTYPE",
            label="Cardiomyopathy",
        )
        session.flush()

        relation = RelationModel(
            research_space_id=space.id,
            source_id=source_entity.id,
            relation_type=" drives ",
            target_id=target_entity.id,
        )
        session.add(relation)
        session.flush()
        claim = RelationClaimModel(
            research_space_id=space.id,
            source_document_id=None,
            agent_run_id="hard-alias-test",
            source_type="GENE",
            relation_type="CAUSES",
            target_type="PHENOTYPE",
            source_label="MED13",
            target_label="Cardiomyopathy",
            confidence=0.5,
            validation_state="ALLOWED",
            validation_reason="Alias hard guarantee integration test",
            persistability="PERSISTABLE",
            claim_status="RESOLVED",
            polarity="SUPPORT",
            claim_text="MED13 drives cardiomyopathy.",
            claim_section=None,
            linked_relation_id=relation.id,
            metadata_payload={"origin": "hard_guarantee_test"},
            triaged_by=None,
            triaged_at=None,
        )
        session.add(claim)
        session.flush()
        session.add(
            RelationProjectionSourceModel(
                research_space_id=space.id,
                relation_id=relation.id,
                claim_id=claim.id,
                projection_origin="MANUAL_RELATION",
                source_document_id=None,
                agent_run_id="hard-alias-test",
                metadata_payload={"origin": "hard_guarantee_test"},
            ),
        )
        session.commit()
        session.refresh(relation)

        assert relation.relation_type == "CAUSES"
    finally:
        session.close()


def test_disallowed_triple_is_rejected() -> None:
    session = session_module.SessionLocal()
    try:
        user = _create_user(session, label="hard-disallowed")
        space = _create_space(session, owner_id=user.id, slug_prefix="hard-disallow")
        _create_entity_type(session, entity_type="GENE")
        _create_entity_type(session, entity_type="PHENOTYPE")
        _create_relation_type(session, relation_type="CAUSES")
        _create_constraint(
            session,
            source_type="GENE",
            relation_type="CAUSES",
            target_type="PHENOTYPE",
            is_allowed=False,
            requires_evidence=False,
        )
        source_entity = _create_entity(
            session,
            research_space_id=space.id,
            entity_type="GENE",
            label="MED13",
        )
        target_entity = _create_entity(
            session,
            research_space_id=space.id,
            entity_type="PHENOTYPE",
            label="Cardiomyopathy",
        )
        session.commit()

        with pytest.raises(SQLAlchemyError) as exc_info:
            _insert_relation_and_commit(
                session,
                research_space_id=space.id,
                source_id=source_entity.id,
                relation_type="CAUSES",
                target_id=target_entity.id,
                claim_backed=True,
            )
        session.rollback()
        assert (
            "not allowed by active relation constraints" in str(exc_info.value).lower()
        )
    finally:
        session.close()


def test_cross_space_relation_is_rejected() -> None:
    session = session_module.SessionLocal()
    try:
        user = _create_user(session, label="hard-cross-space")
        space_a = _create_space(session, owner_id=user.id, slug_prefix="hard-space-a")
        space_b = _create_space(session, owner_id=user.id, slug_prefix="hard-space-b")
        _create_entity_type(session, entity_type="GENE")
        _create_entity_type(session, entity_type="PHENOTYPE")
        _create_relation_type(session, relation_type="CAUSES")
        _create_constraint(
            session,
            source_type="GENE",
            relation_type="CAUSES",
            target_type="PHENOTYPE",
            is_allowed=True,
            requires_evidence=False,
        )
        source_entity = _create_entity(
            session,
            research_space_id=space_a.id,
            entity_type="GENE",
            label="MED13",
        )
        target_entity_other_space = _create_entity(
            session,
            research_space_id=space_b.id,
            entity_type="PHENOTYPE",
            label="Cardiomyopathy",
        )
        session.commit()

        with pytest.raises(SQLAlchemyError) as exc_info:
            _insert_relation_and_commit(
                session,
                research_space_id=space_a.id,
                source_id=source_entity.id,
                relation_type="CAUSES",
                target_id=target_entity_other_space.id,
            )
        session.rollback()
        error_message = str(exc_info.value).lower()
        assert (
            "does not belong to research_space_id" in error_message
            or "fk_relations_target_space_entities" in error_message
        )
    finally:
        session.close()


def test_requires_evidence_constraint_is_enforced_at_commit() -> None:
    session = session_module.SessionLocal()
    try:
        user = _create_user(session, label="hard-evidence")
        space = _create_space(session, owner_id=user.id, slug_prefix="hard-evidence")
        _create_entity_type(session, entity_type="GENE")
        _create_entity_type(session, entity_type="PHENOTYPE")
        _create_relation_type(session, relation_type="CAUSES")
        _create_constraint(
            session,
            source_type="GENE",
            relation_type="CAUSES",
            target_type="PHENOTYPE",
            is_allowed=True,
            requires_evidence=True,
        )
        source_entity = _create_entity(
            session,
            research_space_id=space.id,
            entity_type="GENE",
            label="MED13",
        )
        target_entity = _create_entity(
            session,
            research_space_id=space.id,
            entity_type="PHENOTYPE",
            label="Cardiomyopathy",
        )
        session.commit()

        with pytest.raises(SQLAlchemyError) as exc_info:
            _insert_relation_and_commit(
                session,
                research_space_id=space.id,
                source_id=source_entity.id,
                relation_type="CAUSES",
                target_id=target_entity.id,
                claim_backed=True,
            )
        session.rollback()
        assert (
            "requires evidence but none exists at commit" in str(exc_info.value).lower()
        )
    finally:
        session.close()
