"""Application service for dictionary-constrained hybrid relation suggestions."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from src.application.services.kernel.hybrid_graph_errors import (
    ConstraintConfigMissingError,
    EmbeddingNotReadyError,
)
from src.application.services.kernel.hybrid_graph_scoring import (
    compute_jaccard_overlap,
    compute_relation_prior_score,
    compute_relation_suggestion_score,
)
from src.domain.entities.kernel.embeddings import (
    KernelRelationSuggestionConstraintCheck,
    KernelRelationSuggestionResult,
    KernelRelationSuggestionScoreBreakdown,
)

if TYPE_CHECKING:
    from src.domain.entities.kernel.entities import KernelEntity
    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )
    from src.domain.repositories.kernel.entity_embedding_repository import (
        EntityEmbeddingRepository,
    )
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
    from src.domain.repositories.kernel.relation_repository import (
        KernelRelationRepository,
    )


class KernelRelationSuggestionService:
    """Suggest missing graph edges using constrained hybrid retrieval and scoring."""

    def __init__(
        self,
        *,
        entity_repo: KernelEntityRepository,
        relation_repo: KernelRelationRepository,
        dictionary_repo: DictionaryRepository,
        embedding_repo: EntityEmbeddingRepository,
    ) -> None:
        self._entities = entity_repo
        self._relations = relation_repo
        self._dictionary = dictionary_repo
        self._embeddings = embedding_repo

    def suggest_relations(  # noqa: C901, PLR0913
        self,
        *,
        research_space_id: str,
        source_entity_ids: list[str],
        limit_per_source: int,
        min_score: float,
        allowed_relation_types: list[str] | None = None,
        target_entity_types: list[str] | None = None,
        exclude_existing_relations: bool = True,
    ) -> list[KernelRelationSuggestionResult]:
        normalized_relation_types = self._normalize_values(allowed_relation_types)
        normalized_target_types = self._normalize_values(target_entity_types)

        source_entities = self._resolve_source_entities(
            research_space_id=research_space_id,
            source_entity_ids=source_entity_ids,
        )
        relation_pair_counts, relation_totals = self._build_relation_prior_maps(
            research_space_id=research_space_id,
        )

        neighbor_cache: dict[str, set[str]] = {}
        aggregated_results: list[KernelRelationSuggestionResult] = []

        for source_entity in source_entities:
            source_id = str(source_entity.id)
            source_type = source_entity.entity_type.strip().upper()

            source_embedding = self._embeddings.get_embedding(entity_id=source_id)
            if source_embedding is None:
                msg = (
                    f"Embedding not ready for source entity {source_id}. "
                    "Run embedding refresh before relation suggestions."
                )
                raise EmbeddingNotReadyError(msg)

            source_neighbors = self._get_neighbors(
                research_space_id=research_space_id,
                entity_id=source_id,
                neighbor_cache=neighbor_cache,
            )
            existing_pairs = self._build_existing_pair_set(
                research_space_id=research_space_id,
                source_entity_id=source_id,
                enabled=exclude_existing_relations,
            )

            constraints = self._dictionary.get_constraints(source_type=source_type)
            eligible_constraints = [
                constraint
                for constraint in constraints
                if constraint.is_allowed
                and constraint.is_active
                and constraint.review_status == "ACTIVE"
                and (
                    normalized_relation_types is None
                    or constraint.relation_type.strip().upper()
                    in normalized_relation_types
                )
                and (
                    normalized_target_types is None
                    or constraint.target_type.strip().upper() in normalized_target_types
                )
            ]
            if not eligible_constraints:
                msg = (
                    "No active dictionary constraints available for source entity "
                    f"{source_id} ({source_type})."
                )
                raise ConstraintConfigMissingError(msg)

            ranked_by_key: dict[
                tuple[str, str, str],
                KernelRelationSuggestionResult,
            ] = {}
            for constraint in eligible_constraints:
                relation_type = constraint.relation_type.strip().upper()
                target_type = constraint.target_type.strip().upper()
                vector_candidates = self._embeddings.find_similar_entities(
                    research_space_id=research_space_id,
                    entity_id=source_id,
                    limit=100,
                    min_similarity=0.0,
                    target_entity_types=[target_type],
                )
                for candidate in vector_candidates:
                    target_entity_id = str(candidate.entity_id)
                    if target_entity_id == source_id:
                        continue
                    if (relation_type, target_entity_id) in existing_pairs:
                        continue

                    candidate_target_type = candidate.entity_type.strip().upper()
                    if candidate_target_type != target_type:
                        continue

                    target_neighbors = self._get_neighbors(
                        research_space_id=research_space_id,
                        entity_id=target_entity_id,
                        neighbor_cache=neighbor_cache,
                    )
                    graph_overlap_score = compute_jaccard_overlap(
                        source_neighbors,
                        target_neighbors,
                    )

                    pair_count = relation_pair_counts.get(
                        (source_type, relation_type, target_type),
                        0,
                    )
                    total_count = relation_totals.get((source_type, target_type), 0)
                    prior_score = compute_relation_prior_score(
                        pair_count=pair_count,
                        total_count=total_count,
                    )
                    final_score = compute_relation_suggestion_score(
                        vector_score=candidate.vector_score,
                        graph_overlap_score=graph_overlap_score,
                        relation_prior_score=prior_score,
                    )
                    if final_score < min_score:
                        continue

                    suggestion = KernelRelationSuggestionResult(
                        source_entity_id=source_entity.id,
                        target_entity_id=candidate.entity_id,
                        relation_type=relation_type,
                        final_score=final_score,
                        score_breakdown=KernelRelationSuggestionScoreBreakdown(
                            vector_score=candidate.vector_score,
                            graph_overlap_score=graph_overlap_score,
                            relation_prior_score=prior_score,
                        ),
                        constraint_check=KernelRelationSuggestionConstraintCheck(
                            passed=True,
                            source_entity_type=source_type,
                            relation_type=relation_type,
                            target_entity_type=target_type,
                        ),
                    )
                    dedupe_key = (source_id, target_entity_id, relation_type)
                    existing = ranked_by_key.get(dedupe_key)
                    if (
                        existing is None
                        or suggestion.final_score > existing.final_score
                    ):
                        ranked_by_key[dedupe_key] = suggestion

            source_ranked = sorted(
                ranked_by_key.values(),
                key=lambda item: item.final_score,
                reverse=True,
            )
            aggregated_results.extend(source_ranked[: max(1, limit_per_source)])

        return aggregated_results

    def _resolve_source_entities(
        self,
        *,
        research_space_id: str,
        source_entity_ids: list[str],
    ) -> list[KernelEntity]:
        seen_ids: set[str] = set()
        entities: list[KernelEntity] = []
        for source_entity_id in source_entity_ids:
            normalized_id = source_entity_id.strip()
            if not normalized_id or normalized_id in seen_ids:
                continue
            seen_ids.add(normalized_id)
            entity = self._entities.get_by_id(normalized_id)
            if entity is None or str(entity.research_space_id) != str(
                research_space_id,
            ):
                msg = (
                    f"Source entity {normalized_id} not found in "
                    f"research space {research_space_id}"
                )
                raise ValueError(msg)
            entities.append(entity)
        return entities

    def _build_existing_pair_set(
        self,
        *,
        research_space_id: str,
        source_entity_id: str,
        enabled: bool,
    ) -> set[tuple[str, str]]:
        if not enabled:
            return set()

        existing_relations = self._relations.find_by_source(source_entity_id)
        pairs: set[tuple[str, str]] = set()
        for relation in existing_relations:
            if str(relation.research_space_id) != str(research_space_id):
                continue
            pairs.add((relation.relation_type.strip().upper(), str(relation.target_id)))
        return pairs

    def _build_relation_prior_maps(
        self,
        *,
        research_space_id: str,
    ) -> tuple[dict[tuple[str, str, str], int], dict[tuple[str, str], int]]:
        relation_rows = self._relations.find_by_research_space(
            research_space_id,
            limit=None,
            offset=None,
        )
        entity_cache: dict[str, KernelEntity | None] = {}

        pair_counts: dict[tuple[str, str, str], int] = defaultdict(int)
        totals: dict[tuple[str, str], int] = defaultdict(int)

        for relation in relation_rows:
            source_entity = self._get_cached_entity(
                entity_id=str(relation.source_id),
                cache=entity_cache,
            )
            target_entity = self._get_cached_entity(
                entity_id=str(relation.target_id),
                cache=entity_cache,
            )
            if source_entity is None or target_entity is None:
                continue

            source_type = source_entity.entity_type.strip().upper()
            target_type = target_entity.entity_type.strip().upper()
            relation_type = relation.relation_type.strip().upper()

            totals[(source_type, target_type)] += 1
            pair_counts[(source_type, relation_type, target_type)] += 1

        return dict(pair_counts), dict(totals)

    def _get_cached_entity(
        self,
        *,
        entity_id: str,
        cache: dict[str, KernelEntity | None],
    ) -> KernelEntity | None:
        if entity_id in cache:
            return cache[entity_id]
        entity = self._entities.get_by_id(entity_id)
        cache[entity_id] = entity
        return entity

    def _get_neighbors(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        neighbor_cache: dict[str, set[str]],
    ) -> set[str]:
        cached = neighbor_cache.get(entity_id)
        if cached is not None:
            return cached
        neighbors = set(
            self._embeddings.list_neighbor_ids_for_overlap(
                research_space_id=research_space_id,
                entity_id=entity_id,
            ),
        )
        neighbor_cache[entity_id] = neighbors
        return neighbors

    @staticmethod
    def _normalize_values(values: list[str] | None) -> set[str] | None:
        if values is None:
            return None
        normalized: set[str] = set()
        for value in values:
            stripped = value.strip().upper()
            if not stripped:
                continue
            normalized.add(stripped)
        return normalized if normalized else None


__all__ = ["KernelRelationSuggestionService"]
