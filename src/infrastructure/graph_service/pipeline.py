"""Pipeline orchestration helpers for graph-service HTTP cutovers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING
from uuid import UUID

from src.application.agents.services.graph_connection_service import (
    GraphConnectionOutcome,
)
from src.domain.agents.contracts.graph_connection import ProposedRelation
from src.domain.agents.contracts.graph_search import GraphSearchContract
from src.domain.entities.user import User, UserRole

from .runtime import (
    build_graph_service_client_for_service,
    build_graph_service_client_for_user,
)

if TYPE_CHECKING:
    from .client import GraphServiceClient


class GraphServiceGraphSearchAdapter:
    """Async adapter that runs graph search against the standalone service."""

    def __init__(
        self,
        *,
        client_factory: Callable[[], GraphServiceClient],
    ) -> None:
        self._client_factory = client_factory

    async def search(  # noqa: PLR0913
        self,
        *,
        question: str,
        research_space_id: str,
        max_depth: int = 2,
        top_k: int = 25,
        curation_statuses: list[str] | None = None,
        include_evidence_chains: bool = True,
        force_agent: bool = False,
        model_id: str | None = None,
    ) -> GraphSearchContract:
        def _call_graph_service() -> GraphSearchContract:
            client = self._client_factory()
            try:
                return client.search_graph(
                    space_id=UUID(research_space_id),
                    question=question,
                    model_id=model_id,
                    max_depth=max_depth,
                    top_k=top_k,
                    curation_statuses=curation_statuses,
                    include_evidence_chains=include_evidence_chains,
                    force_agent=force_agent,
                )
            finally:
                client.close()

        return await asyncio.to_thread(_call_graph_service)


def build_graph_connection_seed_runner_for_user(
    current_user: User,
    *,
    client_factory: Callable[[User], GraphServiceClient] = (
        build_graph_service_client_for_user
    ),
) -> Callable[..., Awaitable[GraphConnectionOutcome]]:
    """Build one HTTP-backed graph seed runner for pipeline orchestration."""

    async def _runner(  # noqa: PLR0913
        *,
        source_id: str,
        research_space_id: str,
        seed_entity_id: str,
        source_type: str,
        model_id: str | None,
        relation_types: list[str] | None,
        max_depth: int,
        shadow_mode: bool | None,
        pipeline_run_id: str | None,
        fallback_relations: tuple[ProposedRelation, ...] | None,
    ) -> GraphConnectionOutcome:
        def _call_graph_service() -> GraphConnectionOutcome:
            client = client_factory(current_user)
            try:
                response = client.discover_entity_connections(
                    space_id=UUID(research_space_id),
                    entity_id=UUID(seed_entity_id),
                    source_type=source_type,
                    model_id=model_id,
                    relation_types=relation_types,
                    max_depth=max_depth,
                    shadow_mode=shadow_mode,
                    source_id=source_id,
                    pipeline_run_id=pipeline_run_id,
                    fallback_relations=list(fallback_relations or ()),
                )
                return GraphConnectionOutcome(
                    seed_entity_id=response.seed_entity_id,
                    research_space_id=response.research_space_id,
                    status=response.status,
                    reason=response.reason,
                    review_required=response.review_required,
                    shadow_mode=response.shadow_mode,
                    wrote_to_graph=response.wrote_to_graph,
                    run_id=response.run_id,
                    proposed_relations_count=response.proposed_relations_count,
                    persisted_relations_count=response.persisted_relations_count,
                    rejected_candidates_count=response.rejected_candidates_count,
                    errors=tuple(response.errors),
                )
            finally:
                client.close()

        return await asyncio.to_thread(_call_graph_service)

    return _runner


def build_graph_search_service_for_user(
    current_user: User,
    *,
    client_factory: Callable[[User], GraphServiceClient] = (
        build_graph_service_client_for_user
    ),
) -> GraphServiceGraphSearchAdapter:
    """Build one HTTP-backed graph-search adapter for user-scoped callers."""
    return GraphServiceGraphSearchAdapter(
        client_factory=lambda: client_factory(current_user),
    )


def build_graph_connection_seed_runner_for_service(
    *,
    role: UserRole = UserRole.VIEWER,
    client_factory: Callable[[], GraphServiceClient] | None = None,
) -> Callable[..., Awaitable[GraphConnectionOutcome]]:
    """Build one HTTP-backed graph seed runner for backend workers."""
    resolved_client_factory = client_factory or (
        lambda: build_graph_service_client_for_service(role=role)
    )

    async def _runner(  # noqa: PLR0913
        *,
        source_id: str,
        research_space_id: str,
        seed_entity_id: str,
        source_type: str,
        model_id: str | None,
        relation_types: list[str] | None,
        max_depth: int,
        shadow_mode: bool | None,
        pipeline_run_id: str | None,
        fallback_relations: tuple[ProposedRelation, ...] | None,
    ) -> GraphConnectionOutcome:
        def _call_graph_service() -> GraphConnectionOutcome:
            client = resolved_client_factory()
            try:
                response = client.discover_entity_connections(
                    space_id=UUID(research_space_id),
                    entity_id=UUID(seed_entity_id),
                    source_type=source_type,
                    model_id=model_id,
                    relation_types=relation_types,
                    max_depth=max_depth,
                    shadow_mode=shadow_mode,
                    source_id=source_id,
                    pipeline_run_id=pipeline_run_id,
                    fallback_relations=list(fallback_relations or ()),
                )
                return GraphConnectionOutcome(
                    seed_entity_id=response.seed_entity_id,
                    research_space_id=response.research_space_id,
                    status=response.status,
                    reason=response.reason,
                    review_required=response.review_required,
                    shadow_mode=response.shadow_mode,
                    wrote_to_graph=response.wrote_to_graph,
                    run_id=response.run_id,
                    proposed_relations_count=response.proposed_relations_count,
                    persisted_relations_count=response.persisted_relations_count,
                    rejected_candidates_count=response.rejected_candidates_count,
                    errors=tuple(response.errors),
                )
            finally:
                client.close()

        return await asyncio.to_thread(_call_graph_service)

    return _runner


def build_graph_search_service_for_service(
    *,
    role: UserRole = UserRole.VIEWER,
    client_factory: Callable[[], GraphServiceClient] | None = None,
) -> GraphServiceGraphSearchAdapter:
    """Build one HTTP-backed graph-search adapter for backend workers."""
    resolved_client_factory = client_factory or (
        lambda: build_graph_service_client_for_service(role=role)
    )
    return GraphServiceGraphSearchAdapter(client_factory=resolved_client_factory)


__all__ = [
    "GraphServiceGraphSearchAdapter",
    "build_graph_connection_seed_runner_for_service",
    "build_graph_connection_seed_runner_for_user",
    "build_graph_search_service_for_user",
    "build_graph_search_service_for_service",
]
