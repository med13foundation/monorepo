"""Unit tests for entity resolver dictionary enforcement."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from src.infrastructure.ingestion.resolution.entity_resolver import EntityResolver
from src.models.database.kernel.dictionary import EntityResolutionPolicyModel


def test_resolve_requires_dictionary_policy() -> None:
    # Setup
    dictionary_repo = Mock()
    entity_repo = Mock()
    dictionary_repo.get_resolution_policy.return_value = None
    resolver = EntityResolver(dictionary_repo, entity_repo)

    # Execute & Verify
    with pytest.raises(ValueError, match="Unknown entity_type"):
        resolver.resolve(
            anchor={"hgnc_id": "HGNC:1234"},
            entity_type="GENE",
            research_space_id="space-1",
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
