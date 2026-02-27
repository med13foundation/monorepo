"""Domain port for interface-layer research query parsing and planning."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.kernel.dictionary import DictionarySearchResult
    from src.domain.entities.research_query import (
        ResearchQueryIntent,
        ResearchQueryPlan,
    )


class ResearchQueryPort(ABC):
    """Interface-layer API for natural-language graph query planning."""

    @abstractmethod
    def parse_intent(
        self,
        *,
        question: str,
        research_space_id: str,
    ) -> ResearchQueryIntent:
        """Parse natural-language question into structured intent."""

    @abstractmethod
    def resolve_terms(
        self,
        *,
        terms: list[str],
        domain_context: str | None = None,
        limit: int = 50,
    ) -> list[DictionarySearchResult]:
        """Resolve terms against dictionary dimensions."""

    @abstractmethod
    def build_query_plan(
        self,
        *,
        intent: ResearchQueryIntent,
        max_depth: int = 2,
        top_k: int = 25,
    ) -> ResearchQueryPlan:
        """Build an executable graph query plan from parsed intent."""


__all__ = ["ResearchQueryPort"]
