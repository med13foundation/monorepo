"""Unit tests for DictionaryManagementService."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from unittest.mock import Mock

import pytest

from src.application.services.kernel.dictionary_management_service import (
    DictionaryManagementService,
)
from src.domain.entities.kernel.dictionary import (
    DictionaryChangelog,
    DictionaryEntityType,
    DictionaryRelationType,
    DictionarySearchResult,
    RelationConstraint,
    ValueSet,
    ValueSetItem,
    VariableDefinition,
    VariableSynonym,
)
from src.domain.ports.dictionary_search_harness_port import DictionarySearchHarnessPort
from src.domain.ports.text_embedding_port import TextEmbeddingPort
from src.domain.repositories.kernel.dictionary_repository import DictionaryRepository


class StubEmbeddingProvider(TextEmbeddingPort):
    """Deterministic test embedding provider."""

    def embed_text(
        self,
        text: str,
        *,
        model_name: str,
    ) -> list[float] | None:
        normalized = text.strip()
        if not normalized:
            return None
        return [float(len(normalized)), float(len(model_name))]


class StubDictionarySearchHarness(DictionarySearchHarnessPort):
    """Deterministic search harness stub."""

    def __init__(
        self,
        *,
        results: list[DictionarySearchResult] | None = None,
        dictionary_repo: Mock | None = None,
    ) -> None:
        self.results = results
        self.dictionary_repo = dictionary_repo
        self.calls = 0
        self.last_terms: list[str] = []
        self.last_dimensions: list[str] | None = None
        self.last_domain_context: str | None = None
        self.last_limit: int = 0
        self.last_include_inactive: bool = False

    def search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        self.calls += 1
        self.last_terms = terms
        self.last_dimensions = dimensions
        self.last_domain_context = domain_context
        self.last_limit = limit
        self.last_include_inactive = include_inactive
        if self.dictionary_repo is None:
            if self.results is None:
                return []
            return list(self.results)
        return self.dictionary_repo.search_dictionary(
            terms=terms,
            dimensions=dimensions,
            domain_context=domain_context,
            limit=limit,
            query_embeddings=None,
            include_inactive=include_inactive,
        )


def _build_variable(
    *,
    review_status: str = "ACTIVE",
    data_type: str = "STRING",
) -> VariableDefinition:
    now = datetime.now(UTC)
    return VariableDefinition(
        id="VAR_TEST",
        canonical_name="test_variable",
        display_name="Test Variable",
        data_type=data_type,
        preferred_unit=None,
        constraints={},
        domain_context="general",
        sensitivity="INTERNAL",
        description="test",
        created_by="seed",
        source_ref=None,
        review_status=review_status,
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        created_at=now,
        updated_at=now,
    )


def _build_synonym(*, review_status: str = "ACTIVE") -> VariableSynonym:
    now = datetime.now(UTC)
    return VariableSynonym(
        id=1,
        variable_id="VAR_TEST",
        synonym="test synonym",
        source="manual",
        created_by="seed",
        source_ref=None,
        review_status=review_status,
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        created_at=now,
        updated_at=now,
    )


def _build_entity_type(*, review_status: str = "ACTIVE") -> DictionaryEntityType:
    now = datetime.now(UTC)
    return DictionaryEntityType(
        id="GENE",
        display_name="Gene",
        description="Gene entity type",
        domain_context="general",
        external_ontology_ref=None,
        expected_properties={},
        description_embedding=None,
        created_by="seed",
        source_ref=None,
        review_status=review_status,
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        created_at=now,
        updated_at=now,
    )


def _build_relation_type(*, review_status: str = "ACTIVE") -> DictionaryRelationType:
    now = datetime.now(UTC)
    return DictionaryRelationType(
        id="ASSOCIATED_WITH",
        display_name="Associated With",
        description="Association relation",
        domain_context="general",
        is_directional=True,
        inverse_label=None,
        description_embedding=None,
        created_by="seed",
        source_ref=None,
        review_status=review_status,
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        created_at=now,
        updated_at=now,
    )


def _build_relation_constraint(
    *,
    review_status: str = "ACTIVE",
) -> RelationConstraint:
    now = datetime.now(UTC)
    return RelationConstraint(
        id=1,
        source_type="VARIANT",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        is_allowed=True,
        requires_evidence=True,
        created_by="seed",
        source_ref=None,
        review_status=review_status,
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        created_at=now,
        updated_at=now,
    )


def _build_changelog() -> DictionaryChangelog:
    now = datetime.now(UTC)
    return DictionaryChangelog(
        id=1,
        table_name="variable_definitions",
        record_id="VAR_TEST",
        action="CREATE",
        before_snapshot=None,
        after_snapshot={"id": "VAR_TEST"},
        changed_by="manual:user-1",
        source_ref="paper:123",
        created_at=now,
        updated_at=now,
    )


def _build_search_result(
    *,
    entry_id: str = "VAR_TEST",
    display_name: str = "Test Variable",
    description: str | None = "test",
    match_method: Literal["exact", "synonym", "fuzzy", "vector"] = "exact",
    similarity_score: float = 1.0,
) -> DictionarySearchResult:
    return DictionarySearchResult(
        dimension="variables",
        entry_id=entry_id,
        display_name=display_name,
        description=description,
        domain_context="general",
        match_method=match_method,
        similarity_score=similarity_score,
        metadata={"canonical_name": f"{entry_id.lower()}_canonical"},
    )


def _build_value_set(
    *,
    is_extensible: bool = False,
    review_status: str = "ACTIVE",
) -> ValueSet:
    now = datetime.now(UTC)
    return ValueSet(
        id="VS_TEST",
        variable_id="VAR_TEST_CODED",
        variable_data_type="CODED",
        name="Test Value Set",
        description="Test coded values",
        external_ref=None,
        is_extensible=is_extensible,
        created_by="seed",
        source_ref=None,
        review_status=review_status,
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        created_at=now,
        updated_at=now,
    )


def _build_value_set_item(
    *,
    is_active: bool = True,
    review_status: str = "ACTIVE",
) -> ValueSetItem:
    now = datetime.now(UTC)
    return ValueSetItem(
        id=1,
        value_set_id="VS_TEST",
        code="PATHOGENIC",
        display_label="Pathogenic",
        synonyms=["path"],
        external_ref=None,
        sort_order=0,
        is_active=is_active,
        created_by="seed",
        source_ref=None,
        review_status=review_status,
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def dictionary_repo() -> Mock:
    repo = Mock(spec=DictionaryRepository)
    repo.search_dictionary.return_value = []
    return repo


@pytest.fixture
def embedding_provider() -> StubEmbeddingProvider:
    return StubEmbeddingProvider()


@pytest.fixture
def service(
    dictionary_repo: Mock,
    embedding_provider: StubEmbeddingProvider,
) -> DictionaryManagementService:
    return DictionaryManagementService(
        dictionary_repo=dictionary_repo,
        dictionary_search_harness=StubDictionarySearchHarness(
            dictionary_repo=dictionary_repo,
        ),
        embedding_provider=embedding_provider,
    )


def test_create_variable_uses_space_policy_for_agent(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.create_variable.return_value = _build_variable(
        review_status="PENDING_REVIEW",
    )

    service.create_variable(
        variable_id="VAR_TEST",
        canonical_name="test_variable",
        display_name="Test Variable",
        data_type="STRING",
        created_by="agent:run-123",
        research_space_settings={
            "dictionary_agent_creation_policy": "PENDING_REVIEW",
        },
    )

    called_kwargs = dictionary_repo.create_variable.call_args.kwargs
    assert called_kwargs["review_status"] == "PENDING_REVIEW"


def test_create_variable_manual_creation_forces_active(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.create_variable.return_value = _build_variable(
        review_status="ACTIVE",
    )

    service.create_variable(
        variable_id="VAR_TEST",
        canonical_name="test_variable",
        display_name="Test Variable",
        data_type="STRING",
        created_by="manual:user-123",
        research_space_settings={
            "dictionary_agent_creation_policy": "PENDING_REVIEW",
        },
    )

    called_kwargs = dictionary_repo.create_variable.call_args.kwargs
    assert called_kwargs["review_status"] == "ACTIVE"


def test_create_variable_embeds_description_before_persist(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.create_variable.return_value = _build_variable()

    service.create_variable(
        variable_id="VAR_TEST",
        canonical_name="test_variable",
        display_name="Test Variable",
        data_type="STRING",
        description="Variable description",
        created_by="manual:user-123",
    )

    called_kwargs = dictionary_repo.create_variable.call_args.kwargs
    assert isinstance(called_kwargs["description_embedding"], list)
    assert called_kwargs["embedding_model"] == "text-embedding-3-small"
    assert called_kwargs["embedded_at"] is not None


def test_create_variable_validates_and_normalizes_numeric_constraints(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.create_variable.return_value = _build_variable(data_type="INTEGER")

    service.create_variable(
        variable_id="VAR_TEST_NUMERIC",
        canonical_name="test_numeric",
        display_name="Test Numeric",
        data_type="integer",
        constraints={"min": 0, "max": 10, "precision": 2},
        created_by="manual:user-123",
    )

    called_kwargs = dictionary_repo.create_variable.call_args.kwargs
    assert called_kwargs["data_type"] == "INTEGER"
    assert called_kwargs["constraints"] == {"min": 0.0, "max": 10.0, "precision": 2}


def test_create_variable_rejects_invalid_constraint_bounds(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.create_variable.return_value = _build_variable(data_type="INTEGER")

    with pytest.raises(
        ValueError,
        match="Invalid constraints for data_type 'INTEGER'",
    ):
        service.create_variable(
            variable_id="VAR_TEST_NUMERIC",
            canonical_name="test_numeric",
            display_name="Test Numeric",
            data_type="INTEGER",
            constraints={"min": 10, "max": 1},
            created_by="manual:user-123",
        )


def test_create_variable_rejects_unknown_constraint_keys(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.create_variable.return_value = _build_variable(data_type="BOOLEAN")

    with pytest.raises(
        ValueError,
        match="Invalid constraints for data_type 'BOOLEAN'",
    ):
        service.create_variable(
            variable_id="VAR_TEST_BOOLEAN",
            canonical_name="test_boolean",
            display_name="Test Boolean",
            data_type="BOOLEAN",
            constraints={"unexpected": True},
            created_by="manual:user-123",
        )


def test_create_variable_rejects_unsupported_data_type(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    with pytest.raises(ValueError, match="Unsupported data_type"):
        service.create_variable(
            variable_id="VAR_TEST_UNKNOWN",
            canonical_name="test_unknown",
            display_name="Test Unknown",
            data_type="VECTOR",
            constraints={},
            created_by="manual:user-123",
        )


def test_set_review_status_requires_reason_for_revoked(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_variable.return_value = _build_variable(review_status="ACTIVE")

    with pytest.raises(
        ValueError,
        match="revocation_reason is required when setting REVOKED status",
    ):
        service.set_review_status(
            "VAR_TEST",
            review_status="REVOKED",
            reviewed_by="manual:user-123",
        )


def test_set_review_status_disallows_revoked_to_pending_review(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_variable.return_value = _build_variable(review_status="REVOKED")

    with pytest.raises(ValueError, match="Invalid review transition"):
        service.set_review_status(
            "VAR_TEST",
            review_status="PENDING_REVIEW",
            reviewed_by="manual:user-123",
        )


def test_revoke_variable_updates_review_state(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_variable.return_value = _build_variable(review_status="ACTIVE")
    dictionary_repo.set_variable_review_status.return_value = _build_variable(
        review_status="REVOKED",
    )

    updated = service.revoke_variable(
        "VAR_TEST",
        reason="Deprecated semantic definition",
        reviewed_by="manual:user-123",
    )

    assert updated.review_status == "REVOKED"
    dictionary_repo.set_variable_review_status.assert_called_once_with(
        "VAR_TEST",
        review_status="REVOKED",
        reviewed_by="manual:user-123",
        revocation_reason="Deprecated semantic definition",
    )


def test_create_value_set_requires_coded_variable(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_variable.return_value = _build_variable(data_type="STRING")

    with pytest.raises(ValueError, match="cannot have a value set"):
        service.create_value_set(
            value_set_id="VS_TEST",
            variable_id="VAR_TEST",
            name="Test Value Set",
            created_by="manual:user-123",
        )


def test_create_value_set_uses_space_policy_for_agent(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_variable.return_value = _build_variable(data_type="CODED")
    dictionary_repo.create_value_set.return_value = _build_value_set(
        review_status="PENDING_REVIEW",
    )

    service.create_value_set(
        value_set_id="VS_TEST",
        variable_id="VAR_TEST",
        name="Test Value Set",
        created_by="agent:run-123",
        research_space_settings={
            "dictionary_agent_creation_policy": "PENDING_REVIEW",
        },
    )

    called_kwargs = dictionary_repo.create_value_set.call_args.kwargs
    assert called_kwargs["review_status"] == "PENDING_REVIEW"


def test_create_value_set_item_blocks_agent_when_not_extensible(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_value_set.return_value = _build_value_set(is_extensible=False)

    with pytest.raises(ValueError, match="not extensible"):
        service.create_value_set_item(
            value_set_id="VS_TEST",
            code="LIKELY_PATHOGENIC",
            display_label="Likely Pathogenic",
            created_by="agent:run-123",
        )


def test_create_value_set_item_allows_manual_when_not_extensible(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_value_set.return_value = _build_value_set(is_extensible=False)
    dictionary_repo.create_value_set_item.return_value = _build_value_set_item()

    service.create_value_set_item(
        value_set_id="VS_TEST",
        code="LIKELY_PATHOGENIC",
        display_label="Likely Pathogenic",
        synonyms=["likely path"],
        created_by="manual:user-123",
    )

    called_kwargs = dictionary_repo.create_value_set_item.call_args.kwargs
    assert called_kwargs["review_status"] == "ACTIVE"


def test_set_value_set_item_active_requires_reason_on_deactivate(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    with pytest.raises(
        ValueError,
        match="revocation_reason is required when deactivating a value set item",
    ):
        service.set_value_set_item_active(
            1,
            is_active=False,
            reviewed_by="manual:user-123",
        )


def test_set_value_set_item_active_delegates_to_repository(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.set_value_set_item_active.return_value = _build_value_set_item(
        is_active=False,
        review_status="REVOKED",
    )

    item = service.set_value_set_item_active(
        1,
        is_active=False,
        reviewed_by="manual:user-123",
        revocation_reason="Deprecated code",
    )

    assert item.is_active is False
    assert item.review_status == "REVOKED"
    dictionary_repo.set_value_set_item_active.assert_called_once_with(
        1,
        is_active=False,
        reviewed_by="manual:user-123",
        revocation_reason="Deprecated code",
    )


def test_create_synonym_uses_space_policy_for_agent(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_variable.return_value = _build_variable(review_status="ACTIVE")
    dictionary_repo.create_synonym.return_value = _build_synonym(
        review_status="PENDING_REVIEW",
    )

    service.create_synonym(
        variable_id="VAR_TEST",
        synonym="alias value",
        source="agent",
        created_by="agent:run-123",
        research_space_settings={
            "dictionary_agent_creation_policy": "PENDING_REVIEW",
        },
    )

    called_kwargs = dictionary_repo.create_synonym.call_args.kwargs
    assert called_kwargs["review_status"] == "PENDING_REVIEW"


def test_create_synonym_requires_existing_variable(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_variable.return_value = None
    with pytest.raises(ValueError, match="Variable 'VAR_MISSING' not found"):
        service.create_synonym(
            variable_id="VAR_MISSING",
            synonym="missing alias",
            created_by="manual:user-1",
        )


def test_requires_evidence_delegates_to_repository(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.requires_evidence.return_value = False
    requires_evidence = service.requires_evidence(
        "GENE",
        "ASSOCIATED_WITH",
        "PHENOTYPE",
    )
    assert requires_evidence is False
    dictionary_repo.requires_evidence.assert_called_once_with(
        "GENE",
        "ASSOCIATED_WITH",
        "PHENOTYPE",
    )


def test_set_entity_type_review_status_requires_reason_for_revoked(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_entity_type.return_value = _build_entity_type(
        review_status="ACTIVE",
    )

    with pytest.raises(
        ValueError,
        match="revocation_reason is required when setting REVOKED status",
    ):
        service.set_entity_type_review_status(
            "GENE",
            review_status="REVOKED",
            reviewed_by="manual:user-123",
        )


def test_revoke_entity_type_updates_review_state(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_entity_type.return_value = _build_entity_type(
        review_status="ACTIVE",
    )
    dictionary_repo.set_entity_type_review_status.return_value = _build_entity_type(
        review_status="REVOKED",
    )

    updated = service.revoke_entity_type(
        "GENE",
        reason="Deprecated entity type",
        reviewed_by="manual:user-123",
    )

    assert updated.review_status == "REVOKED"
    dictionary_repo.set_entity_type_review_status.assert_called_once_with(
        "GENE",
        review_status="REVOKED",
        reviewed_by="manual:user-123",
        revocation_reason="Deprecated entity type",
    )


def test_set_relation_type_review_status_requires_reason_for_revoked(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_relation_type.return_value = _build_relation_type(
        review_status="ACTIVE",
    )

    with pytest.raises(
        ValueError,
        match="revocation_reason is required when setting REVOKED status",
    ):
        service.set_relation_type_review_status(
            "ASSOCIATED_WITH",
            review_status="REVOKED",
            reviewed_by="manual:user-123",
        )


def test_revoke_relation_type_updates_review_state(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_relation_type.return_value = _build_relation_type(
        review_status="ACTIVE",
    )
    dictionary_repo.set_relation_type_review_status.return_value = _build_relation_type(
        review_status="REVOKED",
    )

    updated = service.revoke_relation_type(
        "ASSOCIATED_WITH",
        reason="Deprecated relation type",
        reviewed_by="manual:user-123",
    )

    assert updated.review_status == "REVOKED"
    dictionary_repo.set_relation_type_review_status.assert_called_once_with(
        "ASSOCIATED_WITH",
        review_status="REVOKED",
        reviewed_by="manual:user-123",
        revocation_reason="Deprecated relation type",
    )


def test_create_relation_constraint_uses_space_policy_for_agent(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_entity_type.return_value = _build_entity_type()
    dictionary_repo.get_relation_type.return_value = _build_relation_type()
    dictionary_repo.create_relation_constraint.return_value = (
        _build_relation_constraint(
            review_status="PENDING_REVIEW",
        )
    )

    service.create_relation_constraint(
        source_type="VARIANT",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        created_by="agent:run-123",
        research_space_settings={"dictionary_agent_creation_policy": "PENDING_REVIEW"},
    )

    called_kwargs = dictionary_repo.create_relation_constraint.call_args.kwargs
    assert called_kwargs["review_status"] == "PENDING_REVIEW"
    assert called_kwargs["source_type"] == "VARIANT"
    assert called_kwargs["target_type"] == "PHENOTYPE"


def test_create_relation_constraint_requires_existing_relation_type(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_entity_type.return_value = _build_entity_type()
    dictionary_repo.get_relation_type.return_value = None

    with pytest.raises(ValueError, match="Relation type 'ASSOCIATED_WITH' not found"):
        service.create_relation_constraint(
            source_type="VARIANT",
            relation_type="ASSOCIATED_WITH",
            target_type="PHENOTYPE",
            created_by="manual:user-123",
        )


def test_list_changelog_entries_delegates_to_repository(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.find_changelog_entries.return_value = [_build_changelog()]

    entries = service.list_changelog_entries(
        table_name="variable_definitions",
        record_id="VAR_TEST",
        limit=20,
    )

    assert len(entries) == 1
    assert entries[0].action == "CREATE"
    dictionary_repo.find_changelog_entries.assert_called_once_with(
        table_name="variable_definitions",
        record_id="VAR_TEST",
        limit=20,
    )


def test_list_variables_passes_include_inactive_flag(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.find_variables.return_value = [_build_variable()]

    service.list_variables(include_inactive=True)

    dictionary_repo.find_variables.assert_called_once_with(
        domain_context=None,
        data_type=None,
        include_inactive=True,
    )


def test_dictionary_search_delegates_to_harness_when_configured(
    dictionary_repo: Mock,
) -> None:
    harness_result = _build_search_result(
        entry_id="VAR_HARNESS",
        display_name="Harness Variable",
        match_method="vector",
        similarity_score=0.88,
    )
    harness = StubDictionarySearchHarness(results=[harness_result])
    service = DictionaryManagementService(
        dictionary_repo=dictionary_repo,
        dictionary_search_harness=harness,
        embedding_provider=StubEmbeddingProvider(),
    )

    results = service.dictionary_search(
        terms=[" Harness Variable "],
        dimensions=["variables"],
        domain_context="cardiology",
        limit=7,
        include_inactive=True,
    )

    assert len(results) == 1
    assert results[0].entry_id == "VAR_HARNESS"
    assert harness.calls == 1
    assert harness.last_terms == ["Harness Variable"]
    assert harness.last_dimensions == ["variables"]
    assert harness.last_domain_context == "cardiology"
    assert harness.last_limit == 7
    assert harness.last_include_inactive is True
    dictionary_repo.search_dictionary.assert_not_called()


def test_dictionary_search_passes_include_inactive_flag(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.search_dictionary.return_value = [_build_search_result()]

    service.dictionary_search(
        terms=["Test Variable"],
        include_inactive=True,
    )

    called_kwargs = dictionary_repo.search_dictionary.call_args.kwargs
    assert called_kwargs["include_inactive"] is True


def test_dictionary_search_short_circuits_on_deterministic_hit(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.search_dictionary.return_value = [_build_search_result()]

    results = service.dictionary_search(
        terms=["test variable"],
        dimensions=["variables"],
    )

    assert len(results) == 1
    assert results[0].match_method == "exact"
    assert dictionary_repo.search_dictionary.call_count == 1


def test_create_variable_reuses_existing_entry_on_deterministic_match(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    existing = _build_variable()
    dictionary_repo.search_dictionary.return_value = [
        _build_search_result(
            entry_id=existing.id,
            display_name=existing.display_name,
            match_method="exact",
            similarity_score=1.0,
        ),
    ]
    dictionary_repo.get_variable.return_value = existing

    resolved = service.create_variable(
        variable_id="VAR_NEW",
        canonical_name="new_variable",
        display_name="New Variable",
        data_type="STRING",
        domain_context="general",
        created_by="agent:run-123",
    )

    assert resolved.id == existing.id
    dictionary_repo.create_variable.assert_not_called()


def test_create_entity_type_reuses_existing_on_exact_search_match(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    existing = _build_entity_type()
    dictionary_repo.search_dictionary.return_value = [
        DictionarySearchResult(
            dimension="entity_types",
            entry_id="GENE",
            display_name="Gene",
            description="Gene entity type",
            domain_context="general",
            match_method="exact",
            similarity_score=1.0,
            metadata={},
        ),
    ]
    dictionary_repo.get_entity_type.return_value = existing

    resolved = service.create_entity_type(
        entity_type="GENE_ALIAS",
        display_name="Gene",
        description="Alias description",
        domain_context="general",
        created_by="agent:run-123",
    )

    assert resolved.id == "GENE"
    dictionary_repo.create_entity_type.assert_not_called()


def test_create_relation_type_reuses_existing_on_exact_search_match(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    existing = _build_relation_type()
    dictionary_repo.search_dictionary.return_value = [
        DictionarySearchResult(
            dimension="relation_types",
            entry_id="ASSOCIATED_WITH",
            display_name="Associated With",
            description="Association relation",
            domain_context="general",
            match_method="exact",
            similarity_score=1.0,
            metadata={},
        ),
    ]
    dictionary_repo.get_relation_type.return_value = existing

    resolved = service.create_relation_type(
        relation_type="ASSOCIATES_WITH_ALIAS",
        display_name="Associated With",
        description="Alias relation",
        domain_context="general",
        created_by="agent:run-123",
    )

    assert resolved.id == "ASSOCIATED_WITH"
    dictionary_repo.create_relation_type.assert_not_called()


def test_set_entity_type_review_status_queries_inactive_records(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_entity_type.return_value = _build_entity_type(
        review_status="REVOKED",
    )
    dictionary_repo.set_entity_type_review_status.return_value = _build_entity_type(
        review_status="ACTIVE",
    )

    service.set_entity_type_review_status(
        "GENE",
        review_status="ACTIVE",
        reviewed_by="manual:user-123",
    )

    dictionary_repo.get_entity_type.assert_called_once_with(
        "GENE",
        include_inactive=True,
    )


def test_set_relation_type_review_status_queries_inactive_records(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.get_relation_type.return_value = _build_relation_type(
        review_status="REVOKED",
    )
    dictionary_repo.set_relation_type_review_status.return_value = _build_relation_type(
        review_status="ACTIVE",
    )

    service.set_relation_type_review_status(
        "ASSOCIATED_WITH",
        review_status="ACTIVE",
        reviewed_by="manual:user-123",
    )

    dictionary_repo.get_relation_type.assert_called_once_with(
        "ASSOCIATED_WITH",
        include_inactive=True,
    )


def test_merge_variable_definition_delegates_with_validation(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.merge_variable_definition.return_value = _build_variable(
        review_status="REVOKED",
    )

    merged = service.merge_variable_definition(
        "VAR_SOURCE",
        "VAR_TARGET",
        reason="Canonical consolidation",
        reviewed_by="manual:user-123",
    )

    assert merged.review_status == "REVOKED"
    dictionary_repo.merge_variable_definition.assert_called_once_with(
        "VAR_SOURCE",
        "VAR_TARGET",
        reason="Canonical consolidation",
        reviewed_by="manual:user-123",
    )


def test_merge_variable_definition_requires_distinct_ids(
    service: DictionaryManagementService,
) -> None:
    with pytest.raises(ValueError, match="must differ"):
        service.merge_variable_definition(
            "VAR_SAME",
            "VAR_SAME",
            reason="Invalid merge",
            reviewed_by="manual:user-123",
        )


def test_merge_entity_type_delegates_with_validation(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.merge_entity_type.return_value = _build_entity_type(
        review_status="REVOKED",
    )

    merged = service.merge_entity_type(
        "ENTITY_A",
        "ENTITY_B",
        reason="Canonical consolidation",
        reviewed_by="manual:user-123",
    )

    assert merged.review_status == "REVOKED"
    dictionary_repo.merge_entity_type.assert_called_once_with(
        "ENTITY_A",
        "ENTITY_B",
        reason="Canonical consolidation",
        reviewed_by="manual:user-123",
    )


def test_merge_relation_type_delegates_with_validation(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.merge_relation_type.return_value = _build_relation_type(
        review_status="REVOKED",
    )

    merged = service.merge_relation_type(
        "REL_A",
        "REL_B",
        reason="Canonical consolidation",
        reviewed_by="manual:user-123",
    )

    assert merged.review_status == "REVOKED"
    dictionary_repo.merge_relation_type.assert_called_once_with(
        "REL_A",
        "REL_B",
        reason="Canonical consolidation",
        reviewed_by="manual:user-123",
    )


def test_reembed_descriptions_updates_all_supported_dimensions(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    dictionary_repo.find_variables.return_value = [_build_variable()]
    dictionary_repo.find_entity_types.return_value = [_build_entity_type()]
    dictionary_repo.find_relation_types.return_value = [_build_relation_type()]

    updated_records = service.reembed_descriptions(
        changed_by="manual:user-123",
        source_ref="job:test-reembed",
    )

    assert updated_records == 3
    dictionary_repo.set_variable_embedding.assert_called_once()
    dictionary_repo.set_entity_type_embedding.assert_called_once()
    dictionary_repo.set_relation_type_embedding.assert_called_once()


def test_get_transform_forwards_require_production_flag(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    service.get_transform(
        "mg",
        "g",
        require_production=True,
    )

    dictionary_repo.get_transform.assert_called_once_with(
        "mg",
        "g",
        include_inactive=False,
        require_production=True,
    )


def test_verify_transform_delegates_to_repository(
    service: DictionaryManagementService,
    dictionary_repo: Mock,
) -> None:
    service.verify_transform("TR_TEST")
    dictionary_repo.verify_transform.assert_called_once_with("TR_TEST")


def test_promote_transform_requires_actor(
    service: DictionaryManagementService,
) -> None:
    with pytest.raises(ValueError, match="reviewed_by is required"):
        service.promote_transform("TR_TEST", reviewed_by=" ")
