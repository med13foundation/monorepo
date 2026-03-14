"""Extension contracts for pack-owned relation suggestion semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class GraphRelationSuggestionExtension(Protocol):
    """Pack-owned runtime policy for constrained relation suggestions."""

    @property
    def vector_candidate_limit(self) -> int:
        """Return the maximum vector candidate count to retrieve."""

    @property
    def min_vector_similarity(self) -> float:
        """Return the minimum vector similarity threshold."""


@dataclass(frozen=True)
class GraphRelationSuggestionConfig:
    """Default relation-suggestion extension configuration."""

    vector_candidate_limit: int = 100
    min_vector_similarity: float = 0.0
