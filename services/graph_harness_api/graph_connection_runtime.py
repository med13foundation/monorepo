"""Harness-owned graph-connection orchestration runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.agents.contexts.graph_connection_context import GraphConnectionContext
from src.graph.runtime import create_graph_domain_pack
from src.infrastructure.llm.adapters.graph_connection_agent_adapter import (
    ArtanaGraphConnectionAdapter,
)

if TYPE_CHECKING:
    from src.domain.agents.contracts.graph_connection import GraphConnectionContract
    from src.type_definitions.common import ResearchSpaceSettings


@dataclass(frozen=True, slots=True)
class HarnessGraphConnectionRequest:
    """One graph-connection AI execution request."""

    seed_entity_id: str
    research_space_id: str
    source_type: str | None
    source_id: str | None
    model_id: str | None
    relation_types: list[str] | None
    max_depth: int
    shadow_mode: bool
    pipeline_run_id: str | None
    research_space_settings: ResearchSpaceSettings


class HarnessGraphConnectionRunner:
    """Run graph-connection through Artana from the harness service."""

    async def run(
        self,
        request: HarnessGraphConnectionRequest,
    ) -> GraphConnectionContract:
        """Execute one AI-backed graph-connection request."""
        graph_domain_pack = create_graph_domain_pack()
        prompt_config = graph_domain_pack.graph_connection_prompt
        resolved_source_type = prompt_config.resolve_source_type(request.source_type)
        agent = ArtanaGraphConnectionAdapter(
            prompt_config=prompt_config,
            dictionary_service=object(),
            graph_query_service=object(),
            relation_repository=object(),
        )
        try:
            return await agent.discover(
                GraphConnectionContext(
                    seed_entity_id=request.seed_entity_id,
                    source_type=resolved_source_type,
                    research_space_id=request.research_space_id,
                    source_id=request.source_id,
                    pipeline_run_id=request.pipeline_run_id,
                    research_space_settings=request.research_space_settings,
                    relation_types=request.relation_types,
                    max_depth=request.max_depth,
                    shadow_mode=request.shadow_mode,
                ),
                model_id=request.model_id,
            )
        finally:
            await agent.close()


__all__ = ["HarnessGraphConnectionRequest", "HarnessGraphConnectionRunner"]
