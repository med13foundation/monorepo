"""Unit tests for relation-suggestion extension wiring."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from src.application.services.kernel.kernel_relation_suggestion_service import (
    KernelRelationSuggestionService,
)
from src.graph.core.relation_suggestion_extension import GraphRelationSuggestionConfig


class _StubEntityRepository:
    def __init__(self, entity: object) -> None:
        self._entity = entity

    def get_by_id(self, entity_id: str) -> object | None:
        return self._entity if str(self._entity.id) == entity_id else None


class _StubRelationRepository:
    def find_by_source(self, source_entity_id: str) -> list[object]:
        del source_entity_id
        return []

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[object]:
        del research_space_id, limit, offset
        return []

    def find_neighborhood(
        self,
        research_space_id: str,
        entity_id: str,
        depth: int = 1,
        limit: int = 500,
    ) -> list[object]:
        del research_space_id, entity_id, depth, limit
        return []


class _StubDictionaryRepository:
    def get_constraints(self, *, source_type: str) -> list[object]:
        del source_type
        return [
            SimpleNamespace(
                is_allowed=True,
                is_active=True,
                review_status="ACTIVE",
                relation_type="ASSOCIATED_WITH",
                target_type="PHENOTYPE",
            ),
        ]


class _StubEmbeddingRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get_embedding(self, *, entity_id: str) -> object | None:
        del entity_id
        return object()

    def find_similar_entities(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int,
        min_similarity: float,
        target_entity_types: list[str] | None = None,
    ) -> list[object]:
        self.calls.append(
            {
                "research_space_id": research_space_id,
                "entity_id": entity_id,
                "limit": limit,
                "min_similarity": min_similarity,
                "target_entity_types": target_entity_types,
            },
        )
        return [
            SimpleNamespace(
                entity_id=uuid4(),
                entity_type="PHENOTYPE",
                vector_score=0.9,
            ),
        ]

    def list_neighbor_ids_for_overlap(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> list[str]:
        del research_space_id, entity_id
        return []


def test_relation_suggestion_service_uses_extension_candidate_policy() -> None:
    research_space_id = uuid4()
    source_entity_id = uuid4()
    entity_repo = _StubEntityRepository(
        SimpleNamespace(
            id=source_entity_id,
            research_space_id=research_space_id,
            entity_type="GENE",
        ),
    )
    embedding_repo = _StubEmbeddingRepository()
    service = KernelRelationSuggestionService(
        entity_repo=entity_repo,
        relation_repo=_StubRelationRepository(),
        dictionary_repo=_StubDictionaryRepository(),
        embedding_repo=embedding_repo,
        relation_suggestion_extension=GraphRelationSuggestionConfig(
            vector_candidate_limit=7,
            min_vector_similarity=0.42,
        ),
    )

    results = service.suggest_relations(
        research_space_id=str(research_space_id),
        source_entity_ids=[str(source_entity_id)],
        limit_per_source=5,
        min_score=0.1,
    )

    assert len(results) == 1
    assert embedding_repo.calls == [
        {
            "research_space_id": str(research_space_id),
            "entity_id": str(source_entity_id),
            "limit": 7,
            "min_similarity": 0.42,
            "target_entity_types": ["PHENOTYPE"],
        },
    ]
