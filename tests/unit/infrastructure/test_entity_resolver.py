"""Unit tests for entity resolver dictionary enforcement."""

from __future__ import annotations

from unittest.mock import Mock

from src.infrastructure.ingestion.resolution.entity_resolver import EntityResolver
from src.models.database.kernel.dictionary import EntityResolutionPolicyModel


def test_resolve_falls_back_when_dictionary_policy_missing() -> None:
    # Setup
    dictionary_repo = Mock()
    entity_repo = Mock()
    dictionary_repo.get_entity_type.return_value = None
    created_entity_type = Mock()
    created_entity_type.id = "GENE"
    created_entity_type.is_active = True
    created_entity_type.review_status = "ACTIVE"
    dictionary_repo.create_entity_type.return_value = created_entity_type
    dictionary_repo.get_resolution_policy.return_value = None
    dictionary_repo.ensure_resolution_policy_for_entity_type.return_value = None
    created_entity = Mock()
    created_entity.id = "ent-1"
    created_entity.entity_type = "GENE"
    created_entity.display_label = "GENE HGNC:1234"
    entity_repo.resolve.return_value = None
    entity_repo.create.return_value = created_entity
    resolver = EntityResolver(dictionary_repo, entity_repo)

    # Execute
    result = resolver.resolve(
        anchor={"hgnc_id": "HGNC:1234"},
        entity_type="GENE",
        research_space_id="space-1",
    )

    # Verify fallback behavior creates a new entity via STRICT_MATCH path
    assert result.id == "ent-1"
    assert result.entity_type == "GENE"
    assert result.created is True
    dictionary_repo.get_resolution_policy.assert_called_once_with("GENE")
    entity_repo.create.assert_called_once()


def test_resolve_auto_provisions_missing_policy_for_normalized_entity_type() -> None:
    dictionary_repo = Mock()
    entity_repo = Mock()
    created_entity_type = Mock()
    created_entity_type.id = "GENE_PROTEIN"
    created_entity_type.is_active = True
    created_entity_type.review_status = "ACTIVE"
    dictionary_repo.create_entity_type.return_value = created_entity_type
    dictionary_repo.get_entity_type.return_value = None
    dictionary_repo.get_resolution_policy.return_value = None
    policy = Mock(spec=EntityResolutionPolicyModel)
    policy.policy_strategy = "STRICT_MATCH"
    policy.required_anchors = []
    dictionary_repo.ensure_resolution_policy_for_entity_type.return_value = policy

    created_entity = Mock()
    created_entity.id = "ent-2"
    created_entity.entity_type = "GENE_PROTEIN"
    created_entity.display_label = "GENE_PROTEIN BRCA1"
    entity_repo.resolve.return_value = None
    entity_repo.create.return_value = created_entity

    resolver = EntityResolver(dictionary_repo, entity_repo)

    result = resolver.resolve(
        anchor={"symbol": "BRCA1"},
        entity_type="GENE/PROTEIN",
        research_space_id="space-1",
        source_record_id="pubmed:pmid:123456",
    )

    assert result.entity_type == "GENE_PROTEIN"
    dictionary_repo.get_resolution_policy.assert_called_once_with("GENE_PROTEIN")
    dictionary_repo.create_entity_type.assert_called_once()
    dictionary_repo.ensure_resolution_policy_for_entity_type.assert_called_once_with(
        entity_type="GENE_PROTEIN",
        created_by="system:entity_resolver",
        source_ref="source_record:pubmed:pmid:123456",
        research_space_settings=None,
    )
    entity_repo.create.assert_called_once()


def test_resolve_reuses_canonical_entity_type_before_persisting() -> None:
    dictionary_repo = Mock()
    entity_repo = Mock()

    canonical_entity_type = Mock()
    canonical_entity_type.id = "PROTEIN_COMPLEX"
    canonical_entity_type.is_active = True
    canonical_entity_type.review_status = "ACTIVE"
    dictionary_repo.get_entity_type.return_value = None
    dictionary_repo.create_entity_type.return_value = canonical_entity_type

    policy = Mock(spec=EntityResolutionPolicyModel)
    policy.policy_strategy = "STRICT_MATCH"
    policy.required_anchors = []
    dictionary_repo.get_resolution_policy.return_value = policy

    created_entity = Mock()
    created_entity.id = "ent-3"
    created_entity.entity_type = "PROTEIN_COMPLEX"
    created_entity.display_label = "Mediator kinase module"
    entity_repo.resolve.return_value = None
    entity_repo.create.return_value = created_entity

    resolver = EntityResolver(dictionary_repo, entity_repo)

    result = resolver.resolve(
        anchor={"title": "Mediator kinase module"},
        entity_type="PROTEIN/PROTEIN_COMPLEX",
        research_space_id="space-1",
        source_record_id="pubmed:pmid:999",
    )

    assert result.entity_type == "PROTEIN_COMPLEX"
    dictionary_repo.create_entity_type.assert_called_once()
    entity_repo.create.assert_called_once_with(
        research_space_id="space-1",
        entity_type="PROTEIN_COMPLEX",
        display_label="Mediator kinase module",
        metadata={"title": "Mediator kinase module"},
    )


def test_resolve_allows_known_dictionary_entity_type() -> None:
    # Setup
    dictionary_repo = Mock()
    entity_repo = Mock()
    policy = Mock(spec=EntityResolutionPolicyModel)
    policy.policy_strategy = "STRICT_MATCH"
    policy.required_anchors = ["hgnc_id"]
    dictionary_repo.get_resolution_policy.return_value = policy

    existing_entity = Mock()
    existing_entity.id = "ent-1"
    existing_entity.entity_type = "GENE"
    existing_entity.display_label = "BRCA1"
    existing_entity_type = Mock()
    existing_entity_type.id = "GENE"
    existing_entity_type.is_active = True
    existing_entity_type.review_status = "ACTIVE"
    dictionary_repo.get_entity_type.return_value = existing_entity_type
    entity_repo.resolve.return_value = existing_entity

    resolver = EntityResolver(dictionary_repo, entity_repo)

    # Execute
    result = resolver.resolve(
        anchor={"hgnc_id": "HGNC:1234"},
        entity_type="GENE",
        research_space_id="space-1",
    )

    # Verify
    assert result.id == "ent-1"
    assert result.entity_type == "GENE"
    assert result.created is False
