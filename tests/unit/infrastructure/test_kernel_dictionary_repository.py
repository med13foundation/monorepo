"""Unit tests for the SQLAlchemy kernel dictionary repository adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.repositories.kernel.kernel_dictionary_repository import (
    SqlAlchemyDictionaryRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _create_variable(
    repository: SqlAlchemyDictionaryRepository,
    *,
    variable_id: str,
    canonical_name: str,
) -> None:
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
