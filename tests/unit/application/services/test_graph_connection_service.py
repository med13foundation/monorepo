"""Tests for GraphConnectionService orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

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
    RejectedCandidate,
)
from src.domain.agents.ports.graph_connection_port import GraphConnectionPort

if TYPE_CHECKING:
    from src.domain.agents.contexts.graph_connection_context import (
        GraphConnectionContext,
    )
    from src.type_definitions.common import ResearchSpaceSettings


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
    """Relation repository stub that captures materialized relation calls."""

    def __post_init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.neighbourhood: list[_StubNeighbourhoodRelation] = []

    def find_neighborhood(
        self,
        entity_id: str,
        *,
        depth: int = 1,
        relation_types: list[str] | None = None,
    ) -> list[_StubNeighbourhoodRelation]:
        _ = entity_id, depth, relation_types
        return list(self.neighbourhood)


class FailingRelationRepository(StubRelationRepository):
    """Relation repository stub that raises deterministic DB integrity errors."""

    def record_materialized_relation(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        statement = "INSERT INTO relations (...)"
        raise IntegrityError(
            statement,
            {},
            Exception(
                "relation triple (GENE -> ASSOCIATED_WITH -> PHENOTYPE) is not "
                "allowed by ACTIVE relation constraints",
            ),
        )


@dataclass
class StubEntityRepository:
    entities: dict[str, object]

    def get_by_id(self, entity_id: str) -> object | None:
        return self.entities.get(entity_id)


@dataclass
class StubSpaceSettingsPort:
    settings_by_space_id: dict[str, ResearchSpaceSettings]

    def __post_init__(self) -> None:
        self.calls: list[str] = []

    def get_settings(self, space_id) -> ResearchSpaceSettings | None:
        self.calls.append(str(space_id))
        return self.settings_by_space_id.get(str(space_id))


@dataclass
class StubRelationClaimRepository:
    calls: list[dict[str, object]]

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(id=str(uuid4()))


@dataclass
class StubClaimParticipantRepository:
    calls: list[dict[str, object]]

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(id=str(uuid4()))


@dataclass
class StubClaimEvidenceRepository:
    calls: list[dict[str, object]]

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(id=str(uuid4()))


@dataclass
class StubRelationProjectionSourceRepository:
    calls: list[dict[str, object]]

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(id=str(uuid4()))


@dataclass
class FailingRelationProjectionSourceRepository:
    calls: list[dict[str, object]]

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        msg = "projection lineage write failed"
        raise ValueError(msg)


@dataclass
class StubProjectionMaterializationService:
    relation_repository: StubRelationRepository
    relation_claim_repository: StubRelationClaimRepository | None = None
    relation_projection_source_repository: (
        StubRelationProjectionSourceRepository
        | FailingRelationProjectionSourceRepository
        | None
    ) = None
    linked_relations_by_claim_id: dict[str, str] | None = None

    def __post_init__(self) -> None:
        self.materialize_calls: list[dict[str, object]] = []
        self.find_calls: list[dict[str, object]] = []

    def materialize_support_claim(
        self,
        claim_id: str,
        research_space_id: str,
        projection_origin: str,
        reviewed_by: str | None = None,
    ) -> object:
        _ = reviewed_by
        relation_id = str(uuid4())
        relation_type = None
        if (
            self.relation_claim_repository is not None
            and self.relation_claim_repository.calls
        ):
            relation_type = self.relation_claim_repository.calls[-1].get(
                "relation_type",
            )
        self.materialize_calls.append(
            {
                "claim_id": claim_id,
                "research_space_id": research_space_id,
                "projection_origin": projection_origin,
                "relation_type": relation_type,
            },
        )
        if isinstance(self.relation_repository, FailingRelationRepository):
            self.relation_repository.record_materialized_relation(
                claim_id=claim_id,
                research_space_id=research_space_id,
                projection_origin=projection_origin,
                relation_type=relation_type,
            )
        else:
            self.relation_repository.calls.append(
                {
                    "claim_id": claim_id,
                    "research_space_id": research_space_id,
                    "projection_origin": projection_origin,
                    "relation_type": relation_type,
                },
            )
        if self.relation_projection_source_repository is not None:
            self.relation_projection_source_repository.create(
                research_space_id=research_space_id,
                relation_id=relation_id,
                claim_id=claim_id,
                projection_origin=projection_origin,
                source_document_id=None,
                agent_run_id=None,
                metadata={"origin": "graph_connection"},
            )
        if (
            self.relation_claim_repository is not None
            and self.relation_claim_repository.calls
        ):
            self.relation_claim_repository.calls[-1]["linked_relation_id"] = relation_id
        return SimpleNamespace(relation=SimpleNamespace(id=relation_id))

    def find_claim_backed_relation_for_claim(
        self,
        *,
        claim_id: str,
        research_space_id: str,
    ) -> object | None:
        self.find_calls.append(
            {
                "claim_id": claim_id,
                "research_space_id": research_space_id,
            },
        )
        relation_id = None
        if self.linked_relations_by_claim_id is not None:
            relation_id = self.linked_relations_by_claim_id.get(claim_id)
        if relation_id is None:
            return None
        return SimpleNamespace(id=relation_id)


@dataclass(frozen=True)
class _StubNeighbourhoodRelation:
    source_id: str
    relation_type: str
    target_id: str
    aggregate_confidence: float
    provenance_id: str | None = None


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
    relation_type: str = "ASSOCIATED_WITH",
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
                relation_type=relation_type,
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


def _build_contract_with_rejected_candidate() -> GraphConnectionContract:
    return GraphConnectionContract(
        decision="fallback",
        confidence_score=0.35,
        rationale="No high-confidence relation candidates survived policy checks",
        evidence=[
            EvidenceItem(
                source_type="db",
                locator=f"relation:{uuid4()}",
                excerpt="Candidate rejected due uncertainty",
                relevance=0.6,
            ),
        ],
        source_type="clinvar",
        research_space_id=str(uuid4()),
        seed_entity_id=str(uuid4()),
        proposed_relations=[],
        rejected_candidates=[
            RejectedCandidate(
                source_id=str(uuid4()),
                relation_type="associates_with",
                target_id=str(uuid4()),
                reason="insufficient_supporting_documents",
                confidence=0.44,
            ),
        ],
        shadow_mode=False,
    )


def _build_empty_contract() -> GraphConnectionContract:
    return GraphConnectionContract(
        decision="fallback",
        confidence_score=0.25,
        rationale="No candidates produced",
        evidence=[
            EvidenceItem(
                source_type="db",
                locator=f"relation:{uuid4()}",
                excerpt="No candidates produced",
                relevance=0.5,
            ),
        ],
        source_type="clinvar",
        research_space_id=str(uuid4()),
        seed_entity_id=str(uuid4()),
        proposed_relations=[],
        rejected_candidates=[],
        shadow_mode=False,
    )


def _build_claim_backed_projection_dependencies(
    contract: GraphConnectionContract,
    *,
    relation_repository: StubRelationRepository | None = None,
    projection_repository: (
        StubRelationProjectionSourceRepository
        | FailingRelationProjectionSourceRepository
        | None
    ) = None,
) -> dict[str, object]:
    entity_map: dict[str, object] = {}
    for relation in contract.proposed_relations:
        entity_map[relation.source_id] = SimpleNamespace(
            id=relation.source_id,
            entity_type="GENE",
            display_label="Source Entity",
        )
        entity_map[relation.target_id] = SimpleNamespace(
            id=relation.target_id,
            entity_type="DISEASE",
            display_label="Target Entity",
        )
    relation_claim_repository = StubRelationClaimRepository(calls=[])
    effective_relation_repository = relation_repository or StubRelationRepository()
    effective_projection_repository = (
        projection_repository
        if projection_repository is not None
        else StubRelationProjectionSourceRepository(calls=[])
    )
    return {
        "entity_repository": StubEntityRepository(entities=entity_map),
        "relation_claim_repository": relation_claim_repository,
        "claim_participant_repository": StubClaimParticipantRepository(calls=[]),
        "claim_evidence_repository": StubClaimEvidenceRepository(calls=[]),
        "relation_projection_source_repository": effective_projection_repository,
        "relation_projection_materialization_service": (
            StubProjectionMaterializationService(
                relation_repository=effective_relation_repository,
                relation_claim_repository=relation_claim_repository,
                relation_projection_source_repository=effective_projection_repository,
            )
        ),
    }


@pytest.mark.asyncio
async def test_discover_connections_for_seed_writes_relations() -> None:
    contract = _build_contract()
    relation_repository = StubRelationRepository()
    projection_dependencies = _build_claim_backed_projection_dependencies(
        contract,
        relation_repository=relation_repository,
    )
    service = GraphConnectionService(
        dependencies=GraphConnectionServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent(contract),
            relation_repository=relation_repository,
            governance_service=_build_governance_service(),
            **projection_dependencies,
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
async def test_discover_connections_for_seed_records_claim_backed_projection() -> None:
    contract = _build_contract()
    proposed_relation = contract.proposed_relations[0]
    relation_repository = StubRelationRepository()
    relation_claim_repository = StubRelationClaimRepository(calls=[])
    claim_participant_repository = StubClaimParticipantRepository(calls=[])
    claim_evidence_repository = StubClaimEvidenceRepository(calls=[])
    projection_repository = StubRelationProjectionSourceRepository(calls=[])
    entity_repository = StubEntityRepository(
        entities={
            proposed_relation.source_id: SimpleNamespace(
                id=proposed_relation.source_id,
                entity_type="GENE",
                display_label="MED13",
            ),
            proposed_relation.target_id: SimpleNamespace(
                id=proposed_relation.target_id,
                entity_type="DISEASE",
                display_label="Cardiomyopathy",
            ),
        },
    )
    service = GraphConnectionService(
        dependencies=GraphConnectionServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent(contract),
            relation_repository=relation_repository,
            entity_repository=entity_repository,
            relation_claim_repository=relation_claim_repository,
            claim_participant_repository=claim_participant_repository,
            claim_evidence_repository=claim_evidence_repository,
            relation_projection_source_repository=projection_repository,
            relation_projection_materialization_service=(
                StubProjectionMaterializationService(
                    relation_repository=relation_repository,
                    relation_claim_repository=relation_claim_repository,
                    relation_projection_source_repository=projection_repository,
                )
            ),
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
    assert len(relation_claim_repository.calls) == 1
    assert relation_claim_repository.calls[0]["claim_status"] == "RESOLVED"
    assert relation_claim_repository.calls[0]["linked_relation_id"]
    assert len(claim_participant_repository.calls) == 2
    assert len(claim_evidence_repository.calls) == 1
    assert {call["role"] for call in claim_participant_repository.calls} == {
        "SUBJECT",
        "OBJECT",
    }
    assert len(projection_repository.calls) == 1
    assert projection_repository.calls[0]["projection_origin"] == "GRAPH_CONNECTION"


@pytest.mark.asyncio
async def test_discover_connections_for_seed_rolls_back_on_projection_failure() -> None:
    contract = _build_contract()
    proposed_relation = contract.proposed_relations[0]
    relation_repository = StubRelationRepository()
    relation_claim_repository = StubRelationClaimRepository(calls=[])
    claim_participant_repository = StubClaimParticipantRepository(calls=[])
    claim_evidence_repository = StubClaimEvidenceRepository(calls=[])
    projection_repository = FailingRelationProjectionSourceRepository(calls=[])
    entity_repository = StubEntityRepository(
        entities={
            proposed_relation.source_id: SimpleNamespace(
                id=proposed_relation.source_id,
                entity_type="GENE",
                display_label="MED13",
            ),
            proposed_relation.target_id: SimpleNamespace(
                id=proposed_relation.target_id,
                entity_type="DISEASE",
                display_label="Cardiomyopathy",
            ),
        },
    )
    rollback_calls: list[str] = []
    service = GraphConnectionService(
        dependencies=GraphConnectionServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent(contract),
            relation_repository=relation_repository,
            entity_repository=entity_repository,
            relation_claim_repository=relation_claim_repository,
            claim_participant_repository=claim_participant_repository,
            claim_evidence_repository=claim_evidence_repository,
            relation_projection_source_repository=projection_repository,
            relation_projection_materialization_service=(
                StubProjectionMaterializationService(
                    relation_repository=relation_repository,
                    relation_claim_repository=relation_claim_repository,
                    relation_projection_source_repository=projection_repository,
                )
            ),
            governance_service=_build_governance_service(),
            rollback_on_error=lambda: rollback_calls.append("rollback"),
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
    assert outcome.wrote_to_graph is False
    assert outcome.persisted_relations_count == 0
    assert outcome.reason == "relation_persistence_failed"
    assert outcome.errors == ("relation_payload_invalid",)
    assert rollback_calls == ["rollback"]


@pytest.mark.asyncio
async def test_discover_connections_for_seed_maps_integrity_errors_to_codes() -> None:
    contract = _build_contract()
    relation_repository = FailingRelationRepository()
    projection_dependencies = _build_claim_backed_projection_dependencies(
        contract,
        relation_repository=relation_repository,
    )
    service = GraphConnectionService(
        dependencies=GraphConnectionServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent(contract),
            relation_repository=relation_repository,
            governance_service=_build_governance_service(),
            **projection_dependencies,
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
    assert outcome.reason == "relation_persistence_failed"
    assert outcome.persisted_relations_count == 0
    assert outcome.errors == ("relation_triple_not_allowed",)


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
    projection_dependencies = _build_claim_backed_projection_dependencies(
        contract,
        relation_repository=relation_repository,
    )
    service = GraphConnectionService(
        dependencies=GraphConnectionServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent(contract),
            relation_repository=relation_repository,
            governance_service=_build_governance_service(),
            **projection_dependencies,
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
    assert outcome.review_required is True
    assert outcome.reason == "processed"
    assert len(relation_repository.calls) == 1


@pytest.mark.asyncio
async def test_discover_connections_for_seed_uses_relation_type_thresholds() -> None:
    contract = _build_contract(confidence_score=0.86, relation_type="CAUSES")
    relation_repository = StubRelationRepository()
    projection_dependencies = _build_claim_backed_projection_dependencies(
        contract,
        relation_repository=relation_repository,
    )
    service = GraphConnectionService(
        dependencies=GraphConnectionServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent(contract),
            relation_repository=relation_repository,
            governance_service=_build_governance_service(),
            **projection_dependencies,
        ),
    )

    outcome = await service.discover_connections_for_seed(
        research_space_id=contract.research_space_id,
        seed_entity_id=contract.seed_entity_id,
        source_type="clinvar",
        research_space_settings={
            "review_threshold": 0.6,
            "relation_review_thresholds": {"CAUSES": 0.9},
        },
        shadow_mode=False,
    )

    assert outcome.status == "discovered"
    assert outcome.wrote_to_graph is True
    assert outcome.review_required is True
    assert outcome.reason == "processed"
    assert len(relation_repository.calls) == 1


@pytest.mark.asyncio
async def test_discover_connections_for_seed_uses_space_settings_port() -> None:
    contract = _build_contract(confidence_score=0.86, relation_type="CAUSES")
    relation_repository = StubRelationRepository()
    projection_dependencies = _build_claim_backed_projection_dependencies(
        contract,
        relation_repository=relation_repository,
    )
    space_settings_port = StubSpaceSettingsPort(
        settings_by_space_id={
            contract.research_space_id: {
                "review_threshold": 0.6,
                "relation_review_thresholds": {"CAUSES": 0.9},
            },
        },
    )
    service = GraphConnectionService(
        dependencies=GraphConnectionServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent(contract),
            relation_repository=relation_repository,
            governance_service=_build_governance_service(),
            space_settings_port=space_settings_port,
            **projection_dependencies,
        ),
    )

    outcome = await service.discover_connections_for_seed(
        research_space_id=contract.research_space_id,
        seed_entity_id=contract.seed_entity_id,
        source_type="clinvar",
        shadow_mode=False,
    )

    assert outcome.status == "discovered"
    assert outcome.wrote_to_graph is True
    assert outcome.review_required is True
    assert outcome.reason == "processed"
    assert space_settings_port.calls == [contract.research_space_id]
    assert len(relation_repository.calls) == 1


@pytest.mark.asyncio
async def test_discover_connections_for_seed_enqueues_review_item() -> None:
    contract = _build_contract(confidence_score=0.86, relation_type="CAUSES")
    relation_repository = StubRelationRepository()
    projection_dependencies = _build_claim_backed_projection_dependencies(
        contract,
        relation_repository=relation_repository,
    )
    queued_items: list[tuple[str, str, str | None, str]] = []

    def submit_review_item(
        entity_type: str,
        entity_id: str,
        research_space_id: str | None,
        priority: str,
    ) -> None:
        queued_items.append((entity_type, entity_id, research_space_id, priority))

    service = GraphConnectionService(
        dependencies=GraphConnectionServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent(contract),
            relation_repository=relation_repository,
            governance_service=_build_governance_service(),
            review_queue_submitter=submit_review_item,
            **projection_dependencies,
        ),
    )

    outcome = await service.discover_connections_for_seed(
        research_space_id=contract.research_space_id,
        seed_entity_id=contract.seed_entity_id,
        source_type="clinvar",
        research_space_settings={
            "review_threshold": 0.6,
            "relation_review_thresholds": {"CAUSES": 0.9},
        },
        shadow_mode=False,
    )

    assert outcome.review_required is True
    assert queued_items[0] == (
        "graph_connection_seed",
        contract.seed_entity_id,
        contract.research_space_id,
        "medium",
    )
    assert queued_items[1][0] == "relation"
    assert queued_items[1][2] == contract.research_space_id


@pytest.mark.asyncio
async def test_discover_connections_for_seed_promotes_rejected_candidates() -> None:
    contract = _build_contract_with_rejected_candidate()
    relation_repository = StubRelationRepository()
    rejected_candidate = contract.rejected_candidates[0]
    relation_claim_repository = StubRelationClaimRepository(calls=[])
    projection_repository = StubRelationProjectionSourceRepository(calls=[])
    projection_dependencies = {
        "entity_repository": StubEntityRepository(
            entities={
                rejected_candidate.source_id: SimpleNamespace(
                    id=rejected_candidate.source_id,
                    entity_type="GENE",
                    display_label="Source Entity",
                ),
                rejected_candidate.target_id: SimpleNamespace(
                    id=rejected_candidate.target_id,
                    entity_type="DISEASE",
                    display_label="Target Entity",
                ),
            },
        ),
        "relation_claim_repository": relation_claim_repository,
        "claim_participant_repository": StubClaimParticipantRepository(calls=[]),
        "claim_evidence_repository": StubClaimEvidenceRepository(calls=[]),
        "relation_projection_source_repository": projection_repository,
        "relation_projection_materialization_service": (
            StubProjectionMaterializationService(
                relation_repository=relation_repository,
                relation_claim_repository=relation_claim_repository,
                relation_projection_source_repository=projection_repository,
            )
        ),
    }
    queued_items: list[tuple[str, str, str | None, str]] = []

    def submit_review_item(
        entity_type: str,
        entity_id: str,
        research_space_id: str | None,
        priority: str,
    ) -> None:
        queued_items.append((entity_type, entity_id, research_space_id, priority))

    service = GraphConnectionService(
        dependencies=GraphConnectionServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent(contract),
            relation_repository=relation_repository,
            governance_service=_build_governance_service(),
            review_queue_submitter=submit_review_item,
            **projection_dependencies,
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
    assert outcome.reason == "processed_promoted_rejected_candidates"
    assert outcome.review_required is True
    assert len(relation_repository.calls) == 1
    assert relation_repository.calls[0]["relation_type"] == "ASSOCIATES_WITH"
    assert queued_items[0] == (
        "graph_connection_seed",
        contract.seed_entity_id,
        contract.research_space_id,
        "medium",
    )
    assert queued_items[1][0] == "relation"
    assert queued_items[1][2] == contract.research_space_id


@pytest.mark.asyncio
async def test_discover_connections_for_seed_uses_neighbourhood_fallback() -> None:
    contract = _build_empty_contract()
    relation_repository = StubRelationRepository()
    relation_repository.neighbourhood = [
        _StubNeighbourhoodRelation(
            source_id=str(uuid4()),
            relation_type="ASSOCIATED_WITH",
            target_id=str(uuid4()),
            aggregate_confidence=0.82,
            provenance_id=str(uuid4()),
        ),
    ]
    fallback_contract = GraphConnectionContract.model_validate(
        contract.model_copy(
            update={
                "proposed_relations": [
                    ProposedRelation(
                        source_id=relation_repository.neighbourhood[0].source_id,
                        relation_type=relation_repository.neighbourhood[
                            0
                        ].relation_type,
                        target_id=relation_repository.neighbourhood[0].target_id,
                        confidence=relation_repository.neighbourhood[
                            0
                        ].aggregate_confidence,
                        evidence_summary="Neighbourhood fallback relation",
                        evidence_tier="COMPUTATIONAL",
                        supporting_provenance_ids=(
                            [relation_repository.neighbourhood[0].provenance_id]
                            if relation_repository.neighbourhood[0].provenance_id
                            else []
                        ),
                        supporting_document_count=1,
                        reasoning="Neighbourhood fallback",
                    ),
                ],
            },
        ),
    )
    projection_dependencies = _build_claim_backed_projection_dependencies(
        fallback_contract,
        relation_repository=relation_repository,
    )
    queued_items: list[tuple[str, str, str | None, str]] = []

    def submit_review_item(
        entity_type: str,
        entity_id: str,
        research_space_id: str | None,
        priority: str,
    ) -> None:
        queued_items.append((entity_type, entity_id, research_space_id, priority))

    service = GraphConnectionService(
        dependencies=GraphConnectionServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent(contract),
            relation_repository=relation_repository,
            governance_service=_build_governance_service(),
            review_queue_submitter=submit_review_item,
            **projection_dependencies,
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
    assert outcome.reason == "processed_seed_neighbourhood_fallback"
    assert outcome.review_required is True
    assert len(relation_repository.calls) == 1
    assert relation_repository.calls[0]["relation_type"] == "ASSOCIATED_WITH"
    assert queued_items[0] == (
        "graph_connection_seed",
        contract.seed_entity_id,
        contract.research_space_id,
        "medium",
    )
    assert queued_items[1][0] == "relation"
    assert queued_items[1][2] == contract.research_space_id
