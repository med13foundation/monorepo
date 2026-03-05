"""Application service for kernel entity similarity via hybrid graph + embeddings."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping  # noqa: TC003
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.services.kernel.hybrid_graph_errors import EmbeddingNotReadyError
from src.application.services.kernel.hybrid_graph_scoring import (
    compute_jaccard_overlap,
    compute_similarity_score,
)
from src.domain.entities.kernel.embeddings import (
    KernelEntitySimilarityResult,
    KernelEntitySimilarityScoreBreakdown,
)

if TYPE_CHECKING:
    from src.domain.entities.kernel.entities import KernelEntity
    from src.domain.ports.text_embedding_port import TextEmbeddingPort
    from src.domain.repositories.kernel.entity_embedding_repository import (
        EntityEmbeddingRepository,
    )
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository

_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
_DEFAULT_EMBEDDING_VERSION = 1

_NON_SENSITIVE_ALIAS_FIELDS: tuple[str, ...] = (
    "aliases",
    "alias",
    "synonyms",
    "alternate_labels",
    "alt_labels",
    "keywords",
)


@dataclass(frozen=True)
class EntityEmbeddingRefreshSummary:
    """Refresh summary for explicit embedding rebuild operations."""

    requested: int
    processed: int
    refreshed: int
    unchanged: int
    missing_entities: list[str]


class KernelEntitySimilarityService:
    """Hybrid entity similarity and embedding refresh service."""

    def __init__(
        self,
        *,
        entity_repo: KernelEntityRepository,
        embedding_repo: EntityEmbeddingRepository,
        embedding_provider: TextEmbeddingPort,
        default_embedding_model: str = _DEFAULT_EMBEDDING_MODEL,
        default_embedding_version: int = _DEFAULT_EMBEDDING_VERSION,
    ) -> None:
        self._entities = entity_repo
        self._embeddings = embedding_repo
        self._embedding_provider = embedding_provider
        normalized_model = default_embedding_model.strip()
        self._default_embedding_model = (
            normalized_model if normalized_model else _DEFAULT_EMBEDDING_MODEL
        )
        self._default_embedding_version = max(1, int(default_embedding_version))

    def get_similar_entities(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int,
        min_similarity: float,
        target_entity_types: list[str] | None = None,
    ) -> list[KernelEntitySimilarityResult]:
        source_entity = self._entities.get_by_id(entity_id)
        if source_entity is None or str(source_entity.research_space_id) != str(
            research_space_id,
        ):
            msg = f"Entity {entity_id} not found in research space {research_space_id}"
            raise ValueError(msg)

        source_embedding = self._embeddings.get_embedding(entity_id=entity_id)
        if source_embedding is None:
            msg = (
                f"Embedding not ready for entity {entity_id}. "
                "Run embedding refresh before similarity search."
            )
            raise EmbeddingNotReadyError(msg)

        source_neighbor_ids = set(
            self._embeddings.list_neighbor_ids_for_overlap(
                research_space_id=research_space_id,
                entity_id=entity_id,
            ),
        )
        neighbor_cache: dict[str, set[str]] = {
            str(source_entity.id): source_neighbor_ids,
        }

        candidates = self._embeddings.find_similar_entities(
            research_space_id=research_space_id,
            entity_id=entity_id,
            limit=limit,
            min_similarity=min_similarity,
            target_entity_types=target_entity_types,
        )

        results: list[KernelEntitySimilarityResult] = []
        for candidate in candidates:
            candidate_id = str(candidate.entity_id)
            target_neighbors = neighbor_cache.get(candidate_id)
            if target_neighbors is None:
                target_neighbors = set(
                    self._embeddings.list_neighbor_ids_for_overlap(
                        research_space_id=research_space_id,
                        entity_id=candidate_id,
                    ),
                )
                neighbor_cache[candidate_id] = target_neighbors

            graph_overlap_score = compute_jaccard_overlap(
                source_neighbor_ids,
                target_neighbors,
            )
            similarity_score = compute_similarity_score(
                vector_score=candidate.vector_score,
                graph_overlap_score=graph_overlap_score,
            )
            if similarity_score < min_similarity:
                continue

            results.append(
                KernelEntitySimilarityResult(
                    entity_id=candidate.entity_id,
                    entity_type=candidate.entity_type,
                    display_label=candidate.display_label,
                    similarity_score=similarity_score,
                    score_breakdown=KernelEntitySimilarityScoreBreakdown(
                        vector_score=candidate.vector_score,
                        graph_overlap_score=graph_overlap_score,
                    ),
                ),
            )

        results.sort(key=lambda item: item.similarity_score, reverse=True)
        return results[: max(1, limit)]

    def refresh_embeddings(
        self,
        *,
        research_space_id: str,
        entity_ids: list[str] | None = None,
        limit: int = 500,
        model_name: str | None = None,
        embedding_version: int | None = None,
    ) -> EntityEmbeddingRefreshSummary:
        normalized_model_name = self._resolve_embedding_model(model_name)
        normalized_embedding_version = self._resolve_embedding_version(
            embedding_version,
        )

        candidates: list[KernelEntity] = []
        missing_entities: list[str] = []

        if entity_ids is None:
            candidates = self._entities.find_by_research_space(
                research_space_id,
                limit=max(1, limit),
                offset=0,
            )
        else:
            for entity_id in entity_ids:
                entity = self._entities.get_by_id(entity_id)
                if entity is None or str(entity.research_space_id) != str(
                    research_space_id,
                ):
                    missing_entities.append(str(entity_id))
                    continue
                candidates.append(entity)

        refreshed = 0
        unchanged = 0
        for entity in candidates:
            was_refreshed = self._upsert_entity_embedding(
                entity=entity,
                model_name=normalized_model_name,
                embedding_version=normalized_embedding_version,
            )
            if was_refreshed:
                refreshed += 1
            else:
                unchanged += 1

        return EntityEmbeddingRefreshSummary(
            requested=len(entity_ids) if entity_ids is not None else len(candidates),
            processed=len(candidates),
            refreshed=refreshed,
            unchanged=unchanged,
            missing_entities=missing_entities,
        )

    def _resolve_embedding_model(self, model_name: str | None) -> str:
        if model_name is None:
            return self._default_embedding_model
        normalized = model_name.strip()
        return normalized if normalized else self._default_embedding_model

    def _resolve_embedding_version(self, embedding_version: int | None) -> int:
        if embedding_version is None:
            return self._default_embedding_version
        return max(1, int(embedding_version))

    def _upsert_entity_embedding(
        self,
        *,
        entity: KernelEntity,
        model_name: str,
        embedding_version: int,
    ) -> bool:
        canonical_text = self._build_embedding_text(entity)
        fingerprint = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()

        existing = self._embeddings.get_embedding(entity_id=str(entity.id))
        if (
            existing is not None
            and existing.source_fingerprint == fingerprint
            and existing.embedding_model == model_name
            and existing.embedding_version == embedding_version
        ):
            return False

        vector = self._embedding_provider.embed_text(
            canonical_text,
            model_name=model_name,
        )
        if vector is None:
            msg = (
                "Embedding provider returned no vector for entity "
                f"{entity.id} with model {model_name}"
            )
            raise RuntimeError(msg)

        self._embeddings.upsert_embedding(
            research_space_id=str(entity.research_space_id),
            entity_id=str(entity.id),
            embedding=[float(item) for item in vector],
            embedding_model=model_name,
            embedding_version=embedding_version,
            source_fingerprint=fingerprint,
        )
        return True

    def _build_embedding_text(self, entity: KernelEntity) -> str:
        label = (entity.display_label or "").strip() or str(entity.id)
        segments: list[str] = [
            f"type:{entity.entity_type.strip().upper()}",
            f"label:{label}",
        ]

        metadata = entity.metadata if isinstance(entity.metadata, dict) else {}
        alias_values = self._extract_alias_values(metadata)
        segments.extend(f"alias:{alias_value}" for alias_value in alias_values)
        return "\n".join(segments)

    def _extract_alias_values(self, metadata: Mapping[str, object]) -> list[str]:
        aliases: list[str] = []
        seen: set[str] = set()
        for field_name in _NON_SENSITIVE_ALIAS_FIELDS:
            raw_value = metadata.get(field_name)
            if isinstance(raw_value, str):
                normalized = raw_value.strip()
                if not normalized:
                    continue
                dedupe_key = normalized.casefold()
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                aliases.append(normalized)
                continue

            if isinstance(raw_value, list | tuple):
                for list_item in raw_value:
                    if not isinstance(list_item, str):
                        continue
                    normalized = list_item.strip()
                    if not normalized:
                        continue
                    dedupe_key = normalized.casefold()
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    aliases.append(normalized)

        return aliases


__all__ = [
    "EntityEmbeddingRefreshSummary",
    "KernelEntitySimilarityService",
]
