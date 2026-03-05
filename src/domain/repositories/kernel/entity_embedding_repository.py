"""Kernel entity embedding repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.kernel.embeddings import (
        KernelEntityEmbedding,
        KernelEntitySimilarityCandidate,
    )


class EntityEmbeddingRepository(ABC):
    """Persistence contract for entity embeddings and vector lookup."""

    @abstractmethod
    def upsert_embedding(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        entity_id: str,
        embedding: list[float],
        embedding_model: str,
        embedding_version: int,
        source_fingerprint: str,
    ) -> KernelEntityEmbedding:
        """Create or update the embedding row for one entity."""

    @abstractmethod
    def get_embedding(
        self,
        *,
        entity_id: str,
    ) -> KernelEntityEmbedding | None:
        """Return embedding metadata for one entity when available."""

    @abstractmethod
    def find_similar_entities(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int,
        min_similarity: float,
        target_entity_types: list[str] | None = None,
    ) -> list[KernelEntitySimilarityCandidate]:
        """Find nearest neighbors for one source entity within a research space."""

    @abstractmethod
    def list_neighbor_ids_for_overlap(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> list[str]:
        """Return unique neighboring entity IDs for graph-overlap scoring."""


__all__ = ["EntityEmbeddingRepository"]
