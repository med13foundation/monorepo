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
from src.application.services.kernel.kernel_reasoning_path_service import (
    KernelReasoningPathDetail,
    ReasoningPathListResult,
)
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_connection import (
    GraphConnectionContract,
    ProposedRelation,
)
from src.domain.entities.kernel.claim_evidence import KernelClaimEvidence
from src.domain.entities.kernel.claim_participants import KernelClaimParticipant
from src.domain.entities.kernel.claim_relations import KernelClaimRelation
from src.domain.entities.kernel.entities import KernelEntity
from src.domain.entities.kernel.reasoning_paths import (
    KernelReasoningPath,
    KernelReasoningPathStep,
)
from src.domain.entities.kernel.relation_claims import KernelRelationClaim
from src.domain.entities.kernel.relations import KernelRelation

pytestmark = pytest.mark.graph

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

    def list_claims_by_ids(self, claim_ids: list[str]) -> list[KernelRelationClaim]:
        allowed = set(claim_ids)
        return [
            claim
            for claim in (
                list(self.discovery_seed_claims) + list(self.existing_hypothesis_claims)
            )
            if str(claim.id) in allowed
        ]

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
    participants_by_claim: dict[str, list[KernelClaimParticipant]] | None = None
    claim_ids_by_entity: dict[str, list[str]] | None = None

    def __post_init__(self) -> None:
        self.created_payloads: list[dict[str, object]] = []
        if self.participants_by_claim is None:
            self.participants_by_claim = {}
        if self.claim_ids_by_entity is None:
            self.claim_ids_by_entity = {}

    def create_participant(self, **kwargs: object) -> None:
        self.created_payloads.append(kwargs)

    def list_for_claim_ids(
        self,
        claim_ids: list[str],
    ) -> dict[str, list[KernelClaimParticipant]]:
        return {
            claim_id: list(self.participants_by_claim.get(claim_id, []))
            for claim_id in claim_ids
        }

    def list_claim_ids_by_entity(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[str]:
        _ = research_space_id, offset
        claim_ids = list(self.claim_ids_by_entity.get(entity_id, []))
        if limit is None:
            return claim_ids
        return claim_ids[:limit]


@dataclass
class StubClaimEvidenceService:
    evidence_by_claim: dict[str, list[KernelClaimEvidence]] | None = None

    def __post_init__(self) -> None:
        if self.evidence_by_claim is None:
            self.evidence_by_claim = {}

    def list_for_claim_ids(
        self,
        claim_ids: list[str],
    ) -> dict[str, list[KernelClaimEvidence]]:
        return {
            claim_id: list(self.evidence_by_claim.get(claim_id, []))
            for claim_id in claim_ids
        }


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
        claim_backed_only: bool = True,
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
            claim_backed_only,
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


@dataclass
class StubReasoningPathService:
    paths_by_start_entity: dict[str, list[KernelReasoningPath]]
    details_by_id: dict[str, KernelReasoningPathDetail]

    def list_paths(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        start_entity_id: str | None = None,
        end_entity_id: str | None = None,
        status: str | None = None,
        path_kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ReasoningPathListResult:
        del research_space_id, end_entity_id, status, path_kind, offset
        paths = list(self.paths_by_start_entity.get(start_entity_id or "", []))
        return ReasoningPathListResult(
            paths=tuple(paths[:limit]),
            total=len(paths),
            offset=0,
            limit=limit,
        )

    def get_path(
        self,
        path_id: str,
        research_space_id: str,
    ) -> KernelReasoningPathDetail | None:
        detail = self.details_by_id.get(path_id)
        if detail is None or str(detail.path.research_space_id) != research_space_id:
            return None
        return detail


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


def _build_reasoning_path(
    *,
    path_id: UUID,
    research_space_id: UUID,
    start_entity_id: UUID,
    end_entity_id: UUID,
    root_claim_id: UUID,
    path_length: int,
    confidence: float,
    metadata_payload: dict[str, object],
) -> KernelReasoningPath:
    now = datetime.now(UTC)
    return KernelReasoningPath(
        id=path_id,
        research_space_id=research_space_id,
        path_kind="MECHANISM",
        status="ACTIVE",
        start_entity_id=start_entity_id,
        end_entity_id=end_entity_id,
        root_claim_id=root_claim_id,
        path_length=path_length,
        confidence=confidence,
        path_signature_hash=f"path:{path_id}",
        generated_by="test",
        generated_at=now,
        metadata_payload=metadata_payload,
        created_at=now,
        updated_at=now,
    )


def _build_path_step(
    *,
    path_id: UUID,
    source_claim_id: UUID,
    target_claim_id: UUID,
    claim_relation_id: UUID,
    step_index: int = 0,
) -> KernelReasoningPathStep:
    return KernelReasoningPathStep(
        id=uuid4(),
        path_id=path_id,
        step_index=step_index,
        source_claim_id=source_claim_id,
        target_claim_id=target_claim_id,
        claim_relation_id=claim_relation_id,
        canonical_relation_id=None,
        metadata_payload={},
        created_at=datetime.now(UTC),
    )


def _build_claim_participant(
    *,
    claim_id: UUID,
    research_space_id: UUID,
    role: str,
    entity_id: UUID,
    position: int,
) -> KernelClaimParticipant:
    return KernelClaimParticipant(
        id=uuid4(),
        claim_id=claim_id,
        research_space_id=research_space_id,
        label=None,
        entity_id=entity_id,
        role=role,  # type: ignore[arg-type]
        position=position,
        qualifiers={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _build_claim_evidence(*, claim_id: UUID) -> KernelClaimEvidence:
    return KernelClaimEvidence(
        id=uuid4(),
        claim_id=claim_id,
        source_document_id=None,
        agent_run_id=None,
        sentence="evidence",
        sentence_source="verbatim_span",
        sentence_confidence="high",
        sentence_rationale=None,
        figure_reference=None,
        table_reference=None,
        confidence=0.8,
        metadata_payload={},
        created_at=datetime.now(UTC),
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
            claim_evidence_service=StubClaimEvidenceService(),
            entity_repository=StubEntityRepository(
                entities={str(source_id): source_entity, str(target_id): target_entity},
                fallback_entities=[source_entity],
            ),
            relation_repository=StubRelationRepository(
                connected_relations=[],
                canonical_by_source={},
            ),
            dictionary_service=StubDictionaryService(allow_all=True),
            reasoning_path_service=None,
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
            claim_evidence_service=StubClaimEvidenceService(),
            entity_repository=StubEntityRepository(
                entities={str(source_id): source_entity, str(target_id): target_entity},
                fallback_entities=[source_entity],
            ),
            relation_repository=StubRelationRepository(
                connected_relations=[],
                canonical_by_source={},
            ),
            dictionary_service=StubDictionaryService(allow_all=True),
            reasoning_path_service=None,
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
            claim_evidence_service=StubClaimEvidenceService(),
            entity_repository=StubEntityRepository(
                entities={str(source_id): source_entity, str(target_id): target_entity},
                fallback_entities=[source_entity],
            ),
            relation_repository=StubRelationRepository(
                connected_relations=[],
                canonical_by_source={},
            ),
            dictionary_service=StubDictionaryService(allow_all=True),
            reasoning_path_service=None,
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


@pytest.mark.asyncio
async def test_generate_hypotheses_is_deterministic_for_identical_inputs() -> None:
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
        confidence=0.91,
        supporting_documents=5,
    )

    def _build_service() -> (
        tuple[HypothesisGenerationService, StubRelationClaimService]
    ):
        claim_service = StubRelationClaimService(
            discovery_seed_claims=[],
            existing_hypothesis_claims=[],
        )
        service = HypothesisGenerationService(
            dependencies=HypothesisGenerationServiceDependencies(
                graph_connection_agent=StubGraphConnectionAgent(
                    {str(seed_id): contract},
                ),
                relation_claim_service=claim_service,
                claim_participant_service=StubClaimParticipantService(),
                claim_evidence_service=StubClaimEvidenceService(),
                entity_repository=StubEntityRepository(
                    entities={
                        str(source_id): source_entity,
                        str(target_id): target_entity,
                    },
                    fallback_entities=[source_entity],
                ),
                relation_repository=StubRelationRepository(
                    connected_relations=[],
                    canonical_by_source={},
                ),
                dictionary_service=StubDictionaryService(allow_all=True),
                reasoning_path_service=None,
            ),
        )
        return service, claim_service

    first_service, first_claim_service = _build_service()
    second_service, second_claim_service = _build_service()

    first_result = await first_service.generate_hypotheses(
        research_space_id=str(research_space_id),
        seed_entity_ids=[str(seed_id)],
        source_type="pubmed",
        relation_types=["ASSOCIATED_WITH"],
        max_depth=2,
        max_hypotheses=20,
        model_id=None,
    )
    second_result = await second_service.generate_hypotheses(
        research_space_id=str(research_space_id),
        seed_entity_ids=[str(seed_id)],
        source_type="pubmed",
        relation_types=["ASSOCIATED_WITH"],
        max_depth=2,
        max_hypotheses=20,
        model_id=None,
    )

    assert first_result.created_count == 1
    assert second_result.created_count == 1
    first_payload = first_claim_service.created_payloads[0]
    second_payload = second_claim_service.created_payloads[0]
    assert first_payload["source_type"] == second_payload["source_type"]
    assert first_payload["target_type"] == second_payload["target_type"]
    assert first_payload["relation_type"] == second_payload["relation_type"]
    assert first_payload["confidence"] == second_payload["confidence"]
    assert first_payload["claim_text"] == second_payload["claim_text"]
    first_metadata = {
        key: value
        for key, value in first_payload["metadata"].items()
        if key != "run_id"
    }
    second_metadata = {
        key: value
        for key, value in second_payload["metadata"].items()
        if key != "run_id"
    }
    assert first_metadata == second_metadata


@pytest.mark.asyncio
async def test_generate_hypotheses_prefers_active_reasoning_paths() -> None:
    reset_metric_counters_for_tests()
    research_space_id = uuid4()
    start_entity_id = uuid4()
    end_entity_id = uuid4()
    root_claim_id = uuid4()
    final_claim_id = uuid4()
    claim_relation_id = uuid4()
    path_id = uuid4()

    start_entity = _build_entity(
        entity_id=start_entity_id,
        research_space_id=research_space_id,
        entity_type="GENE",
        display_label="MED13",
    )
    end_entity = _build_entity(
        entity_id=end_entity_id,
        research_space_id=research_space_id,
        entity_type="PHENOTYPE",
        display_label="Speech delay",
    )
    root_claim = _build_claim(
        claim_id=root_claim_id,
        research_space_id=research_space_id,
        source_type="GENE",
        relation_type="PART_OF",
        target_type="COMPLEX",
        source_label="MED13",
        target_label="Mediator complex",
        confidence=0.8,
        validation_state="ALLOWED",
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        claim_text="Root claim",
        metadata_payload={},
    ).model_copy(update={"polarity": "SUPPORT"})
    final_claim = _build_claim(
        claim_id=final_claim_id,
        research_space_id=research_space_id,
        source_type="PROCESS",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="Transcription dysregulation",
        target_label="Speech delay",
        confidence=0.82,
        validation_state="ALLOWED",
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        claim_text="Final claim",
        metadata_payload={},
    ).model_copy(update={"polarity": "SUPPORT"})

    path = _build_reasoning_path(
        path_id=path_id,
        research_space_id=research_space_id,
        start_entity_id=start_entity_id,
        end_entity_id=end_entity_id,
        root_claim_id=root_claim_id,
        path_length=1,
        confidence=0.74,
        metadata_payload={
            "terminal_relation_type": "ASSOCIATED_WITH",
            "supporting_claim_ids": [str(root_claim_id), str(final_claim_id)],
        },
    )
    path_detail = KernelReasoningPathDetail(
        path=path,
        steps=(
            _build_path_step(
                path_id=path_id,
                source_claim_id=root_claim_id,
                target_claim_id=final_claim_id,
                claim_relation_id=claim_relation_id,
            ),
        ),
        claims=(root_claim, final_claim),
        claim_relations=(
            KernelClaimRelation(
                id=claim_relation_id,
                research_space_id=research_space_id,
                source_claim_id=root_claim_id,
                target_claim_id=final_claim_id,
                relation_type="CAUSES",
                agent_run_id=None,
                source_document_id=None,
                confidence=0.74,
                review_status="ACCEPTED",
                evidence_summary=None,
                metadata_payload={},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ),
        canonical_relations=(),
        participants=(
            _build_claim_participant(
                claim_id=root_claim_id,
                research_space_id=research_space_id,
                role="SUBJECT",
                entity_id=start_entity_id,
                position=0,
            ),
            _build_claim_participant(
                claim_id=final_claim_id,
                research_space_id=research_space_id,
                role="OBJECT",
                entity_id=end_entity_id,
                position=1,
            ),
        ),
        evidence=(
            _build_claim_evidence(claim_id=root_claim_id),
            _build_claim_evidence(claim_id=final_claim_id),
        ),
    )

    claim_service = StubRelationClaimService(
        discovery_seed_claims=[],
        existing_hypothesis_claims=[],
    )
    participant_service = StubClaimParticipantService()
    service = HypothesisGenerationService(
        dependencies=HypothesisGenerationServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent({}),
            relation_claim_service=claim_service,
            claim_participant_service=participant_service,
            claim_evidence_service=StubClaimEvidenceService(),
            entity_repository=StubEntityRepository(
                entities={
                    str(start_entity_id): start_entity,
                    str(end_entity_id): end_entity,
                },
                fallback_entities=[start_entity],
            ),
            relation_repository=StubRelationRepository(
                connected_relations=[],
                canonical_by_source={},
            ),
            dictionary_service=StubDictionaryService(allow_all=True),
            reasoning_path_service=StubReasoningPathService(
                paths_by_start_entity={str(start_entity_id): [path]},
                details_by_id={str(path_id): path_detail},
            ),
        ),
    )

    result = await service.generate_hypotheses(
        research_space_id=str(research_space_id),
        seed_entity_ids=[str(start_entity_id)],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
    )

    assert result.created_count == 1
    metadata = claim_service.created_payloads[0]["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["origin"] == "reasoning_path"
    assert metadata["reasoning_path_id"] == str(path_id)
    assert metadata["supporting_claim_ids"] == [
        str(root_claim_id),
        str(final_claim_id),
    ]
    assert metadata["path_length"] == 1
    assert len(participant_service.created_payloads) == 2


@pytest.mark.asyncio
async def test_generate_hypotheses_creates_transfer_backed_hypothesis() -> None:
    reset_metric_counters_for_tests()
    research_space_id = uuid4()
    start_entity_id = uuid4()
    neighbor_entity_id = uuid4()
    end_entity_id = uuid4()
    root_claim_id = uuid4()
    final_claim_id = uuid4()
    transfer_claim_id = uuid4()
    claim_relation_id = uuid4()
    path_id = uuid4()

    start_entity = _build_entity(
        entity_id=start_entity_id,
        research_space_id=research_space_id,
        entity_type="GENE",
        display_label="MED13",
    )
    neighbor_entity = _build_entity(
        entity_id=neighbor_entity_id,
        research_space_id=research_space_id,
        entity_type="GENE",
        display_label="MED12",
    )
    end_entity = _build_entity(
        entity_id=end_entity_id,
        research_space_id=research_space_id,
        entity_type="PHENOTYPE",
        display_label="Speech delay",
    )
    root_claim = _build_claim(
        claim_id=root_claim_id,
        research_space_id=research_space_id,
        source_type="GENE",
        relation_type="PART_OF",
        target_type="COMPLEX",
        source_label="MED13",
        target_label="Mediator complex",
        confidence=0.84,
        validation_state="ALLOWED",
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        claim_text="Root claim",
        metadata_payload={},
    ).model_copy(update={"polarity": "SUPPORT"})
    final_claim = _build_claim(
        claim_id=final_claim_id,
        research_space_id=research_space_id,
        source_type="PROCESS",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="Transcription dysregulation",
        target_label="Speech delay",
        confidence=0.81,
        validation_state="ALLOWED",
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        claim_text="Final claim",
        metadata_payload={},
    ).model_copy(update={"polarity": "SUPPORT"})
    transfer_claim = _build_claim(
        claim_id=transfer_claim_id,
        research_space_id=research_space_id,
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED12",
        target_label="Speech delay",
        confidence=0.86,
        validation_state="ALLOWED",
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        claim_text="Transferred support claim",
        metadata_payload={},
    ).model_copy(update={"polarity": "SUPPORT"})

    path = _build_reasoning_path(
        path_id=path_id,
        research_space_id=research_space_id,
        start_entity_id=start_entity_id,
        end_entity_id=end_entity_id,
        root_claim_id=root_claim_id,
        path_length=1,
        confidence=0.79,
        metadata_payload={
            "terminal_relation_type": "ASSOCIATED_WITH",
            "supporting_claim_ids": [str(root_claim_id), str(final_claim_id)],
        },
    )
    path_detail = KernelReasoningPathDetail(
        path=path,
        steps=(
            _build_path_step(
                path_id=path_id,
                source_claim_id=root_claim_id,
                target_claim_id=final_claim_id,
                claim_relation_id=claim_relation_id,
            ),
        ),
        claims=(root_claim, final_claim),
        claim_relations=(
            KernelClaimRelation(
                id=claim_relation_id,
                research_space_id=research_space_id,
                source_claim_id=root_claim_id,
                target_claim_id=final_claim_id,
                relation_type="CAUSES",
                agent_run_id=None,
                source_document_id=None,
                confidence=0.79,
                review_status="ACCEPTED",
                evidence_summary=None,
                metadata_payload={},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ),
        canonical_relations=(),
        participants=(),
        evidence=(
            _build_claim_evidence(claim_id=root_claim_id),
            _build_claim_evidence(claim_id=final_claim_id),
        ),
    )

    claim_service = StubRelationClaimService(
        discovery_seed_claims=[transfer_claim],
        existing_hypothesis_claims=[],
    )
    participant_service = StubClaimParticipantService(
        participants_by_claim={
            str(transfer_claim_id): [
                _build_claim_participant(
                    claim_id=transfer_claim_id,
                    research_space_id=research_space_id,
                    role="SUBJECT",
                    entity_id=neighbor_entity_id,
                    position=0,
                ),
                _build_claim_participant(
                    claim_id=transfer_claim_id,
                    research_space_id=research_space_id,
                    role="OBJECT",
                    entity_id=end_entity_id,
                    position=1,
                ),
            ],
        },
        claim_ids_by_entity={str(neighbor_entity_id): [str(transfer_claim_id)]},
    )
    service = HypothesisGenerationService(
        dependencies=HypothesisGenerationServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent({}),
            relation_claim_service=claim_service,
            claim_participant_service=participant_service,
            claim_evidence_service=StubClaimEvidenceService(
                evidence_by_claim={
                    str(transfer_claim_id): [
                        _build_claim_evidence(claim_id=transfer_claim_id),
                    ],
                },
            ),
            entity_repository=StubEntityRepository(
                entities={
                    str(start_entity_id): start_entity,
                    str(neighbor_entity_id): neighbor_entity,
                    str(end_entity_id): end_entity,
                },
                fallback_entities=[start_entity],
            ),
            relation_repository=StubRelationRepository(
                connected_relations=[
                    _build_relation(
                        relation_id=uuid4(),
                        research_space_id=research_space_id,
                        source_id=start_entity_id,
                        relation_type="PART_OF",
                        target_id=neighbor_entity_id,
                    ),
                ],
                canonical_by_source={},
            ),
            dictionary_service=StubDictionaryService(allow_all=True),
            reasoning_path_service=StubReasoningPathService(
                paths_by_start_entity={str(start_entity_id): [path]},
                details_by_id={str(path_id): path_detail},
            ),
        ),
    )

    result = await service.generate_hypotheses(
        research_space_id=str(research_space_id),
        seed_entity_ids=[str(start_entity_id)],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
    )

    assert result.created_count == 1
    metadata = claim_service.created_payloads[0]["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["origin"] == "mechanism_transfer"
    assert metadata["reasoning_path_id"] == str(path_id)
    assert metadata["transferred_from_entities"] == [str(neighbor_entity_id)]
    assert metadata["direct_supporting_claim_ids"] == [
        str(root_claim_id),
        str(final_claim_id),
    ]
    assert metadata["transferred_supporting_claim_ids"] == [str(transfer_claim_id)]
    assert "explanation" in metadata


@pytest.mark.asyncio
async def test_generate_hypotheses_blocks_transfer_when_contradictions_dominate() -> (
    None
):
    reset_metric_counters_for_tests()
    research_space_id = uuid4()
    start_entity_id = uuid4()
    neighbor_entity_id = uuid4()
    end_entity_id = uuid4()
    root_claim_id = uuid4()
    final_claim_id = uuid4()
    transfer_claim_id = uuid4()
    contradiction_claim_ids = [uuid4(), uuid4(), uuid4(), uuid4()]
    claim_relation_id = uuid4()
    path_id = uuid4()

    start_entity = _build_entity(
        entity_id=start_entity_id,
        research_space_id=research_space_id,
        entity_type="GENE",
        display_label="MED13",
    )
    neighbor_entity = _build_entity(
        entity_id=neighbor_entity_id,
        research_space_id=research_space_id,
        entity_type="GENE",
        display_label="MED16",
    )
    end_entity = _build_entity(
        entity_id=end_entity_id,
        research_space_id=research_space_id,
        entity_type="PHENOTYPE",
        display_label="Speech delay",
    )
    root_claim = _build_claim(
        claim_id=root_claim_id,
        research_space_id=research_space_id,
        source_type="GENE",
        relation_type="PART_OF",
        target_type="COMPLEX",
        source_label="MED13",
        target_label="Mediator complex",
        confidence=0.73,
        validation_state="ALLOWED",
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        claim_text="Root claim",
        metadata_payload={},
    ).model_copy(update={"polarity": "SUPPORT"})
    final_claim = _build_claim(
        claim_id=final_claim_id,
        research_space_id=research_space_id,
        source_type="PROCESS",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="Transcription dysregulation",
        target_label="Speech delay",
        confidence=0.71,
        validation_state="ALLOWED",
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        claim_text="Final claim",
        metadata_payload={},
    ).model_copy(update={"polarity": "SUPPORT"})
    transfer_claim = _build_claim(
        claim_id=transfer_claim_id,
        research_space_id=research_space_id,
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED16",
        target_label="Speech delay",
        confidence=0.74,
        validation_state="ALLOWED",
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        claim_text="Transfer support claim",
        metadata_payload={},
    ).model_copy(update={"polarity": "SUPPORT"})

    contradiction_claims = [
        _build_claim(
            claim_id=claim_id,
            research_space_id=research_space_id,
            source_type="GENE",
            relation_type="ASSOCIATED_WITH",
            target_type="PHENOTYPE",
            source_label="MED16",
            target_label="Speech delay",
            confidence=0.65,
            validation_state="ALLOWED",
            persistability="NON_PERSISTABLE",
            claim_status="OPEN",
            claim_text="Contradiction claim",
            metadata_payload={},
        ).model_copy(update={"polarity": "REFUTE"})
        for claim_id in contradiction_claim_ids
    ]

    path = _build_reasoning_path(
        path_id=path_id,
        research_space_id=research_space_id,
        start_entity_id=start_entity_id,
        end_entity_id=end_entity_id,
        root_claim_id=root_claim_id,
        path_length=1,
        confidence=0.61,
        metadata_payload={
            "terminal_relation_type": "ASSOCIATED_WITH",
            "supporting_claim_ids": [str(root_claim_id), str(final_claim_id)],
        },
    )
    path_detail = KernelReasoningPathDetail(
        path=path,
        steps=(
            _build_path_step(
                path_id=path_id,
                source_claim_id=root_claim_id,
                target_claim_id=final_claim_id,
                claim_relation_id=claim_relation_id,
            ),
        ),
        claims=(root_claim, final_claim),
        claim_relations=(),
        canonical_relations=(),
        participants=(),
        evidence=(
            _build_claim_evidence(claim_id=root_claim_id),
            _build_claim_evidence(claim_id=final_claim_id),
        ),
    )

    all_discovery_claims = [transfer_claim, *contradiction_claims]
    participant_map = {
        str(claim.id): [
            _build_claim_participant(
                claim_id=claim.id,
                research_space_id=research_space_id,
                role="SUBJECT",
                entity_id=neighbor_entity_id,
                position=0,
            ),
            _build_claim_participant(
                claim_id=claim.id,
                research_space_id=research_space_id,
                role="OBJECT",
                entity_id=end_entity_id,
                position=1,
            ),
        ]
        for claim in all_discovery_claims
    }

    claim_service = StubRelationClaimService(
        discovery_seed_claims=all_discovery_claims,
        existing_hypothesis_claims=[],
    )
    service = HypothesisGenerationService(
        dependencies=HypothesisGenerationServiceDependencies(
            graph_connection_agent=StubGraphConnectionAgent({}),
            relation_claim_service=claim_service,
            claim_participant_service=StubClaimParticipantService(
                participants_by_claim=participant_map,
                claim_ids_by_entity={
                    str(neighbor_entity_id): [
                        str(claim.id) for claim in all_discovery_claims
                    ],
                },
            ),
            claim_evidence_service=StubClaimEvidenceService(
                evidence_by_claim={
                    str(transfer_claim_id): [
                        _build_claim_evidence(claim_id=transfer_claim_id),
                    ],
                },
            ),
            entity_repository=StubEntityRepository(
                entities={
                    str(start_entity_id): start_entity,
                    str(neighbor_entity_id): neighbor_entity,
                    str(end_entity_id): end_entity,
                },
                fallback_entities=[start_entity],
            ),
            relation_repository=StubRelationRepository(
                connected_relations=[
                    _build_relation(
                        relation_id=uuid4(),
                        research_space_id=research_space_id,
                        source_id=start_entity_id,
                        relation_type="PART_OF",
                        target_id=neighbor_entity_id,
                    ),
                ],
                canonical_by_source={},
            ),
            dictionary_service=StubDictionaryService(allow_all=True),
            reasoning_path_service=StubReasoningPathService(
                paths_by_start_entity={str(start_entity_id): [path]},
                details_by_id={str(path_id): path_detail},
            ),
        ),
    )

    result = await service.generate_hypotheses(
        research_space_id=str(research_space_id),
        seed_entity_ids=[str(start_entity_id)],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
    )

    assert result.created_count == 1
    metadata = claim_service.created_payloads[0]["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["origin"] == "reasoning_path"
