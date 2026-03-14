"""Harness-owned graph-search orchestration runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.agents.contexts.graph_search_context import GraphSearchContext
from src.graph.runtime import create_graph_domain_pack
from src.infrastructure.llm.adapters.graph_search_agent_adapter import (
    ArtanaGraphSearchAdapter,
)

if TYPE_CHECKING:
    from src.domain.agents.contracts.graph_search import GraphSearchContract


@dataclass(frozen=True, slots=True)
class HarnessGraphSearchRequest:
    """One graph-search AI execution request."""

    question: str
    research_space_id: str
    max_depth: int
    top_k: int
    curation_statuses: list[str] | None
    include_evidence_chains: bool
    model_id: str | None


class HarnessGraphSearchRunner:
    """Run graph-search through Artana from the harness service."""

    async def run(
        self,
        request: HarnessGraphSearchRequest,
    ) -> GraphSearchContract:
        """Execute one AI-backed graph-search request."""
        graph_domain_pack = create_graph_domain_pack()
        agent = ArtanaGraphSearchAdapter(
            search_extension=graph_domain_pack.search_extension,
            graph_query_service=object(),
        )
        try:
            return await agent.search(
                GraphSearchContext(
                    question=request.question,
                    research_space_id=request.research_space_id,
                    max_depth=request.max_depth,
                    top_k=request.top_k,
                    curation_statuses=request.curation_statuses,
                    include_evidence_chains=request.include_evidence_chains,
                    force_agent=True,
                ),
                model_id=request.model_id,
            )
        finally:
            await agent.close()


__all__ = ["HarnessGraphSearchRequest", "HarnessGraphSearchRunner"]
