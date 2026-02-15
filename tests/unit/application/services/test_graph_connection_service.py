"""Tests for GraphConnectionService orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from src.application.agents.services.governance_service import (
    GovernancePolicy,
    GovernanceService,
)
from src.application.agents.services.graph_connection_service import (
    GraphConnectionService,
    GraphConnectionServiceDependencies,
)
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_connection import (
    GraphConnectionContract,
    ProposedRelation,
)
from src.domain.agents.ports.graph_connection_port import GraphConnectionPort

if TYPE_CHECKING:
    from src.domain.agents.contexts.graph_connection_context import (
        GraphConnectionContext,
    )


class StubGraphConnectionAgent(GraphConnectionPort):
    """Deterministic graph-connection agent stub."""

    def __init__(self, contract: GraphConnectionContract) -> None:
        self.contract = contract
        self.calls: list[GraphConnectionContext] = []

    async def discover(
        self,
        context: GraphConnectionContext,
        *,
        model_id: str | None = None,
    ) -> GraphConnectionContract:
        _ = model_id
        self.calls.append(context)
        return self.contract

    async def close(self) -> None:
        return None


@dataclass
class StubRelationRepository:
    """Relation repository stub that captures create calls."""

    def __post_init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return object()


def _build_governance_service() -> GovernanceService:
    return GovernanceService(
        policy=GovernancePolicy(
            confidence_threshold=0.8,
            require_evidence=True,
        ),
    )


def _build_contract(
    *,
    decision: str = "generated",
    confidence_score: float = 0.9,
) -> GraphConnectionContract:
    return GraphConnectionContract(
        decision=decision,
        confidence_score=confidence_score,
        rationale="Strong cross-document support",
        evidence=[
            EvidenceItem(
                source_type="db",
                locator=f"relation:{uuid4()}",
                excerpt="Neighbourhood evidence",
                relevance=0.9,
            ),
        ],
        source_type="clinvar",
        research_space_id=str(uuid4()),
        seed_entity_id=str(uuid4()),
        proposed_relations=[
            ProposedRelation(
                source_id=str(uuid4()),
                relation_type="ASSOCIATED_WITH",
                target_id=str(uuid4()),
                confidence=0.87,
                evidence_summary="Shared high-confidence neighbourhood pattern",
                evidence_tier="COMPUTATIONAL",
                supporting_provenance_ids=[str(uuid4())],
                supporting_document_count=3,
                reasoning="Multiple independent edges support this inferred relation.",
            ),
        ],
        rejected_candidates=[],
        shadow_mode=False,
    )


@pytest.mark.asyncio
async def test_discover_connections_for_seed_writes_relations() -> None:
    contract = _build_contract()
    relation_repository = StubRelationRepository()
    service = GraphConnectionService(
        dependencies=GraphConnectionServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent(contract),
            relation_repository=relation_repository,
            governance_service=_build_governance_service(),
        ),
    )

    outcome = await service.discover_connections_for_seed(
        research_space_id=contract.research_space_id,
        seed_entity_id=contract.seed_entity_id,
        source_type="clinvar",
        research_space_settings={},
        shadow_mode=False,
    )

    assert outcome.status == "discovered"
    assert outcome.wrote_to_graph is True
    assert outcome.persisted_relations_count == 1
    assert len(relation_repository.calls) == 1


@pytest.mark.asyncio
async def test_discover_connections_for_seed_respects_shadow_mode() -> None:
    contract = _build_contract()
    relation_repository = StubRelationRepository()
    service = GraphConnectionService(
        dependencies=GraphConnectionServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent(contract),
            relation_repository=relation_repository,
            governance_service=_build_governance_service(),
        ),
    )

    outcome = await service.discover_connections_for_seed(
        research_space_id=contract.research_space_id,
        seed_entity_id=contract.seed_entity_id,
        source_type="clinvar",
        research_space_settings={},
        shadow_mode=True,
    )

    assert outcome.status == "discovered"
    assert outcome.shadow_mode is True
    assert outcome.wrote_to_graph is False
    assert relation_repository.calls == []


@pytest.mark.asyncio
async def test_discover_connections_for_seed_requires_review_on_low_confidence() -> (
    None
):
    contract = _build_contract(confidence_score=0.4)
    relation_repository = StubRelationRepository()
    service = GraphConnectionService(
        dependencies=GraphConnectionServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent(contract),
            relation_repository=relation_repository,
            governance_service=_build_governance_service(),
        ),
    )

    outcome = await service.discover_connections_for_seed(
        research_space_id=contract.research_space_id,
        seed_entity_id=contract.seed_entity_id,
        source_type="clinvar",
        research_space_settings={},
        shadow_mode=False,
    )

    assert outcome.status == "failed"
    assert outcome.review_required is True
    assert outcome.reason == "confidence_below_threshold"
    assert relation_repository.calls == []
