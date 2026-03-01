"""Unit tests for the SQLAlchemy kernel dictionary repository adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from src.domain.entities.user import UserRole, UserStatus
from src.infrastructure.repositories.kernel.kernel_dictionary_repository import (
    SqlAlchemyDictionaryRepository,
)
from src.models.database.kernel.dictionary import DictionaryDomainContextModel
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel
from src.models.database.research_space import ResearchSpaceModel, SpaceStatusEnum
from src.models.database.user import UserModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _create_variable(
    repository: SqlAlchemyDictionaryRepository,
    *,
    variable_id: str,
    canonical_name: str,
) -> None:
    _ensure_domain_context(repository, "general")
    repository.create_variable(
        variable_id=variable_id,
        canonical_name=canonical_name,
        display_name=canonical_name.replace("_", " ").title(),
        data_type="STRING",
        domain_context="general",
        sensitivity="INTERNAL",
        constraints={},
        description=f"Dictionary repository test variable {variable_id}",
        created_by="manual:test",
        source_ref="test:repository",
    )


def _create_entity_type(
    repository: SqlAlchemyDictionaryRepository,
    *,
    entity_type: str,
) -> None:
    _ensure_domain_context(repository, "general")
    repository.create_entity_type(
        entity_type=entity_type,
        display_name=entity_type.replace("_", " ").title(),
        description=f"Dictionary repository test entity type {entity_type}",
        domain_context="general",
        expected_properties={},
        created_by="manual:test",
        source_ref="test:repository",
    )


def _create_relation_type(
    repository: SqlAlchemyDictionaryRepository,
    *,
    relation_type: str,
) -> None:
    _ensure_domain_context(repository, "general")
    repository.create_relation_type(
        relation_type=relation_type,
        display_name=relation_type.replace("_", " ").title(),
        description=f"Dictionary repository test relation type {relation_type}",
        domain_context="general",
        is_directional=True,
        inverse_label=None,
        created_by="manual:test",
        source_ref="test:repository",
    )


def _ensure_domain_context(
    repository: SqlAlchemyDictionaryRepository,
    domain_context: str,
) -> None:
    normalized = domain_context.strip().lower()
    existing = repository._session.get(DictionaryDomainContextModel, normalized)
    if existing is not None:
        return
    repository._session.add(
        DictionaryDomainContextModel(
            id=normalized,
            display_name=normalized.replace("_", " ").title(),
            description="Test domain context",
        ),
    )
    repository._session.flush()


def _seed_space_with_entities(
    repository: SqlAlchemyDictionaryRepository,
    *,
    source_entity_type: str,
    target_entity_type: str,
) -> tuple[UUID, UUID, UUID]:
    owner_id = uuid4()
    repository._session.add(
        UserModel(
            id=owner_id,
            email=f"{owner_id}@example.org",
            username=f"user_{str(owner_id).replace('-', '')[:8]}",
            full_name="Dictionary Repository Test User",
            hashed_password="hashed",
            role=UserRole.RESEARCHER,
            status=UserStatus.ACTIVE,
            email_verified=True,
        ),
    )

    research_space_id = uuid4()
    repository._session.add(
        ResearchSpaceModel(
            id=research_space_id,
            slug=f"dict-space-{str(research_space_id).replace('-', '')[:8]}",
            name="Dictionary Repository Test Space",
            description="Dictionary repository merge test space",
            owner_id=owner_id,
            status=SpaceStatusEnum.ACTIVE,
            settings={},
            tags=[],
        ),
    )

    source_entity_id = uuid4()
    target_entity_id = uuid4()
    repository._session.add_all(
        [
            EntityModel(
                id=source_entity_id,
                research_space_id=research_space_id,
                entity_type=source_entity_type,
                display_label="Source entity",
                metadata_payload={},
            ),
            EntityModel(
                id=target_entity_id,
                research_space_id=research_space_id,
                entity_type=target_entity_type,
                display_label="Target entity",
                metadata_payload={},
            ),
        ],
    )
    repository._session.flush()
    return research_space_id, source_entity_id, target_entity_id


def test_find_variables_excludes_inactive_by_default(db_session: Session) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    _create_variable(
        repository,
        variable_id="VAR_REPO_ACTIVE",
        canonical_name="repo_active",
    )
    _create_variable(
        repository,
        variable_id="VAR_REPO_INACTIVE",
        canonical_name="repo_inactive",
    )

    repository.set_variable_review_status(
        "VAR_REPO_INACTIVE",
        review_status="REVOKED",
        reviewed_by="manual:test",
        revocation_reason="Deprecated in tests",
    )

    default_results = repository.find_variables()
    default_ids = {entry.id for entry in default_results}
    assert "VAR_REPO_ACTIVE" in default_ids
    assert "VAR_REPO_INACTIVE" not in default_ids

    all_results = repository.find_variables(include_inactive=True)
    all_ids = {entry.id for entry in all_results}
    assert "VAR_REPO_ACTIVE" in all_ids
    assert "VAR_REPO_INACTIVE" in all_ids


def test_create_variable_rejects_unknown_domain_context(db_session: Session) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)

    with pytest.raises(ValueError, match="Unknown domain_context 'unknown_domain'"):
        repository.create_variable(
            variable_id="VAR_REPO_UNKNOWN_DOMAIN",
            canonical_name="repo_unknown_domain",
            display_name="Repo Unknown Domain",
            data_type="STRING",
            domain_context="unknown_domain",
            sensitivity="INTERNAL",
            constraints={},
            description="Should fail because domain is not approved",
            created_by="manual:test",
            source_ref="test:repository",
        )


def test_set_variable_review_status_updates_validity_fields(
    db_session: Session,
) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    _create_variable(
        repository,
        variable_id="VAR_REPO_REVIEW",
        canonical_name="repo_review",
    )

    revoked = repository.set_variable_review_status(
        "VAR_REPO_REVIEW",
        review_status="REVOKED",
        reviewed_by="manual:test",
        revocation_reason="Deprecated in tests",
    )
    assert revoked.review_status == "REVOKED"
    assert revoked.is_active is False
    assert revoked.valid_to is not None

    reactivated = repository.set_variable_review_status(
        "VAR_REPO_REVIEW",
        review_status="ACTIVE",
        reviewed_by="manual:test",
    )
    assert reactivated.review_status == "ACTIVE"
    assert reactivated.is_active is True
    assert reactivated.valid_to is None


def test_create_synonym_rejects_active_cross_variable_duplicates(
    db_session: Session,
) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    _create_variable(
        repository,
        variable_id="VAR_REPO_SYNONYM_A",
        canonical_name="repo_synonym_a",
    )
    _create_variable(
        repository,
        variable_id="VAR_REPO_SYNONYM_B",
        canonical_name="repo_synonym_b",
    )

    repository.create_synonym(
        variable_id="VAR_REPO_SYNONYM_A",
        synonym="shared alias",
        source="manual",
        created_by="manual:test",
    )

    with pytest.raises(
        ValueError,
        match=(
            "Synonym 'shared alias' is already mapped to variable 'VAR_REPO_SYNONYM_A'"
        ),
    ):
        repository.create_synonym(
            variable_id="VAR_REPO_SYNONYM_B",
            synonym="Shared Alias",
            source="manual",
            created_by="manual:test",
        )


def test_create_synonym_is_idempotent_for_same_variable_case_variants(
    db_session: Session,
) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    _create_variable(
        repository,
        variable_id="VAR_REPO_SYNONYM_SINGLE",
        canonical_name="repo_synonym_single",
    )

    first = repository.create_synonym(
        variable_id="VAR_REPO_SYNONYM_SINGLE",
        synonym="My Alias",
        source="manual",
        created_by="manual:test",
    )
    second = repository.create_synonym(
        variable_id="VAR_REPO_SYNONYM_SINGLE",
        synonym="my alias",
        source="manual",
        created_by="manual:test",
    )

    assert second.id == first.id
    assert second.synonym == "my alias"


def test_merge_variable_definition_sets_versioning_state(db_session: Session) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    _create_variable(
        repository,
        variable_id="VAR_REPO_SOURCE",
        canonical_name="repo_source",
    )
    _create_variable(
        repository,
        variable_id="VAR_REPO_TARGET",
        canonical_name="repo_target",
    )

    merged = repository.merge_variable_definition(
        "VAR_REPO_SOURCE",
        "VAR_REPO_TARGET",
        reason="Duplicate variable",
        reviewed_by="manual:test",
    )
    assert merged.review_status == "REVOKED"
    assert merged.is_active is False
    assert merged.superseded_by == "VAR_REPO_TARGET"
    assert merged.valid_to is not None

    persisted = repository.get_variable("VAR_REPO_SOURCE")
    assert persisted is not None
    assert persisted.review_status == "REVOKED"
    assert persisted.is_active is False
    assert persisted.superseded_by == "VAR_REPO_TARGET"
    assert persisted.valid_to is not None


def test_merge_entity_type_sets_versioning_state(db_session: Session) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    _create_entity_type(repository, entity_type="ENTITY_REPO_SOURCE")
    _create_entity_type(repository, entity_type="ENTITY_REPO_TARGET")

    merged = repository.merge_entity_type(
        "ENTITY_REPO_SOURCE",
        "ENTITY_REPO_TARGET",
        reason="Duplicate entity type",
        reviewed_by="manual:test",
    )
    assert merged.review_status == "REVOKED"
    assert merged.is_active is False
    assert merged.superseded_by == "ENTITY_REPO_TARGET"
    assert merged.valid_to is not None

    persisted = repository.get_entity_type(
        "ENTITY_REPO_SOURCE",
        include_inactive=True,
    )
    assert persisted is not None
    assert persisted.review_status == "REVOKED"
    assert persisted.is_active is False
    assert persisted.superseded_by == "ENTITY_REPO_TARGET"
    assert persisted.valid_to is not None

    default_results = repository.find_entity_types(domain_context="general")
    default_ids = {entry.id for entry in default_results}
    assert "ENTITY_REPO_TARGET" in default_ids
    assert "ENTITY_REPO_SOURCE" not in default_ids

    all_results = repository.find_entity_types(
        domain_context="general",
        include_inactive=True,
    )
    all_ids = {entry.id for entry in all_results}
    assert "ENTITY_REPO_TARGET" in all_ids
    assert "ENTITY_REPO_SOURCE" in all_ids


def test_merge_entity_type_repoints_existing_entities_before_revoke(
    db_session: Session,
) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    _create_entity_type(repository, entity_type="ENTITY_REPO_SRC_REPOINT")
    _create_entity_type(repository, entity_type="ENTITY_REPO_TGT_REPOINT")

    research_space_id, source_entity_id, target_entity_id = _seed_space_with_entities(
        repository,
        source_entity_type="ENTITY_REPO_SRC_REPOINT",
        target_entity_type="ENTITY_REPO_SRC_REPOINT",
    )
    assert research_space_id is not None
    assert target_entity_id is not None

    repository.merge_entity_type(
        "ENTITY_REPO_SRC_REPOINT",
        "ENTITY_REPO_TGT_REPOINT",
        reason="Entity type merge repoint test",
        reviewed_by="manual:test",
    )
    db_session.flush()

    repointed_types = db_session.scalars(
        select(EntityModel.entity_type).where(
            EntityModel.id.in_([source_entity_id, target_entity_id]),
        ),
    ).all()
    assert len(repointed_types) == 2
    assert set(repointed_types) == {"ENTITY_REPO_TGT_REPOINT"}


def test_set_entity_type_review_status_updates_validity_fields(
    db_session: Session,
) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    _create_entity_type(repository, entity_type="ENTITY_REPO_REVIEW")

    revoked = repository.set_entity_type_review_status(
        "ENTITY_REPO_REVIEW",
        review_status="REVOKED",
        reviewed_by="manual:test",
        revocation_reason="Deprecated in tests",
    )
    assert revoked.review_status == "REVOKED"
    assert revoked.is_active is False
    assert revoked.valid_to is not None

    reactivated = repository.set_entity_type_review_status(
        "ENTITY_REPO_REVIEW",
        review_status="ACTIVE",
        reviewed_by="manual:test",
    )
    assert reactivated.review_status == "ACTIVE"
    assert reactivated.is_active is True
    assert reactivated.valid_to is None


def test_merge_relation_type_sets_versioning_state(db_session: Session) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    _create_relation_type(repository, relation_type="REL_REPO_SOURCE")
    _create_relation_type(repository, relation_type="REL_REPO_TARGET")

    merged = repository.merge_relation_type(
        "REL_REPO_SOURCE",
        "REL_REPO_TARGET",
        reason="Duplicate relation type",
        reviewed_by="manual:test",
    )
    assert merged.review_status == "REVOKED"
    assert merged.is_active is False
    assert merged.superseded_by == "REL_REPO_TARGET"
    assert merged.valid_to is not None

    persisted = repository.get_relation_type(
        "REL_REPO_SOURCE",
        include_inactive=True,
    )
    assert persisted is not None
    assert persisted.review_status == "REVOKED"
    assert persisted.is_active is False
    assert persisted.superseded_by == "REL_REPO_TARGET"
    assert persisted.valid_to is not None

    default_results = repository.find_relation_types(domain_context="general")
    default_ids = {entry.id for entry in default_results}
    assert "REL_REPO_TARGET" in default_ids
    assert "REL_REPO_SOURCE" not in default_ids

    all_results = repository.find_relation_types(
        domain_context="general",
        include_inactive=True,
    )
    all_ids = {entry.id for entry in all_results}
    assert "REL_REPO_TARGET" in all_ids
    assert "REL_REPO_SOURCE" in all_ids


def test_merge_relation_type_repoints_and_merges_relation_evidence(
    db_session: Session,
) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    _create_entity_type(repository, entity_type="GENE")
    _create_entity_type(repository, entity_type="PHENOTYPE")
    _create_relation_type(repository, relation_type="REL_REPO_SRC_REL")
    _create_relation_type(repository, relation_type="REL_REPO_TGT_REL")
    research_space_id, source_entity_id, target_entity_id = _seed_space_with_entities(
        repository,
        source_entity_type="GENE",
        target_entity_type="PHENOTYPE",
    )

    source_relation = RelationModel(
        research_space_id=research_space_id,
        source_id=source_entity_id,
        relation_type="REL_REPO_SRC_REL",
        target_id=target_entity_id,
    )
    target_relation = RelationModel(
        research_space_id=research_space_id,
        source_id=source_entity_id,
        relation_type="REL_REPO_TGT_REL",
        target_id=target_entity_id,
    )
    db_session.add_all([source_relation, target_relation])
    db_session.flush()

    db_session.add_all(
        [
            RelationEvidenceModel(
                relation_id=source_relation.id,
                confidence=0.2,
                evidence_tier="COMPUTATIONAL",
                evidence_summary="source evidence",
            ),
            RelationEvidenceModel(
                relation_id=target_relation.id,
                confidence=0.7,
                evidence_tier="LITERATURE",
                evidence_summary="target evidence",
            ),
        ],
    )
    db_session.flush()

    repository.merge_relation_type(
        "REL_REPO_SRC_REL",
        "REL_REPO_TGT_REL",
        reason="Relation type merge repoint test",
        reviewed_by="manual:test",
    )
    db_session.flush()

    merged_relations = db_session.scalars(
        select(RelationModel).where(
            RelationModel.research_space_id == research_space_id,
            RelationModel.source_id == source_entity_id,
            RelationModel.target_id == target_entity_id,
            RelationModel.relation_type == "REL_REPO_TGT_REL",
        ),
    ).all()
    assert len(merged_relations) == 1
    merged_relation = merged_relations[0]

    remaining_source_relation = db_session.get(RelationModel, source_relation.id)
    assert remaining_source_relation is None

    merged_evidence = db_session.scalars(
        select(RelationEvidenceModel).where(
            RelationEvidenceModel.relation_id == merged_relation.id,
        ),
    ).all()
    assert len(merged_evidence) == 2
    assert merged_relation.source_count == 2
    assert merged_relation.highest_evidence_tier == "LITERATURE"
    assert pytest.approx(0.76, abs=1e-6) == merged_relation.aggregate_confidence


def test_create_relation_synonym_rejects_active_cross_relation_duplicates(
    db_session: Session,
) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    _create_relation_type(repository, relation_type="REL_REPO_SYNONYM_A")
    _create_relation_type(repository, relation_type="REL_REPO_SYNONYM_B")

    repository.create_relation_synonym(
        relation_type_id="REL_REPO_SYNONYM_A",
        synonym="REL_ALIAS",
        source="manual",
        created_by="manual:test",
    )

    with pytest.raises(
        ValueError,
        match=(
            "Synonym 'REL_ALIAS' is already mapped to relation type "
            "'REL_REPO_SYNONYM_A'"
        ),
    ):
        repository.create_relation_synonym(
            relation_type_id="REL_REPO_SYNONYM_B",
            synonym="rel_alias",
            source="manual",
            created_by="manual:test",
        )


def test_resolve_relation_synonym_returns_canonical_relation_type(
    db_session: Session,
) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    _create_relation_type(repository, relation_type="REL_REPO_CANONICAL")
    repository.create_relation_synonym(
        relation_type_id="REL_REPO_CANONICAL",
        synonym="REL_REPO_ALIAS",
        source="manual",
        created_by="manual:test",
    )

    resolved = repository.resolve_relation_synonym("rel_repo_alias")
    assert resolved is not None
    assert resolved.id == "REL_REPO_CANONICAL"


def test_set_relation_synonym_review_status_updates_validity_fields(
    db_session: Session,
) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    _create_relation_type(repository, relation_type="REL_REPO_SYNONYM_REVIEW")
    synonym = repository.create_relation_synonym(
        relation_type_id="REL_REPO_SYNONYM_REVIEW",
        synonym="REL_REPO_REVIEW_ALIAS",
        source="manual",
        created_by="manual:test",
    )

    revoked = repository.set_relation_synonym_review_status(
        synonym.id,
        review_status="REVOKED",
        reviewed_by="manual:test",
        revocation_reason="Deprecated in tests",
    )
    assert revoked.review_status == "REVOKED"
    assert revoked.is_active is False
    assert revoked.valid_to is not None

    reactivated = repository.set_relation_synonym_review_status(
        synonym.id,
        review_status="ACTIVE",
        reviewed_by="manual:test",
    )
    assert reactivated.review_status == "ACTIVE"
    assert reactivated.is_active is True
    assert reactivated.valid_to is None


def test_set_relation_type_review_status_updates_validity_fields(
    db_session: Session,
) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    _create_relation_type(repository, relation_type="REL_REPO_REVIEW")

    revoked = repository.set_relation_type_review_status(
        "REL_REPO_REVIEW",
        review_status="REVOKED",
        reviewed_by="manual:test",
        revocation_reason="Deprecated in tests",
    )
    assert revoked.review_status == "REVOKED"
    assert revoked.is_active is False
    assert revoked.valid_to is not None

    reactivated = repository.set_relation_type_review_status(
        "REL_REPO_REVIEW",
        review_status="ACTIVE",
        reviewed_by="manual:test",
    )
    assert reactivated.review_status == "ACTIVE"
    assert reactivated.is_active is True
    assert reactivated.valid_to is None


def test_transform_production_filter_and_promotion(db_session: Session) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    repository.create_transform(
        transform_id="TR_REPO_PROMOTE",
        input_unit="mg",
        output_unit="g",
        category="UNIT_CONVERSION",
        implementation_ref="func:std_lib.convert.mg_to_g",
        is_deterministic=True,
        is_production_allowed=False,
        test_input=1000,
        expected_output=1.0,
        status="ACTIVE",
        created_by="manual:test",
    )
    db_session.commit()

    pre_promotion = repository.get_transform(
        "mg",
        "g",
        require_production=True,
    )
    assert pre_promotion is None

    promoted = repository.promote_transform(
        "TR_REPO_PROMOTE",
        reviewed_by="manual:test",
    )
    assert promoted.is_production_allowed is True

    post_promotion = repository.get_transform(
        "mg",
        "g",
        require_production=True,
    )
    assert post_promotion is not None
    assert post_promotion.id == "TR_REPO_PROMOTE"


def test_verify_transform_reports_failure_for_bad_fixture(db_session: Session) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    repository.create_transform(
        transform_id="TR_REPO_BAD_FIXTURE",
        input_unit="kg",
        output_unit="g",
        category="UNIT_CONVERSION",
        implementation_ref="func:std_lib.convert.g_to_mg",
        is_deterministic=True,
        is_production_allowed=False,
        test_input=2,
        expected_output=2,
        status="ACTIVE",
        created_by="manual:test",
    )
    db_session.commit()

    verification = repository.verify_transform("TR_REPO_BAD_FIXTURE")
    assert verification.transform_id == "TR_REPO_BAD_FIXTURE"
    assert verification.passed is False
    assert verification.actual_output is not None


def test_create_transform_persists_phase7_fields(db_session: Session) -> None:
    repository = SqlAlchemyDictionaryRepository(db_session)
    created = repository.create_transform(
        transform_id="TR_REPO_CREATE",
        input_unit="mg/dL",
        output_unit="mmol/L",
        category="UNIT_CONVERSION",
        input_data_type="FLOAT",
        output_data_type="FLOAT",
        implementation_ref="func:std_lib.convert.mg_dl_to_mmol_l_glucose",
        is_deterministic=True,
        is_production_allowed=False,
        test_input=180.182,
        expected_output=10.0,
        description="Glucose conversion transform",
        status="ACTIVE",
        created_by="manual:test",
        source_ref="test:create-transform",
    )
    db_session.commit()

    assert created.id == "TR_REPO_CREATE"
    assert created.category == "UNIT_CONVERSION"
    assert created.input_data_type == "FLOAT"
    assert created.output_data_type == "FLOAT"
    assert created.is_deterministic is True
    assert created.is_production_allowed is False
    assert created.test_input == 180.182
    assert created.expected_output == 10.0
    assert created.description == "Glucose conversion transform"

    persisted = repository.get_transform(
        "mg/dL",
        "mmol/L",
        include_inactive=True,
    )
    assert persisted is not None
    assert persisted.id == "TR_REPO_CREATE"
