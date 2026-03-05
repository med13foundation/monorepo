"""Unit tests for graph-based hypothesis generation service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from src.application.agents.services.hypothesis_generation_service import (
    HypothesisGenerationService,
    HypothesisGenerationServiceDependencies,
)
from src.application.services.claim_first_metrics import reset_metric_counters_for_tests
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_connection import (
    GraphConnectionContract,
    ProposedRelation,
)
from src.domain.entities.kernel.entities import KernelEntity
from src.domain.entities.kernel.relation_claims import KernelRelationClaim
from src.domain.entities.kernel.relations import KernelRelation

if TYPE_CHECKING:
    from src.domain.agents.contexts.graph_connection_context import (
        GraphConnectionContext,
    )


class StubGraphConnectionAgent:
    """Deterministic graph-agent stub keyed by seed entity ID."""

    def __init__(
        self,
        contracts_by_seed: dict[str, GraphConnectionContract],
    ) -> None:
        self._contracts_by_seed = contracts_by_seed
        self.calls: list[GraphConnectionContext] = []

    async def discover(
        self,
        context: GraphConnectionContext,
        *,
        model_id: str | None = None,
    ) -> GraphConnectionContract:
        _ = model_id
        self.calls.append(context)
        contract = self._contracts_by_seed.get(context.seed_entity_id)
        if contract is not None:
            return contract
        return _empty_contract(
            research_space_id=context.research_space_id,
            seed_entity_id=context.seed_entity_id,
            source_type=context.source_type,
        )


@dataclass
class StubRelationClaimService:
    discovery_seed_claims: list[KernelRelationClaim]
    existing_hypothesis_claims: list[KernelRelationClaim]

    def __post_init__(self) -> None:
        self.created_payloads: list[dict[str, object]] = []

    def list_by_research_space(
        self,
        research_space_id: str,
        **kwargs: object,
    ) -> list[KernelRelationClaim]:
        _ = research_space_id
        if kwargs.get("polarity") == "HYPOTHESIS":
            return list(self.existing_hypothesis_claims)
        return list(self.discovery_seed_claims)

    def create_hypothesis_claim(self, **kwargs: object) -> KernelRelationClaim:
        self.created_payloads.append(kwargs)
        return _build_claim(
            claim_id=uuid4(),
            research_space_id=UUID(str(kwargs["research_space_id"])),
            source_type=str(kwargs["source_type"]),
            relation_type=str(kwargs["relation_type"]),
            target_type=str(kwargs["target_type"]),
            source_label=(
                str(kwargs["source_label"])
                if isinstance(kwargs.get("source_label"), str)
                else None
            ),
            target_label=(
                str(kwargs["target_label"])
                if isinstance(kwargs.get("target_label"), str)
                else None
            ),
            confidence=float(kwargs["confidence"]),
            validation_state=str(kwargs["validation_state"]),
            persistability=str(kwargs["persistability"]),
            claim_status=str(kwargs.get("claim_status", "OPEN")),
            claim_text=(
                str(kwargs["claim_text"])
                if isinstance(kwargs.get("claim_text"), str)
                else None
            ),
            metadata_payload=(
                dict(kwargs["metadata"])
                if isinstance(kwargs.get("metadata"), dict)
                else {}
            ),
        )


@dataclass
class StubClaimParticipantService:
    def __post_init__(self) -> None:
        self.created_payloads: list[dict[str, object]] = []

    def create_participant(self, **kwargs: object) -> None:
        self.created_payloads.append(kwargs)


@dataclass
class StubEntityRepository:
    entities: dict[str, KernelEntity]
    fallback_entities: list[KernelEntity]

    def get_by_id(self, entity_id: str) -> KernelEntity | None:
        return self.entities.get(entity_id)

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        entity_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelEntity]:
        _ = research_space_id, entity_type, offset
        if limit is None:
            return list(self.fallback_entities)
        return list(self.fallback_entities[:limit])


@dataclass
class StubRelationRepository:
    connected_relations: list[KernelRelation]
    canonical_by_source: dict[tuple[str, str], list[KernelRelation]]

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        validation_state: str | None = None,
        source_document_id: str | None = None,
        certainty_band: str | None = None,
        node_query: str | None = None,
        node_ids: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        _ = (
            research_space_id,
            relation_type,
            curation_status,
            validation_state,
            source_document_id,
            certainty_band,
            node_query,
            node_ids,
            offset,
        )
        if limit is None:
            return list(self.connected_relations)
        return list(self.connected_relations[:limit])

    def find_by_source(
        self,
        source_id: str,
        *,
        relation_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        _ = offset
        key = (source_id, relation_type or "")
        relations = list(self.canonical_by_source.get(key, []))
        if limit is None:
            return relations
        return relations[:limit]


@dataclass
class StubDictionaryService:
    allow_all: bool = True

    def is_relation_allowed(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        _ = source_type, relation_type, target_type
        return self.allow_all


def _build_entity(
    *,
    entity_id: UUID,
    research_space_id: UUID,
    entity_type: str,
    display_label: str,
) -> KernelEntity:
    now = datetime.now(UTC)
    return KernelEntity(
        id=entity_id,
        research_space_id=research_space_id,
        entity_type=entity_type,
        display_label=display_label,
        metadata_payload={},
        created_at=now,
        updated_at=now,
    )


def _build_relation(
    *,
    relation_id: UUID,
    research_space_id: UUID,
    source_id: UUID,
    relation_type: str,
    target_id: UUID,
) -> KernelRelation:
    now = datetime.now(UTC)
    return KernelRelation(
        id=relation_id,
        research_space_id=research_space_id,
        source_id=source_id,
        relation_type=relation_type,
        target_id=target_id,
        aggregate_confidence=0.8,
        source_count=1,
        highest_evidence_tier="COMPUTATIONAL",
        curation_status="DRAFT",
        provenance_id=None,
        reviewed_by=None,
        reviewed_at=None,
        created_at=now,
        updated_at=now,
    )


def _build_claim(  # noqa: PLR0913
    *,
    claim_id: UUID,
    research_space_id: UUID,
    source_type: str,
    relation_type: str,
    target_type: str,
    source_label: str | None,
    target_label: str | None,
    confidence: float,
    validation_state: str,
    persistability: str,
    claim_status: str,
    claim_text: str | None,
    metadata_payload: dict[str, object],
) -> KernelRelationClaim:
    now = datetime.now(UTC)
    return KernelRelationClaim(
        id=claim_id,
        research_space_id=research_space_id,
        source_document_id=None,
        agent_run_id=None,
        source_type=source_type,
        relation_type=relation_type,
        target_type=target_type,
        source_label=source_label,
        target_label=target_label,
        confidence=confidence,
        validation_state=validation_state,
        validation_reason=None,
        persistability=persistability,
        claim_status=claim_status,
        polarity="HYPOTHESIS",
        claim_text=claim_text,
        claim_section=None,
        linked_relation_id=None,
        metadata_payload=metadata_payload,
        triaged_by=None,
        triaged_at=None,
        created_at=now,
        updated_at=now,
    )


def _build_contract(
    *,
    research_space_id: str,
    seed_entity_id: str,
    source_entity_id: str,
    target_entity_id: str,
    relation_type: str = "ASSOCIATED_WITH",
    confidence: float = 0.9,
    supporting_documents: int = 3,
) -> GraphConnectionContract:
    return GraphConnectionContract(
        decision="generated",
        confidence_score=0.9,
        rationale="Graph exploration completed",
        evidence=[
            EvidenceItem(
                source_type="tool",
                locator=f"seed:{seed_entity_id}",
                excerpt="Cross-edge support",
                relevance=0.9,
            ),
        ],
        source_type="pubmed",
        research_space_id=research_space_id,
        seed_entity_id=seed_entity_id,
        proposed_relations=[
            ProposedRelation(
                source_id=source_entity_id,
                relation_type=relation_type,
                target_id=target_entity_id,
                confidence=confidence,
                evidence_summary="Multi-hop support",
                evidence_tier="COMPUTATIONAL",
                supporting_provenance_ids=[str(uuid4()), str(uuid4())],
                supporting_document_count=supporting_documents,
                reasoning="Neighbourhood overlap and evidence concentration.",
            ),
        ],
        rejected_candidates=[],
        shadow_mode=True,
        agent_run_id=str(uuid4()),
    )


def _empty_contract(
    *,
    research_space_id: str,
    seed_entity_id: str,
    source_type: str,
) -> GraphConnectionContract:
    return GraphConnectionContract(
        decision="fallback",
        confidence_score=0.2,
        rationale="No candidates",
        evidence=[],
        source_type=source_type,
        research_space_id=research_space_id,
        seed_entity_id=seed_entity_id,
        proposed_relations=[],
        rejected_candidates=[],
        shadow_mode=True,
        agent_run_id=None,
    )


@pytest.mark.asyncio
async def test_generate_hypotheses_uses_claim_seed_fallback() -> None:
    reset_metric_counters_for_tests()
    research_space_id = uuid4()
    seed_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()

    discovery_claim = _build_claim(
        claim_id=uuid4(),
        research_space_id=research_space_id,
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Autism",
        confidence=0.83,
        validation_state="ALLOWED",
        persistability="PERSISTABLE",
        claim_status="OPEN",
        claim_text="seed claim",
        metadata_payload={"source_entity_id": str(seed_id)},
    )

    source_entity = _build_entity(
        entity_id=source_id,
        research_space_id=research_space_id,
        entity_type="GENE",
        display_label="MED13",
    )
    target_entity = _build_entity(
        entity_id=target_id,
        research_space_id=research_space_id,
        entity_type="PHENOTYPE",
        display_label="Autism",
    )

    contract = _build_contract(
        research_space_id=str(research_space_id),
        seed_entity_id=str(seed_id),
        source_entity_id=str(source_id),
        target_entity_id=str(target_id),
    )

    service = HypothesisGenerationService(
        dependencies=HypothesisGenerationServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent({str(seed_id): contract}),
            relation_claim_service=StubRelationClaimService(
                discovery_seed_claims=[discovery_claim],
                existing_hypothesis_claims=[],
            ),
            claim_participant_service=StubClaimParticipantService(),
            entity_repository=StubEntityRepository(
                entities={str(source_id): source_entity, str(target_id): target_entity},
                fallback_entities=[source_entity],
            ),
            relation_repository=StubRelationRepository(
                connected_relations=[],
                canonical_by_source={},
            ),
            dictionary_service=StubDictionaryService(allow_all=True),
        ),
    )

    result = await service.generate_hypotheses(
        research_space_id=str(research_space_id),
        seed_entity_ids=None,
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=20,
        model_id=None,
    )

    assert result.used_seed_count >= 1
    assert result.created_count == 1
    assert result.hypotheses


@pytest.mark.asyncio
async def test_generate_hypotheses_scores_and_maps_claim_payload() -> None:
    reset_metric_counters_for_tests()
    research_space_id = uuid4()
    seed_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()

    source_entity = _build_entity(
        entity_id=source_id,
        research_space_id=research_space_id,
        entity_type="GENE",
        display_label="MED13",
    )
    target_entity = _build_entity(
        entity_id=target_id,
        research_space_id=research_space_id,
        entity_type="PHENOTYPE",
        display_label="Autism",
    )

    contract = _build_contract(
        research_space_id=str(research_space_id),
        seed_entity_id=str(seed_id),
        source_entity_id=str(source_id),
        target_entity_id=str(target_id),
        confidence=0.88,
        supporting_documents=4,
    )

    claim_service = StubRelationClaimService(
        discovery_seed_claims=[],
        existing_hypothesis_claims=[],
    )
    participant_service = StubClaimParticipantService()
    service = HypothesisGenerationService(
        dependencies=HypothesisGenerationServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent({str(seed_id): contract}),
            relation_claim_service=claim_service,
            claim_participant_service=participant_service,
            entity_repository=StubEntityRepository(
                entities={str(source_id): source_entity, str(target_id): target_entity},
                fallback_entities=[source_entity],
            ),
            relation_repository=StubRelationRepository(
                connected_relations=[],
                canonical_by_source={},
            ),
            dictionary_service=StubDictionaryService(allow_all=True),
        ),
    )

    result = await service.generate_hypotheses(
        research_space_id=str(research_space_id),
        seed_entity_ids=[str(seed_id)],
        source_type="pubmed",
        relation_types=["ASSOCIATED_WITH"],
        max_depth=2,
        max_hypotheses=20,
        model_id=None,
    )

    assert result.created_count == 1
    assert claim_service.created_payloads
    created_payload = claim_service.created_payloads[0]
    assert created_payload["source_type"] == "GENE"
    assert created_payload["target_type"] == "PHENOTYPE"
    assert created_payload["relation_type"] == "ASSOCIATED_WITH"

    metadata = created_payload.get("metadata")
    assert isinstance(metadata, dict)
    assert metadata.get("origin") == "graph_agent"
    assert metadata.get("source_entity_id") == str(source_id)
    assert metadata.get("target_entity_id") == str(target_id)
    assert isinstance(metadata.get("candidate_score"), float)
    assert len(participant_service.created_payloads) == 2
    participants_by_role = {
        str(payload["role"]): payload
        for payload in participant_service.created_payloads
    }
    assert set(participants_by_role) == {"SUBJECT", "OBJECT"}
    subject_payload = participants_by_role["SUBJECT"]
    object_payload = participants_by_role["OBJECT"]
    assert str(subject_payload["entity_id"]) == str(source_id)
    assert str(object_payload["entity_id"]) == str(target_id)
    assert str(subject_payload["label"]) == "MED13"
    assert str(object_payload["label"]) == "Autism"


@pytest.mark.asyncio
async def test_generate_hypotheses_dedupes_existing_fingerprint() -> None:
    reset_metric_counters_for_tests()
    research_space_id = uuid4()
    seed_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()

    source_entity = _build_entity(
        entity_id=source_id,
        research_space_id=research_space_id,
        entity_type="GENE",
        display_label="MED13",
    )
    target_entity = _build_entity(
        entity_id=target_id,
        research_space_id=research_space_id,
        entity_type="PHENOTYPE",
        display_label="Autism",
    )

    fingerprint = f"{source_id}|ASSOCIATED_WITH|{target_id}|graph_agent"
    existing_hypothesis = _build_claim(
        claim_id=uuid4(),
        research_space_id=research_space_id,
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Autism",
        confidence=0.91,
        validation_state="ALLOWED",
        persistability="PERSISTABLE",
        claim_status="OPEN",
        claim_text="Existing hypothesis",
        metadata_payload={"fingerprint": fingerprint},
    )

    contract = _build_contract(
        research_space_id=str(research_space_id),
        seed_entity_id=str(seed_id),
        source_entity_id=str(source_id),
        target_entity_id=str(target_id),
    )

    claim_service = StubRelationClaimService(
        discovery_seed_claims=[],
        existing_hypothesis_claims=[existing_hypothesis],
    )

    service = HypothesisGenerationService(
        dependencies=HypothesisGenerationServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent({str(seed_id): contract}),
            relation_claim_service=claim_service,
            claim_participant_service=StubClaimParticipantService(),
            entity_repository=StubEntityRepository(
                entities={str(source_id): source_entity, str(target_id): target_entity},
                fallback_entities=[source_entity],
            ),
            relation_repository=StubRelationRepository(
                connected_relations=[],
                canonical_by_source={},
            ),
            dictionary_service=StubDictionaryService(allow_all=True),
        ),
    )

    result = await service.generate_hypotheses(
        research_space_id=str(research_space_id),
        seed_entity_ids=[str(seed_id)],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=20,
        model_id=None,
    )

    assert result.created_count == 0
    assert result.deduped_count == 1
    assert claim_service.created_payloads == []
