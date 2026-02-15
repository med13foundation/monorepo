"""Port for text embedding generation services."""

from __future__ import annotations

from abc import ABC, abstractmethod


class TextEmbeddingPort(ABC):
    """Interface for computing fixed-size embedding vectors from text."""

    @abstractmethod
    def embed_text(
        self,
        text: str,
        *,
        model_name: str,
    ) -> list[float] | None:
        """Return an embedding vector for text, or None when unavailable."""


__all__ = ["TextEmbeddingPort"]
