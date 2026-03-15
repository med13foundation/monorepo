"""Unit tests for the standalone harness service."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Final
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi.testclient import TestClient

from services.graph_harness_api.app import create_app
from services.graph_harness_api.approval_store import HarnessApprovalStore
from services.graph_harness_api.artifact_store import HarnessArtifactStore
from services.graph_harness_api.chat_sessions import HarnessChatSessionStore
from services.graph_harness_api.chat_workflow import execute_graph_chat_message
from services.graph_harness_api.claim_curation_runtime import (
    load_curatable_proposals,
    resume_claim_curation_run,
)
from services.graph_harness_api.claim_curation_workflow import (
    execute_claim_curation_run_for_proposals,
)
from services.graph_harness_api.continuous_learning_runtime import (
    execute_continuous_learning_run,
    normalize_seed_entity_ids,
)
from services.graph_harness_api.dependencies import (
    get_approval_store,
    get_artifact_store,
    get_chat_session_store,
    get_graph_api_gateway,
    get_graph_chat_runner,
    get_graph_connection_runner,
    get_graph_search_runner,
    get_graph_snapshot_store,
    get_harness_execution_services,
    get_proposal_store,
    get_pubmed_discovery_service,
    get_research_state_store,
    get_run_registry,
    get_schedule_store,
)
from services.graph_harness_api.graph_chat_runtime import (
    GraphChatEvidenceItem,
    GraphChatResult,
    GraphChatVerification,
    HarnessGraphChatRequest,
)
from services.graph_harness_api.graph_connection_runtime import (
    HarnessGraphConnectionRequest,
    HarnessGraphConnectionResult,
)
from services.graph_harness_api.graph_search_runtime import (
    HarnessGraphSearchRequest,
    HarnessGraphSearchResult,
)
from services.graph_harness_api.graph_snapshot import HarnessGraphSnapshotStore
from services.graph_harness_api.harness_runtime import HarnessExecutionServices
from services.graph_harness_api.mechanism_discovery_runtime import (
    execute_mechanism_discovery_run,
)
from services.graph_harness_api.proposal_store import HarnessProposalStore
from services.graph_harness_api.research_bootstrap_runtime import (
    execute_research_bootstrap_run,
)
from services.graph_harness_api.research_state import HarnessResearchStateStore
from services.graph_harness_api.run_budget import (
    budget_from_json,
    resolve_continuous_learning_run_budget,
)
from services.graph_harness_api.run_registry import HarnessRunRegistry
from services.graph_harness_api.schedule_store import HarnessScheduleStore
from services.graph_harness_api.supervisor_runtime import (
    execute_supervisor_run,
    resume_supervisor_run,
)
from src.application.services.pubmed_discovery_service import RunPubmedSearchRequest
from src.application.services.pubmed_query_builder import PubMedQueryBuilder
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_connection import GraphConnectionContract
from src.domain.agents.contracts.graph_search import (
    GraphSearchContract,
    GraphSearchResultEntry,
)
from src.domain.entities.discovery_preset import DiscoveryProvider
from src.domain.entities.discovery_search_job import (
    DiscoverySearchJob,
    DiscoverySearchStatus,
)
from src.infrastructure.graph_service.client import GraphServiceHealthResponse
from src.type_definitions.graph_service_contracts import (
    ClaimParticipantListResponse,
    ClaimParticipantResponse,
    CreateManualHypothesisRequest,
    HypothesisListResponse,
    HypothesisResponse,
    KernelClaimEvidenceListResponse,
    KernelClaimEvidenceResponse,
    KernelGraphDocumentCounts,
    KernelGraphDocumentEdge,
    KernelGraphDocumentMeta,
    KernelGraphDocumentNode,
    KernelGraphDocumentRequest,
    KernelGraphDocumentResponse,
    KernelGraphViewCountsResponse,
    KernelReasoningPathDetailResponse,
    KernelReasoningPathListResponse,
    KernelReasoningPathResponse,
    KernelReasoningPathStepResponse,
    KernelRelationClaimCreateRequest,
    KernelRelationClaimListResponse,
    KernelRelationClaimResponse,
    KernelRelationConflictListResponse,
    KernelRelationConflictResponse,
    KernelRelationSuggestionConstraintCheckResponse,
    KernelRelationSuggestionListResponse,
    KernelRelationSuggestionRequest,
    KernelRelationSuggestionResponse,
    KernelRelationSuggestionScoreBreakdownResponse,
)
from tests.graph_harness_api_support import (
    FakeEvent,
    FakeEventType,
    FakePayload,
    FakeStepToolResult,
    fake_tool_allowlist,
    fake_tool_result_payload,
)

_TEST_USER_ID: Final[str] = "11111111-1111-1111-1111-111111111111"
_TEST_USER_EMAIL: Final[str] = "graph-harness-test@example.com"
_CURATION_DUPLICATE_SOURCE_ID: Final[str] = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_CURATION_DUPLICATE_TARGET_ID: Final[str] = "33333333-3333-3333-3333-333333333333"
_CURATION_DUPLICATE_CLAIM_ID: Final[UUID] = uuid5(
    NAMESPACE_URL,
    "curation-duplicate-claim",
)
_CURATION_DUPLICATE_RELATION_ID: Final[UUID] = uuid5(
    NAMESPACE_URL,
    "curation-duplicate-relation",
)
_GRAPH_CHAT_EVIDENCE_ENTITY_ID: Final[str] = "88888888-8888-4888-8888-888888888888"
_GRAPH_CHAT_SECOND_EVIDENCE_ENTITY_ID: Final[str] = (
    "77777777-7777-4777-8777-777777777777"
)
_GRAPH_CHAT_SUGGESTION_TARGET_ID: Final[str] = "99999999-9999-4999-9999-999999999999"
_GRAPH_CHAT_SECOND_SUGGESTION_TARGET_ID: Final[str] = (
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
)
_GRAPH_CHAT_THIRD_SUGGESTION_TARGET_ID: Final[str] = (
    "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
)
_GRAPH_CHAT_FOURTH_SUGGESTION_TARGET_ID: Final[str] = (
    "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
)
_GRAPH_CHAT_FIFTH_SUGGESTION_TARGET_ID: Final[str] = (
    "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
)
_GRAPH_CHAT_SIXTH_SUGGESTION_TARGET_ID: Final[str] = (
    "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
)


class _FakeGraphApiGateway:
    def __init__(self) -> None:
        self.closed = False
        self._reasoning_path_seed_by_id: dict[UUID, str] = {}

    def get_health(self) -> GraphServiceHealthResponse:
        return GraphServiceHealthResponse(status="ok", version="test-graph")

    def create_claim(
        self,
        *,
        space_id: str,
        request: KernelRelationClaimCreateRequest,
    ) -> KernelRelationClaimResponse:
        return KernelRelationClaimResponse(
            id=uuid4(),
            research_space_id=UUID(space_id),
            source_document_id=None,
            source_document_ref=request.source_document_ref,
            agent_run_id=request.agent_run_id,
            source_type="GENE",
            relation_type=request.relation_type,
            target_type="GENE",
            source_label="Source",
            target_label="Target",
            confidence=request.confidence,
            validation_state="ALLOWED",
            validation_reason="created_via_claim_api",
            persistability="PERSISTABLE",
            claim_status="OPEN",
            polarity="SUPPORT",
            claim_text=request.claim_text,
            claim_section=None,
            linked_relation_id=None,
            metadata=request.metadata,
            triaged_by=None,
            triaged_at=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    def list_claims(
        self,
        *,
        space_id: UUID | str,
        claim_status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelRelationClaimListResponse:
        del claim_status, offset
        now = datetime.now(UTC)
        return KernelRelationClaimListResponse(
            claims=[
                KernelRelationClaimResponse(
                    id=uuid5(NAMESPACE_URL, f"bootstrap-claim:{space_id}"),
                    research_space_id=UUID(str(space_id)),
                    source_document_id=None,
                    source_document_ref="pmid:1",
                    agent_run_id="bootstrap:test-claim",
                    source_type="PUBMED",
                    relation_type="SUPPORTS",
                    target_type="GENE",
                    source_label="MED13",
                    target_label="Mediator complex",
                    confidence=0.79,
                    validation_state="ALLOWED",
                    validation_reason="test",
                    persistability="PERSISTABLE",
                    claim_status="OPEN",
                    polarity="SUPPORT",
                    claim_text="Synthetic bootstrap claim",
                    claim_section=None,
                    linked_relation_id=uuid5(
                        NAMESPACE_URL,
                        f"bootstrap-relation:{space_id}",
                    ),
                    metadata={},
                    triaged_by=None,
                    triaged_at=None,
                    created_at=now,
                    updated_at=now,
                ),
            ],
            total=1,
            offset=0,
            limit=limit,
        )

    def suggest_relations(
        self,
        *,
        space_id: UUID | str,
        request: KernelRelationSuggestionRequest,
    ) -> KernelRelationSuggestionListResponse:
        del space_id
        suggestions = [
            KernelRelationSuggestionResponse(
                source_entity_id=source_entity_id,
                target_entity_id=UUID(_GRAPH_CHAT_SUGGESTION_TARGET_ID),
                relation_type="SUGGESTS",
                final_score=0.86,
                score_breakdown=KernelRelationSuggestionScoreBreakdownResponse(
                    vector_score=0.84,
                    graph_overlap_score=0.78,
                    relation_prior_score=0.65,
                ),
                constraint_check=KernelRelationSuggestionConstraintCheckResponse(
                    passed=True,
                    source_entity_type="GENE",
                    relation_type="SUGGESTS",
                    target_entity_type="GENE",
                ),
            )
            for source_entity_id in request.source_entity_ids[
                : request.limit_per_source
            ]
        ]
        return KernelRelationSuggestionListResponse(
            suggestions=suggestions,
            total=len(suggestions),
            limit_per_source=request.limit_per_source,
            min_score=request.min_score,
        )

    def list_reasoning_paths(
        self,
        *,
        space_id: UUID | str,
        start_entity_id: UUID | str | None = None,
        end_entity_id: UUID | str | None = None,
        status: str | None = None,
        path_kind: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelReasoningPathListResponse:
        del end_entity_id, offset, status
        assert path_kind in {None, "MECHANISM"}
        assert limit >= 1
        if start_entity_id is None:
            return KernelReasoningPathListResponse(
                paths=[],
                total=0,
                offset=0,
                limit=limit,
            )
        normalized_space_id = UUID(str(space_id))
        normalized_seed_id = str(start_entity_id)
        path_id = uuid5(NAMESPACE_URL, f"reasoning-path:{normalized_seed_id}")
        self._reasoning_path_seed_by_id[path_id] = normalized_seed_id
        end_claim_id = uuid5(NAMESPACE_URL, f"mechanism-end-claim:{normalized_seed_id}")
        return KernelReasoningPathListResponse(
            paths=[
                KernelReasoningPathResponse(
                    id=path_id,
                    research_space_id=normalized_space_id,
                    path_kind="MECHANISM",
                    status="ACTIVE",
                    start_entity_id=UUID(normalized_seed_id),
                    end_entity_id=UUID("44444444-4444-4444-4444-444444444444"),
                    root_claim_id=uuid5(
                        NAMESPACE_URL,
                        f"mechanism-root-claim:{normalized_seed_id}",
                    ),
                    path_length=1,
                    confidence=0.82,
                    path_signature_hash=path_id.hex,
                    generated_by="test_gateway",
                    generated_at=datetime.now(UTC),
                    metadata={
                        "supporting_claim_ids": [
                            str(
                                uuid5(
                                    NAMESPACE_URL,
                                    f"mechanism-root-claim:{normalized_seed_id}",
                                ),
                            ),
                            str(end_claim_id),
                        ],
                        "end_claim_id": str(end_claim_id),
                        "terminal_relation_type": "ACTIVATES",
                    },
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                ),
            ],
            total=1,
            offset=0,
            limit=limit,
        )

    def get_reasoning_path(
        self,
        *,
        space_id: UUID | str,
        path_id: UUID | str,
    ) -> KernelReasoningPathDetailResponse:
        normalized_space_id = UUID(str(space_id))
        normalized_path_id = UUID(str(path_id))
        seed_entity_id = self._reasoning_path_seed_by_id[normalized_path_id]
        root_claim_id = uuid5(NAMESPACE_URL, f"mechanism-root-claim:{seed_entity_id}")
        end_claim_id = uuid5(NAMESPACE_URL, f"mechanism-end-claim:{seed_entity_id}")
        now = datetime.now(UTC)
        return KernelReasoningPathDetailResponse(
            path=KernelReasoningPathResponse(
                id=normalized_path_id,
                research_space_id=normalized_space_id,
                path_kind="MECHANISM",
                status="ACTIVE",
                start_entity_id=UUID(seed_entity_id),
                end_entity_id=UUID("44444444-4444-4444-4444-444444444444"),
                root_claim_id=root_claim_id,
                path_length=1,
                confidence=0.82,
                path_signature_hash=normalized_path_id.hex,
                generated_by="test_gateway",
                generated_at=now,
                metadata={
                    "supporting_claim_ids": [str(root_claim_id), str(end_claim_id)],
                    "end_claim_id": str(end_claim_id),
                    "terminal_relation_type": "ACTIVATES",
                },
                created_at=now,
                updated_at=now,
            ),
            steps=[
                KernelReasoningPathStepResponse(
                    id=uuid5(NAMESPACE_URL, f"mechanism-step:{seed_entity_id}"),
                    path_id=normalized_path_id,
                    step_index=0,
                    source_claim_id=root_claim_id,
                    target_claim_id=end_claim_id,
                    claim_relation_id=uuid5(
                        NAMESPACE_URL,
                        f"mechanism-claim-relation:{seed_entity_id}",
                    ),
                    canonical_relation_id=None,
                    metadata={"relation_type": "ACTIVATES", "confidence": 0.82},
                    created_at=now,
                ),
            ],
            canonical_relations=[],
            claims=[
                KernelRelationClaimResponse(
                    id=root_claim_id,
                    research_space_id=normalized_space_id,
                    source_document_id=None,
                    source_document_ref=None,
                    agent_run_id="mechanism:test-root",
                    source_type="GENE",
                    relation_type="UPSTREAM_OF",
                    target_type="PATHWAY",
                    source_label=f"Seed {seed_entity_id[-4:]}",
                    target_label="Bridge pathway",
                    confidence=0.84,
                    validation_state="ALLOWED",
                    validation_reason="test",
                    persistability="PERSISTABLE",
                    claim_status="OPEN",
                    polarity="SUPPORT",
                    claim_text="Synthetic root claim",
                    claim_section=None,
                    linked_relation_id=None,
                    metadata={},
                    triaged_by=None,
                    triaged_at=None,
                    created_at=now,
                    updated_at=now,
                ),
                KernelRelationClaimResponse(
                    id=end_claim_id,
                    research_space_id=normalized_space_id,
                    source_document_id=None,
                    source_document_ref=f"pmid:{seed_entity_id[-4:]}",
                    agent_run_id="mechanism:test-terminal",
                    source_type="PATHWAY",
                    relation_type="ACTIVATES",
                    target_type="PROCESS",
                    source_label="Bridge pathway",
                    target_label="Shared mechanism target",
                    confidence=0.82,
                    validation_state="ALLOWED",
                    validation_reason="test",
                    persistability="PERSISTABLE",
                    claim_status="OPEN",
                    polarity="SUPPORT",
                    claim_text="Synthetic terminal claim",
                    claim_section=None,
                    linked_relation_id=None,
                    metadata={},
                    triaged_by=None,
                    triaged_at=None,
                    created_at=now,
                    updated_at=now,
                ),
            ],
            claim_relations=[],
            participants=[],
            evidence=[
                KernelClaimEvidenceResponse(
                    id=uuid5(NAMESPACE_URL, f"mechanism-evidence:{seed_entity_id}"),
                    claim_id=end_claim_id,
                    source_document_id=None,
                    source_document_ref=f"pmid:{seed_entity_id[-4:]}",
                    agent_run_id="mechanism:test-evidence",
                    sentence=(
                        "Synthetic evidence supporting a converging mechanism path."
                    ),
                    sentence_source="abstract",
                    sentence_confidence="high",
                    sentence_rationale="Synthetic reasoning-path evidence",
                    figure_reference=None,
                    table_reference=None,
                    confidence=0.81,
                    metadata={},
                    paper_links=[],
                    created_at=now,
                ),
            ],
            counts=KernelGraphViewCountsResponse(
                canonical_relations=0,
                claims=2,
                claim_relations=0,
                participants=0,
                evidence=1,
            ),
        )

    def create_manual_hypothesis(
        self,
        *,
        space_id: UUID | str,
        request: CreateManualHypothesisRequest,
    ) -> HypothesisResponse:
        return HypothesisResponse(
            claim_id=uuid4(),
            polarity="HYPOTHESIS",
            claim_status="OPEN",
            validation_state="ALLOWED",
            persistability="PERSISTABLE",
            confidence=0.83,
            source_label=None,
            relation_type="HYPOTHESIS",
            target_label=None,
            claim_text=request.statement,
            linked_relation_id=None,
            origin="manual",
            seed_entity_ids=list(request.seed_entity_ids),
            supporting_provenance_ids=[],
            reasoning_path_id=None,
            supporting_claim_ids=[],
            direct_supporting_claim_ids=[],
            transferred_supporting_claim_ids=[],
            transferred_from_entities=[],
            transfer_basis=[],
            contradiction_claim_ids=[],
            explanation=request.rationale,
            path_confidence=None,
            path_length=None,
            created_at=datetime.now(UTC),
            metadata={"source_type": request.source_type, "space_id": str(space_id)},
        )

    def list_hypotheses(
        self,
        *,
        space_id: UUID | str,
        offset: int = 0,
        limit: int = 50,
    ) -> HypothesisListResponse:
        del offset
        return HypothesisListResponse(
            hypotheses=[
                HypothesisResponse(
                    claim_id=uuid5(NAMESPACE_URL, f"bootstrap-hypothesis:{space_id}"),
                    polarity="SUPPORT",
                    claim_status="OPEN",
                    validation_state="ALLOWED",
                    persistability="PERSISTABLE",
                    confidence=0.68,
                    source_label="MED13",
                    relation_type="REGULATES",
                    target_label="Transcriptional program",
                    claim_text="MED13 may regulate a transcriptional program.",
                    linked_relation_id=None,
                    origin="test",
                    seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
                    supporting_provenance_ids=[],
                    reasoning_path_id=None,
                    supporting_claim_ids=[],
                    direct_supporting_claim_ids=[],
                    transferred_supporting_claim_ids=[],
                    transferred_from_entities=[],
                    transfer_basis=[],
                    contradiction_claim_ids=[],
                    explanation="Synthetic bootstrap hypothesis.",
                    path_confidence=None,
                    path_length=None,
                    created_at=datetime.now(UTC),
                    metadata={},
                ),
            ],
            total=1,
            offset=0,
            limit=limit,
        )

    def get_graph_document(
        self,
        *,
        space_id: UUID | str,
        request: KernelGraphDocumentRequest,
    ) -> KernelGraphDocumentResponse:
        now = datetime.now(UTC)
        seed_entity_id = (
            str(request.seed_entity_ids[0])
            if request.seed_entity_ids
            else "11111111-1111-1111-1111-111111111111"
        )
        relation_id = str(uuid5(NAMESPACE_URL, f"bootstrap-relation:{space_id}"))
        return KernelGraphDocumentResponse(
            nodes=[
                KernelGraphDocumentNode(
                    id="ENTITY:seed",
                    resource_id=seed_entity_id,
                    kind="ENTITY",
                    type_label="GENE",
                    label="MED13",
                    confidence=None,
                    curation_status=None,
                    claim_status=None,
                    polarity=None,
                    canonical_relation_id=None,
                    metadata={},
                    created_at=now,
                    updated_at=now,
                ),
                KernelGraphDocumentNode(
                    id="CLAIM:bootstrap",
                    resource_id=str(
                        uuid5(NAMESPACE_URL, f"bootstrap-claim:{space_id}"),
                    ),
                    kind="CLAIM",
                    type_label="RELATION_CLAIM",
                    label="Synthetic bootstrap claim",
                    confidence=0.79,
                    curation_status=None,
                    claim_status="OPEN",
                    polarity="SUPPORT",
                    canonical_relation_id=None,
                    metadata={},
                    created_at=now,
                    updated_at=now,
                ),
            ],
            edges=[
                KernelGraphDocumentEdge(
                    id="CANONICAL_RELATION:bootstrap",
                    resource_id=relation_id,
                    kind="CANONICAL_RELATION",
                    source_id="ENTITY:seed",
                    target_id="CLAIM:bootstrap",
                    type_label="SUPPORTS",
                    label="supports",
                    confidence=0.79,
                    curation_status="accepted",
                    claim_id=None,
                    canonical_relation_id=UUID(relation_id),
                    evidence_id=None,
                    metadata={},
                    created_at=now,
                    updated_at=now,
                ),
            ],
            meta=KernelGraphDocumentMeta(
                mode=request.mode,
                seed_entity_ids=list(request.seed_entity_ids),
                requested_depth=request.depth,
                requested_top_k=request.top_k,
                pre_cap_entity_node_count=1,
                pre_cap_canonical_edge_count=1,
                truncated_entity_nodes=False,
                truncated_canonical_edges=False,
                included_claims=request.include_claims,
                included_evidence=request.include_evidence,
                max_claims=request.max_claims,
                evidence_limit_per_claim=request.evidence_limit_per_claim,
                counts=KernelGraphDocumentCounts(
                    entity_nodes=1,
                    claim_nodes=1,
                    evidence_nodes=0,
                    canonical_edges=1,
                    claim_participant_edges=0,
                    claim_evidence_edges=0,
                ),
            ),
        )

    def list_claims_by_entity(
        self,
        *,
        space_id: UUID | str,
        entity_id: UUID | str,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelRelationClaimListResponse:
        del offset
        normalized_space_id = UUID(str(space_id))
        normalized_entity_id = str(entity_id)
        if normalized_entity_id != _CURATION_DUPLICATE_SOURCE_ID:
            return KernelRelationClaimListResponse(
                claims=[],
                total=0,
                offset=0,
                limit=limit,
            )
        now = datetime.now(UTC)
        return KernelRelationClaimListResponse(
            claims=[
                KernelRelationClaimResponse(
                    id=_CURATION_DUPLICATE_CLAIM_ID,
                    research_space_id=normalized_space_id,
                    source_document_id=None,
                    source_document_ref="pmid:duplicate",
                    agent_run_id="curation:test-duplicate",
                    source_type="GENE",
                    relation_type="SUGGESTS",
                    target_type="GENE",
                    source_label="Duplicate source",
                    target_label="Synthetic duplicate target",
                    confidence=0.91,
                    validation_state="ALLOWED",
                    validation_reason="test_duplicate",
                    persistability="PERSISTABLE",
                    claim_status="OPEN",
                    polarity="SUPPORT",
                    claim_text="Synthetic duplicate graph claim",
                    claim_section=None,
                    linked_relation_id=_CURATION_DUPLICATE_RELATION_ID,
                    metadata={},
                    triaged_by=None,
                    triaged_at=None,
                    created_at=now,
                    updated_at=now,
                ),
            ],
            total=1,
            offset=0,
            limit=limit,
        )

    def list_claim_participants(
        self,
        *,
        space_id: UUID | str,
        claim_id: UUID | str,
    ) -> ClaimParticipantListResponse:
        normalized_space_id = UUID(str(space_id))
        normalized_claim_id = UUID(str(claim_id))
        if normalized_claim_id != _CURATION_DUPLICATE_CLAIM_ID:
            return ClaimParticipantListResponse(
                claim_id=normalized_claim_id,
                participants=[],
                total=0,
            )
        now = datetime.now(UTC)
        return ClaimParticipantListResponse(
            claim_id=normalized_claim_id,
            participants=[
                ClaimParticipantResponse(
                    id=uuid5(NAMESPACE_URL, "curation-duplicate-subject"),
                    claim_id=normalized_claim_id,
                    research_space_id=normalized_space_id,
                    label="Duplicate source",
                    entity_id=UUID(_CURATION_DUPLICATE_SOURCE_ID),
                    role="SUBJECT",
                    position=0,
                    qualifiers={},
                    created_at=now,
                ),
                ClaimParticipantResponse(
                    id=uuid5(NAMESPACE_URL, "curation-duplicate-object"),
                    claim_id=normalized_claim_id,
                    research_space_id=normalized_space_id,
                    label="Synthetic duplicate target",
                    entity_id=UUID(_CURATION_DUPLICATE_TARGET_ID),
                    role="OBJECT",
                    position=1,
                    qualifiers={},
                    created_at=now,
                ),
            ],
            total=2,
        )

    def list_claim_evidence(
        self,
        *,
        space_id: UUID | str,
        claim_id: UUID | str,
    ) -> KernelClaimEvidenceListResponse:
        del space_id
        normalized_claim_id = UUID(str(claim_id))
        if normalized_claim_id != _CURATION_DUPLICATE_CLAIM_ID:
            return KernelClaimEvidenceListResponse(
                claim_id=normalized_claim_id,
                evidence=[],
                total=0,
            )
        return KernelClaimEvidenceListResponse(
            claim_id=normalized_claim_id,
            evidence=[
                KernelClaimEvidenceResponse(
                    id=uuid5(NAMESPACE_URL, "curation-duplicate-evidence"),
                    claim_id=normalized_claim_id,
                    source_document_id=None,
                    source_document_ref="pmid:duplicate",
                    agent_run_id="curation:test-duplicate",
                    sentence="Synthetic duplicate claim evidence.",
                    sentence_source="abstract",
                    sentence_confidence="high",
                    sentence_rationale="Duplicate evidence",
                    figure_reference=None,
                    table_reference=None,
                    confidence=0.89,
                    metadata={},
                    paper_links=[],
                    created_at=datetime.now(UTC),
                ),
            ],
            total=1,
        )

    def list_relation_conflicts(
        self,
        *,
        space_id: UUID | str,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelRelationConflictListResponse:
        del space_id, offset
        return KernelRelationConflictListResponse(
            conflicts=[
                KernelRelationConflictResponse(
                    relation_id=_CURATION_DUPLICATE_RELATION_ID,
                    support_count=1,
                    refute_count=1,
                    support_claim_ids=[_CURATION_DUPLICATE_CLAIM_ID],
                    refute_claim_ids=[uuid5(NAMESPACE_URL, "curation-conflict-refute")],
                ),
            ],
            total=1,
            offset=0,
            limit=limit,
        )

    def close(self) -> None:
        self.closed = True


class _FakeNoSuggestionGraphApiGateway(_FakeGraphApiGateway):
    def suggest_relations(
        self,
        *,
        space_id: UUID | str,
        request: KernelRelationSuggestionRequest,
    ) -> KernelRelationSuggestionListResponse:
        del space_id
        return KernelRelationSuggestionListResponse(
            suggestions=[],
            total=0,
            limit_per_source=request.limit_per_source,
            min_score=request.min_score,
        )


class _FakeSingleDerivationGraphApiGateway(_FakeGraphApiGateway):
    suggest_relations_call_count = 0

    def suggest_relations(
        self,
        *,
        space_id: UUID | str,
        request: KernelRelationSuggestionRequest,
    ) -> KernelRelationSuggestionListResponse:
        type(self).suggest_relations_call_count += 1
        if type(self).suggest_relations_call_count > 1:
            raise AssertionError(
                "Chat graph-write proposals should reuse stored candidates instead "
                "of re-deriving relation suggestions.",
            )
        return super().suggest_relations(space_id=space_id, request=request)


class _FakeRankedSuggestionGraphApiGateway(_FakeGraphApiGateway):
    def suggest_relations(
        self,
        *,
        space_id: UUID | str,
        request: KernelRelationSuggestionRequest,
    ) -> KernelRelationSuggestionListResponse:
        del space_id
        source_ids = [
            str(source_entity_id) for source_entity_id in request.source_entity_ids
        ]
        suggestion_specs = {
            _GRAPH_CHAT_EVIDENCE_ENTITY_ID: [
                (_GRAPH_CHAT_SUGGESTION_TARGET_ID, 0.96, 0.95, 0.93, 0.85),
                (_GRAPH_CHAT_THIRD_SUGGESTION_TARGET_ID, 0.89, 0.87, 0.84, 0.80),
                (_GRAPH_CHAT_FIFTH_SUGGESTION_TARGET_ID, 0.80, 0.79, 0.77, 0.74),
            ],
            _GRAPH_CHAT_SECOND_EVIDENCE_ENTITY_ID: [
                (_GRAPH_CHAT_SECOND_SUGGESTION_TARGET_ID, 0.94, 0.92, 0.90, 0.82),
                (_GRAPH_CHAT_FOURTH_SUGGESTION_TARGET_ID, 0.84, 0.83, 0.81, 0.77),
                (_GRAPH_CHAT_SIXTH_SUGGESTION_TARGET_ID, 0.78, 0.77, 0.75, 0.72),
            ],
        }
        suggestions: list[KernelRelationSuggestionResponse] = []
        for source_entity_id in source_ids:
            for (
                target_entity_id,
                final_score,
                vector_score,
                overlap_score,
                prior_score,
            ) in suggestion_specs.get(source_entity_id, [])[: request.limit_per_source]:
                suggestions.append(
                    KernelRelationSuggestionResponse(
                        source_entity_id=UUID(source_entity_id),
                        target_entity_id=UUID(target_entity_id),
                        relation_type="SUGGESTS",
                        final_score=final_score,
                        score_breakdown=KernelRelationSuggestionScoreBreakdownResponse(
                            vector_score=vector_score,
                            graph_overlap_score=overlap_score,
                            relation_prior_score=prior_score,
                        ),
                        constraint_check=KernelRelationSuggestionConstraintCheckResponse(
                            passed=True,
                            source_entity_type="GENE",
                            relation_type="SUGGESTS",
                            target_entity_type="GENE",
                        ),
                    ),
                )
        return KernelRelationSuggestionListResponse(
            suggestions=suggestions,
            total=len(suggestions),
            limit_per_source=request.limit_per_source,
            min_score=request.min_score,
        )


class _FakeGraphSearchRunner:
    async def run(
        self,
        request: HarnessGraphSearchRequest,
    ) -> HarnessGraphSearchResult:
        contract = GraphSearchContract(
            decision="generated",
            confidence_score=0.81,
            rationale="Synthetic graph-search result for harness tests.",
            evidence=[
                EvidenceItem(
                    source_type="db",
                    locator=f"space:{request.research_space_id}",
                    excerpt="Synthetic evidence",
                    relevance=0.8,
                ),
            ],
            research_space_id=request.research_space_id,
            original_query=request.question,
            interpreted_intent=request.question,
            query_plan_summary="Synthetic harness graph-search plan.",
            total_results=0,
            results=[],
            executed_path="agent",
            warnings=[],
            agent_run_id="graph_search:test-run",
        )
        return HarnessGraphSearchResult(
            contract=contract,
            agent_run_id=contract.agent_run_id,
            active_skill_names=("graph_harness.graph_grounding",),
        )


class _FakeGraphConnectionRunner:
    async def run(
        self,
        request: HarnessGraphConnectionRequest,
    ) -> HarnessGraphConnectionResult:
        contract = GraphConnectionContract(
            decision="generated",
            confidence_score=0.73,
            rationale="Synthetic graph-connection result for harness tests.",
            evidence=[
                EvidenceItem(
                    source_type="db",
                    locator=f"seed:{request.seed_entity_id}",
                    excerpt="Synthetic connection evidence",
                    relevance=0.7,
                ),
            ],
            source_type=request.source_type or "pubmed",
            research_space_id=request.research_space_id,
            seed_entity_id=request.seed_entity_id,
            proposed_relations=[
                {
                    "source_id": request.seed_entity_id,
                    "relation_type": "SUGGESTS",
                    "target_id": "33333333-3333-3333-3333-333333333333",
                    "confidence": 0.73,
                    "evidence_summary": "Synthetic hypothesis evidence",
                    "supporting_document_count": 2,
                    "reasoning": "Synthetic bridge from graph-connection runner.",
                },
            ],
            rejected_candidates=[],
            shadow_mode=request.shadow_mode,
            agent_run_id="graph_connection:test-run",
        )
        return HarnessGraphConnectionResult(
            contract=contract,
            agent_run_id=contract.agent_run_id,
            active_skill_names=(
                "graph_harness.graph_grounding",
                "graph_harness.relation_discovery",
            ),
        )


class _FakeGraphChatRunner:
    async def run(
        self,
        request: HarnessGraphChatRequest,
    ) -> GraphChatResult:
        result = GraphChatResult(
            answer_text=(
                "Grounded graph answer:\n"
                "MED13 (gene): Synthetic grounded answer for harness chat tests."
            ),
            chat_summary="Answered with 1 grounded graph match.",
            evidence_bundle=[
                GraphChatEvidenceItem(
                    entity_id=_GRAPH_CHAT_EVIDENCE_ENTITY_ID,
                    entity_type="gene",
                    display_label="MED13",
                    relevance_score=0.92,
                    support_summary="Synthetic grounded answer for harness chat tests.",
                    explanation="Synthetic graph-chat explanation.",
                ),
            ],
            warnings=[],
            verification=GraphChatVerification(
                status="verified",
                reason="Synthetic grounded answer cleared verification.",
                grounded_match_count=1,
                top_relevance_score=0.92,
                warning_count=0,
                allows_graph_write=True,
            ),
            search=GraphSearchContract(
                decision="generated",
                confidence_score=0.92,
                rationale="Synthetic graph-chat search result for harness tests.",
                evidence=[
                    EvidenceItem(
                        source_type="db",
                        locator="entity:entity-1",
                        excerpt="Synthetic graph-chat evidence",
                        relevance=0.9,
                    ),
                ],
                research_space_id=request.research_space_id,
                original_query=request.question,
                interpreted_intent=request.question,
                query_plan_summary="Synthetic graph-chat plan.",
                total_results=1,
                results=[
                    GraphSearchResultEntry(
                        entity_id=_GRAPH_CHAT_EVIDENCE_ENTITY_ID,
                        entity_type="gene",
                        display_label="MED13",
                        relevance_score=0.92,
                        matching_observation_ids=["obs-1"],
                        matching_relation_ids=["rel-1"],
                        evidence_chain=[],
                        explanation="Synthetic graph-chat explanation.",
                        support_summary="Synthetic grounded answer for harness chat tests.",
                    ),
                ],
                executed_path="agent",
                warnings=[],
                agent_run_id="graph_chat:test-search",
            ),
        )
        result._active_skill_names = (
            "graph_harness.graph_grounding",
            "graph_harness.graph_write_review",
        )
        return result


class _FakeNeedsReviewGraphChatRunner:
    async def run(
        self,
        request: HarnessGraphChatRequest,
    ) -> GraphChatResult:
        del request
        result = GraphChatResult(
            answer_text="Preliminary graph answer:\nMED13: synthetic low-confidence result.",
            chat_summary="Answered with 1 grounded graph match. Verification: needs_review.",
            evidence_bundle=[
                GraphChatEvidenceItem(
                    entity_id=_GRAPH_CHAT_EVIDENCE_ENTITY_ID,
                    entity_type="gene",
                    display_label="MED13",
                    relevance_score=0.71,
                    support_summary="Synthetic low-confidence support summary.",
                    explanation="Synthetic low-confidence explanation.",
                ),
            ],
            warnings=["Synthetic verification warning."],
            verification=GraphChatVerification(
                status="needs_review",
                reason="Synthetic verification warning requires review.",
                grounded_match_count=1,
                top_relevance_score=0.71,
                warning_count=1,
                allows_graph_write=False,
            ),
            search=GraphSearchContract(
                decision="generated",
                confidence_score=0.71,
                rationale="Synthetic low-confidence graph-chat result.",
                evidence=[
                    EvidenceItem(
                        source_type="db",
                        locator="entity:entity-1",
                        excerpt="Synthetic low-confidence evidence",
                        relevance=0.71,
                    ),
                ],
                research_space_id="needs-review-space",
                original_query="needs review",
                interpreted_intent="needs review",
                query_plan_summary="Synthetic low-confidence graph-chat plan.",
                total_results=1,
                results=[
                    GraphSearchResultEntry(
                        entity_id=_GRAPH_CHAT_EVIDENCE_ENTITY_ID,
                        entity_type="gene",
                        display_label="MED13",
                        relevance_score=0.71,
                        matching_observation_ids=["obs-1"],
                        matching_relation_ids=["rel-1"],
                        evidence_chain=[],
                        explanation="Synthetic low-confidence explanation.",
                        support_summary="Synthetic low-confidence support summary.",
                    ),
                ],
                executed_path="agent",
                warnings=["Synthetic verification warning."],
                agent_run_id="graph_chat:test-search-needs-review",
            ),
        )
        result._active_skill_names = (
            "graph_harness.graph_grounding",
            "graph_harness.graph_write_review",
            "graph_harness.literature_refresh",
        )
        return result


class _FakeMultiEvidenceGraphChatRunner:
    async def run(
        self,
        request: HarnessGraphChatRequest,
    ) -> GraphChatResult:
        result = GraphChatResult(
            answer_text=(
                "Grounded graph answer:\n"
                "MED13 (gene): Synthetic grounded answer for harness chat tests.\n"
                "CDK8 (gene): Synthetic companion evidence for ranking tests."
            ),
            chat_summary="Answered with 2 grounded graph matches.",
            evidence_bundle=[
                GraphChatEvidenceItem(
                    entity_id=_GRAPH_CHAT_EVIDENCE_ENTITY_ID,
                    entity_type="gene",
                    display_label="MED13",
                    relevance_score=0.92,
                    support_summary="Synthetic grounded answer for harness chat tests.",
                    explanation="Synthetic graph-chat explanation.",
                ),
                GraphChatEvidenceItem(
                    entity_id=_GRAPH_CHAT_SECOND_EVIDENCE_ENTITY_ID,
                    entity_type="gene",
                    display_label="CDK8",
                    relevance_score=0.88,
                    support_summary="Synthetic companion evidence for ranking tests.",
                    explanation="Synthetic ranking companion explanation.",
                ),
            ],
            warnings=[],
            verification=GraphChatVerification(
                status="verified",
                reason="Synthetic grounded answer cleared verification.",
                grounded_match_count=2,
                top_relevance_score=0.92,
                warning_count=0,
                allows_graph_write=True,
            ),
            search=GraphSearchContract(
                decision="generated",
                confidence_score=0.91,
                rationale="Synthetic graph-chat search result for ranking tests.",
                evidence=[
                    EvidenceItem(
                        source_type="db",
                        locator="entity:entity-1",
                        excerpt="Synthetic graph-chat evidence",
                        relevance=0.9,
                    ),
                ],
                research_space_id=request.research_space_id,
                original_query=request.question,
                interpreted_intent=request.question,
                query_plan_summary="Synthetic graph-chat plan.",
                total_results=2,
                results=[
                    GraphSearchResultEntry(
                        entity_id=_GRAPH_CHAT_EVIDENCE_ENTITY_ID,
                        entity_type="gene",
                        display_label="MED13",
                        relevance_score=0.92,
                        matching_observation_ids=["obs-1"],
                        matching_relation_ids=["rel-1"],
                        evidence_chain=[],
                        explanation="Synthetic graph-chat explanation.",
                        support_summary="Synthetic grounded answer for harness chat tests.",
                    ),
                    GraphSearchResultEntry(
                        entity_id=_GRAPH_CHAT_SECOND_EVIDENCE_ENTITY_ID,
                        entity_type="gene",
                        display_label="CDK8",
                        relevance_score=0.88,
                        matching_observation_ids=["obs-2"],
                        matching_relation_ids=["rel-2"],
                        evidence_chain=[],
                        explanation="Synthetic ranking companion explanation.",
                        support_summary="Synthetic companion evidence for ranking tests.",
                    ),
                ],
                executed_path="agent",
                warnings=[],
                agent_run_id="graph_chat:test-search-multi",
            ),
        )
        result._active_skill_names = (
            "graph_harness.graph_grounding",
            "graph_harness.graph_write_review",
            "graph_harness.relation_discovery",
        )
        return result


class _FakePubMedDiscoveryService:
    def __init__(self) -> None:
        self._query_builder = PubMedQueryBuilder()

    async def run_pubmed_search(
        self,
        owner_id: UUID,
        request: RunPubmedSearchRequest,
    ) -> DiscoverySearchJob:
        query_preview = self._query_builder.build_query(request.parameters)
        now = datetime.now(UTC)
        return DiscoverySearchJob(
            id=uuid5(NAMESPACE_URL, f"pubmed-search:{query_preview}"),
            owner_id=owner_id,
            session_id=request.session_id,
            provider=DiscoveryProvider.PUBMED,
            status=DiscoverySearchStatus.COMPLETED,
            query_preview=query_preview,
            parameters=request.parameters,
            total_results=5,
            result_metadata={
                "article_ids": [f"pmid-{index}" for index in range(1, 6)],
                "preview_records": [
                    {
                        "pmid": f"pmid-{index}",
                        "title": f"Synthetic PubMed result {index}",
                        "query": query_preview,
                    }
                    for index in range(1, 6)
                ],
            },
            created_at=now,
            updated_at=now,
            completed_at=now,
        )


class _FakeWorkerRuntime:
    def __init__(
        self,
        *,
        graph_api_gateway_factory: type[_FakeGraphApiGateway] = _FakeGraphApiGateway,
    ) -> None:
        self._leases: dict[tuple[str, str], str] = {}
        self._events: dict[tuple[str, str], list[FakeEvent]] = {}
        self._graph_api_gateway = graph_api_gateway_factory()

    def acquire_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        _ = ttl_seconds
        key = (tenant_id, run_id)
        if key in self._leases:
            return False
        self._leases[key] = worker_id
        return True

    def release_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
    ) -> bool:
        key = (tenant_id, run_id)
        if self._leases.get(key) != worker_id:
            return False
        del self._leases[key]
        return True

    def explain_tool_allowlist(
        self,
        *,
        tenant_id: str,
        run_id: str,
        visible_tool_names: set[str] | None = None,
    ) -> dict[str, object]:
        _ = tenant_id, run_id
        return fake_tool_allowlist(visible_tool_names=visible_tool_names)

    def get_events(
        self,
        *,
        run_id: str,
        tenant_id: str,
    ) -> tuple[FakeEvent, ...]:
        return tuple(self._events.get((tenant_id, run_id), ()))

    def _tool_result_payload(  # noqa: PLR0912
        self,
        *,
        tool_name: str,
        arguments: object,
    ) -> dict[str, object]:
        if tool_name == "get_graph_document":
            if not hasattr(arguments, "space_id"):
                return fake_tool_result_payload(
                    tool_name=tool_name,
                    arguments=arguments,
                )
            response = self._graph_api_gateway.get_graph_document(
                space_id=str(arguments.space_id),
                request=KernelGraphDocumentRequest(
                    mode="seeded" if list(arguments.seed_entity_ids) else "starter",
                    seed_entity_ids=[
                        UUID(seed_entity_id)
                        for seed_entity_id in arguments.seed_entity_ids
                    ],
                    depth=arguments.depth,
                    top_k=arguments.top_k,
                    include_claims=True,
                    include_evidence=True,
                    max_claims=max(25, arguments.top_k * 2),
                    evidence_limit_per_claim=3,
                ),
            )
            return response.model_dump(mode="json")
        if tool_name == "capture_graph_snapshot":
            if not hasattr(arguments, "space_id"):
                return fake_tool_result_payload(
                    tool_name=tool_name,
                    arguments=arguments,
                )
            response = self._graph_api_gateway.get_graph_document(
                space_id=str(arguments.space_id),
                request=KernelGraphDocumentRequest(
                    mode="seeded" if list(arguments.seed_entity_ids) else "starter",
                    seed_entity_ids=[
                        UUID(seed_entity_id)
                        for seed_entity_id in arguments.seed_entity_ids
                    ],
                    depth=arguments.depth,
                    top_k=arguments.top_k,
                    include_claims=True,
                    include_evidence=True,
                    max_claims=max(25, arguments.top_k * 2),
                    evidence_limit_per_claim=3,
                ),
            )
            payload = response.model_dump(mode="json")
            payload["snapshot_hash"] = str(
                uuid5(
                    NAMESPACE_URL,
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ),
                ),
            )
            return payload
        if tool_name == "list_graph_claims":
            response = self._graph_api_gateway.list_claims(
                space_id=str(arguments.space_id),
                claim_status=arguments.claim_status,
                limit=arguments.limit,
            )
            return response.model_dump(mode="json")
        if tool_name == "list_graph_hypotheses":
            response = self._graph_api_gateway.list_hypotheses(
                space_id=str(arguments.space_id),
                limit=arguments.limit,
            )
            return response.model_dump(mode="json")
        if tool_name == "suggest_relations":
            response = self._graph_api_gateway.suggest_relations(
                space_id=str(arguments.space_id),
                request=KernelRelationSuggestionRequest(
                    source_entity_ids=[
                        UUID(entity_id) for entity_id in arguments.source_entity_ids
                    ],
                    limit_per_source=arguments.limit_per_source,
                    min_score=arguments.min_score,
                    allowed_relation_types=arguments.allowed_relation_types,
                    target_entity_types=arguments.target_entity_types,
                    exclude_existing_relations=True,
                ),
            )
            return response.model_dump(mode="json")
        if tool_name == "list_reasoning_paths":
            response = self._graph_api_gateway.list_reasoning_paths(
                space_id=str(arguments.space_id),
                start_entity_id=arguments.start_entity_id,
                end_entity_id=arguments.end_entity_id,
                status=arguments.status,
                path_kind=arguments.path_kind,
                offset=arguments.offset,
                limit=arguments.limit,
            )
            return response.model_dump(mode="json")
        if tool_name == "get_reasoning_path":
            response = self._graph_api_gateway.get_reasoning_path(
                space_id=str(arguments.space_id),
                path_id=arguments.path_id,
            )
            return response.model_dump(mode="json")
        if tool_name == "list_claims_by_entity":
            response = self._graph_api_gateway.list_claims_by_entity(
                space_id=str(arguments.space_id),
                entity_id=arguments.entity_id,
                offset=arguments.offset,
                limit=arguments.limit,
            )
            return response.model_dump(mode="json")
        if tool_name == "list_claim_participants":
            response = self._graph_api_gateway.list_claim_participants(
                space_id=str(arguments.space_id),
                claim_id=arguments.claim_id,
            )
            return response.model_dump(mode="json")
        if tool_name == "list_claim_evidence":
            response = self._graph_api_gateway.list_claim_evidence(
                space_id=str(arguments.space_id),
                claim_id=arguments.claim_id,
            )
            return response.model_dump(mode="json")
        if tool_name == "list_relation_conflicts":
            response = self._graph_api_gateway.list_relation_conflicts(
                space_id=str(arguments.space_id),
                offset=arguments.offset,
                limit=arguments.limit,
            )
            return response.model_dump(mode="json")
        if tool_name == "create_graph_claim":
            response = self._graph_api_gateway.create_claim(
                space_id=str(arguments.space_id),
                request=KernelRelationClaimCreateRequest(
                    source_entity_id=UUID(arguments.source_entity_id),
                    target_entity_id=UUID(arguments.target_entity_id),
                    relation_type=arguments.relation_type,
                    confidence=arguments.confidence,
                    claim_text=arguments.claim_text,
                    evidence_summary=arguments.evidence_summary,
                    source_document_ref=arguments.source_document_ref,
                    agent_run_id="graph_harness:test",
                    metadata={},
                ),
            )
            return response.model_dump(mode="json")
        if tool_name == "create_manual_hypothesis":
            response = self._graph_api_gateway.create_manual_hypothesis(
                space_id=str(arguments.space_id),
                request=CreateManualHypothesisRequest(
                    statement=arguments.statement,
                    rationale=arguments.rationale,
                    seed_entity_ids=list(arguments.seed_entity_ids),
                    source_type=arguments.source_type,
                    metadata={},
                ),
            )
            return response.model_dump(mode="json")
        return fake_tool_result_payload(tool_name=tool_name, arguments=arguments)

    def step_tool(
        self,
        *,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        arguments,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> FakeStepToolResult:
        _ = parent_step_key
        events = self._events.setdefault((tenant_id, run_id), [])
        events.append(
            FakeEvent(
                event_id=f"{step_key}:requested:{len(events)}",
                event_type=FakeEventType(value="tool_requested"),
                payload=FakePayload(
                    payload={
                        "tool_name": tool_name,
                        "idempotency_key": step_key,
                    },
                ),
                timestamp=datetime.now(UTC),
            ),
        )
        result_payload = self._tool_result_payload(
            tool_name=tool_name,
            arguments=arguments,
        )
        events.append(
            FakeEvent(
                event_id=f"{step_key}:completed:{len(events)}",
                event_type=FakeEventType(value="tool_completed"),
                payload=FakePayload(
                    payload={
                        "tool_name": tool_name,
                        "outcome": "success",
                        "received_idempotency_key": step_key,
                    },
                ),
                timestamp=datetime.now(UTC),
            ),
        )
        return FakeStepToolResult(
            result_json=json.dumps(
                result_payload,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
        )

    def reconcile_tool(
        self,
        *,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        arguments,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> str:
        _ = run_id, tenant_id, step_key, parent_step_key
        return json.dumps(
            self._tool_result_payload(tool_name=tool_name, arguments=arguments),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )


@contextmanager
def _fake_pubmed_discovery_context(service: _FakePubMedDiscoveryService):
    yield service


async def _execute_test_harness_run(
    run,
    services: HarnessExecutionServices,
):
    payload = run.input_payload
    space_id = UUID(run.space_id)
    if run.harness_id == "research-bootstrap":
        return await execute_research_bootstrap_run(
            space_id=space_id,
            title=run.title,
            objective=(
                payload.get("objective")
                if isinstance(payload.get("objective"), str)
                else None
            ),
            seed_entity_ids=[
                item
                for item in payload.get("seed_entity_ids", [])
                if isinstance(item, str)
            ],
            source_type=str(payload.get("source_type", "pubmed")),
            relation_types=(
                payload.get("relation_types")
                if isinstance(payload.get("relation_types"), list)
                else None
            ),
            max_depth=int(payload.get("max_depth", 2)),
            max_hypotheses=int(payload.get("max_hypotheses", 20)),
            model_id=(
                payload.get("model_id")
                if isinstance(payload.get("model_id"), str)
                else None
            ),
            run_registry=services.run_registry,
            artifact_store=services.artifact_store,
            graph_api_gateway=services.graph_api_gateway_factory(),
            graph_connection_runner=services.graph_connection_runner,
            proposal_store=services.proposal_store,
            research_state_store=services.research_state_store,
            graph_snapshot_store=services.graph_snapshot_store,
            schedule_store=services.schedule_store,
            runtime=services.runtime,
            existing_run=run,
        )
    if run.harness_id == "graph-chat":
        session = services.chat_session_store.get_session(
            space_id=space_id,
            session_id=UUID(str(payload["session_id"])),
        )
        assert session is not None
        with services.pubmed_discovery_service_factory() as pubmed_discovery_service:
            return await execute_graph_chat_message(
                space_id=space_id,
                session=session,
                content=str(payload["question"]),
                model_id=(
                    payload.get("model_id")
                    if isinstance(payload.get("model_id"), str)
                    else None
                ),
                max_depth=int(payload.get("max_depth", 2)),
                top_k=int(payload.get("top_k", 10)),
                include_evidence_chains=bool(
                    payload.get("include_evidence_chains", True),
                ),
                current_user_id=str(payload.get("current_user_id", _TEST_USER_ID)),
                chat_session_store=services.chat_session_store,
                run_registry=services.run_registry,
                artifact_store=services.artifact_store,
                runtime=services.runtime,
                graph_api_gateway=services.graph_api_gateway_factory(),
                graph_chat_runner=services.graph_chat_runner,
                graph_snapshot_store=services.graph_snapshot_store,
                _pubmed_discovery_service=pubmed_discovery_service,
                research_state_store=services.research_state_store,
                existing_run=run,
            )
    if run.harness_id == "continuous-learning":
        return await execute_continuous_learning_run(
            space_id=space_id,
            title=run.title,
            seed_entity_ids=normalize_seed_entity_ids(
                [
                    item
                    for item in payload.get("seed_entity_ids", [])
                    if isinstance(item, str)
                ],
            ),
            source_type=str(payload.get("source_type", "pubmed")),
            relation_types=(
                payload.get("relation_types")
                if isinstance(payload.get("relation_types"), list)
                else None
            ),
            max_depth=int(payload.get("max_depth", 2)),
            max_new_proposals=int(payload.get("max_new_proposals", 20)),
            max_next_questions=int(payload.get("max_next_questions", 5)),
            model_id=(
                payload.get("model_id")
                if isinstance(payload.get("model_id"), str)
                else None
            ),
            schedule_id=(
                payload.get("schedule_id")
                if isinstance(payload.get("schedule_id"), str)
                else None
            ),
            run_budget=resolve_continuous_learning_run_budget(
                budget_from_json(payload.get("run_budget")),
            ),
            run_registry=services.run_registry,
            artifact_store=services.artifact_store,
            graph_api_gateway=services.graph_api_gateway_factory(),
            graph_connection_runner=services.graph_connection_runner,
            proposal_store=services.proposal_store,
            research_state_store=services.research_state_store,
            graph_snapshot_store=services.graph_snapshot_store,
            runtime=services.runtime,
            existing_run=run,
        )
    if run.harness_id == "mechanism-discovery":
        return execute_mechanism_discovery_run(
            space_id=space_id,
            title=run.title,
            seed_entity_ids=tuple(
                item
                for item in payload.get("seed_entity_ids", [])
                if isinstance(item, str)
            ),
            max_candidates=int(payload.get("max_candidates", 10)),
            max_reasoning_paths=int(payload.get("max_reasoning_paths", 50)),
            max_path_depth=int(payload.get("max_path_depth", 4)),
            min_path_confidence=float(payload.get("min_path_confidence", 0.0)),
            run_registry=services.run_registry,
            artifact_store=services.artifact_store,
            graph_api_gateway=services.graph_api_gateway_factory(),
            proposal_store=services.proposal_store,
            runtime=services.runtime,
            existing_run=run,
        )
    if run.harness_id == "claim-curation":
        approvals = services.approval_store.list_approvals(
            space_id=space_id,
            run_id=run.id,
        )
        if approvals:
            updated_run, _ = resume_claim_curation_run(
                space_id=space_id,
                run=run,
                approval_store=services.approval_store,
                proposal_store=services.proposal_store,
                run_registry=services.run_registry,
                artifact_store=services.artifact_store,
                runtime=services.runtime,
                graph_api_gateway=services.graph_api_gateway_factory(),
                resume_reason="test_resume",
                resume_metadata={},
            )
            return updated_run
        proposals = load_curatable_proposals(
            space_id=space_id,
            proposal_ids=tuple(
                item
                for item in payload.get("proposal_ids", [])
                if isinstance(item, str)
            ),
            proposal_store=services.proposal_store,
        )
        return execute_claim_curation_run_for_proposals(
            space_id=space_id,
            proposals=proposals,
            title=run.title,
            run_registry=services.run_registry,
            artifact_store=services.artifact_store,
            proposal_store=services.proposal_store,
            approval_store=services.approval_store,
            graph_api_gateway=services.graph_api_gateway_factory(),
            runtime=services.runtime,
            existing_run=run,
        )
    if run.harness_id == "supervisor":
        workspace = services.artifact_store.get_workspace(
            space_id=space_id,
            run_id=run.id,
        )
        if workspace is not None and isinstance(
            workspace.snapshot.get("curation_run_id"),
            str,
        ):
            updated_run, _ = resume_supervisor_run(
                space_id=space_id,
                run=run,
                approval_store=services.approval_store,
                proposal_store=services.proposal_store,
                run_registry=services.run_registry,
                artifact_store=services.artifact_store,
                runtime=services.runtime,
                graph_api_gateway=services.graph_api_gateway_factory(),
                resume_reason="test_resume",
                resume_metadata={},
            )
            return updated_run
        with services.pubmed_discovery_service_factory() as pubmed_discovery_service:
            return await execute_supervisor_run(
                space_id=space_id,
                title=run.title,
                objective=(
                    payload.get("objective")
                    if isinstance(payload.get("objective"), str)
                    else None
                ),
                seed_entity_ids=[
                    item
                    for item in payload.get("seed_entity_ids", [])
                    if isinstance(item, str)
                ],
                source_type=str(payload.get("source_type", "pubmed")),
                relation_types=(
                    payload.get("relation_types")
                    if isinstance(payload.get("relation_types"), list)
                    else None
                ),
                max_depth=int(payload.get("max_depth", 2)),
                max_hypotheses=int(payload.get("max_hypotheses", 20)),
                model_id=(
                    payload.get("model_id")
                    if isinstance(payload.get("model_id"), str)
                    else None
                ),
                include_chat=bool(payload.get("include_chat", True)),
                include_curation=bool(payload.get("include_curation", True)),
                curation_source=str(payload.get("curation_source", "bootstrap")),
                briefing_question=(
                    payload.get("briefing_question")
                    if isinstance(payload.get("briefing_question"), str)
                    else None
                ),
                chat_max_depth=int(payload.get("chat_max_depth", 2)),
                chat_top_k=int(payload.get("chat_top_k", 5)),
                chat_include_evidence_chains=bool(
                    payload.get("chat_include_evidence_chains", False),
                ),
                curation_proposal_limit=int(payload.get("curation_proposal_limit", 5)),
                current_user_id=str(payload.get("current_user_id", _TEST_USER_ID)),
                run_registry=services.run_registry,
                artifact_store=services.artifact_store,
                chat_session_store=services.chat_session_store,
                proposal_store=services.proposal_store,
                approval_store=services.approval_store,
                research_state_store=services.research_state_store,
                graph_snapshot_store=services.graph_snapshot_store,
                schedule_store=services.schedule_store,
                graph_connection_runner=services.graph_connection_runner,
                graph_chat_runner=services.graph_chat_runner,
                pubmed_discovery_service=pubmed_discovery_service,
                runtime=services.runtime,
                parent_graph_api_gateway=services.graph_api_gateway_factory(),
                bootstrap_graph_api_gateway=services.graph_api_gateway_factory(),
                chat_graph_api_gateway=services.graph_api_gateway_factory(),
                curation_graph_api_gateway=services.graph_api_gateway_factory(),
                existing_run=run,
            )
    raise AssertionError(f"Unsupported harness id: {run.harness_id}")


def _build_client(
    *,
    graph_chat_runner_dependency: object = _FakeGraphChatRunner,
    graph_api_gateway_dependency: object = _FakeGraphApiGateway,
) -> TestClient:
    app = create_app()
    graph_chat_runner = graph_chat_runner_dependency()
    chat_session_store = HarnessChatSessionStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    research_state_store = HarnessResearchStateStore()
    app.dependency_overrides[get_chat_session_store] = lambda: chat_session_store
    app.dependency_overrides[get_graph_chat_runner] = lambda: graph_chat_runner
    app.dependency_overrides[get_graph_connection_runner] = _FakeGraphConnectionRunner
    app.dependency_overrides[get_graph_api_gateway] = graph_api_gateway_dependency
    app.dependency_overrides[get_graph_search_runner] = _FakeGraphSearchRunner
    approval_store = HarnessApprovalStore()
    artifact_store = HarnessArtifactStore()
    proposal_store = HarnessProposalStore()
    pubmed_discovery_service = _FakePubMedDiscoveryService()
    run_registry = HarnessRunRegistry()
    schedule_store = HarnessScheduleStore()
    app.dependency_overrides[get_approval_store] = lambda: approval_store
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_graph_snapshot_store] = lambda: graph_snapshot_store
    app.dependency_overrides[get_proposal_store] = lambda: proposal_store
    app.dependency_overrides[get_pubmed_discovery_service] = (
        lambda: pubmed_discovery_service
    )
    app.dependency_overrides[get_research_state_store] = lambda: research_state_store
    app.dependency_overrides[get_run_registry] = lambda: run_registry
    app.dependency_overrides[get_schedule_store] = lambda: schedule_store
    runtime = _FakeWorkerRuntime(
        graph_api_gateway_factory=graph_api_gateway_dependency,
    )
    app.dependency_overrides[get_harness_execution_services] = (
        lambda: HarnessExecutionServices(
            runtime=runtime,
            run_registry=run_registry,
            artifact_store=artifact_store,
            chat_session_store=chat_session_store,
            proposal_store=proposal_store,
            approval_store=approval_store,
            research_state_store=research_state_store,
            graph_snapshot_store=graph_snapshot_store,
            schedule_store=schedule_store,
            graph_connection_runner=_FakeGraphConnectionRunner(),
            graph_chat_runner=graph_chat_runner,
            graph_api_gateway_factory=graph_api_gateway_dependency,
            pubmed_discovery_service_factory=lambda: _fake_pubmed_discovery_context(
                pubmed_discovery_service,
            ),
            execution_override=_execute_test_harness_run,
        )
    )
    return TestClient(app)


def _auth_headers(*, role: str = "researcher") -> dict[str, str]:
    return {
        "X-TEST-USER-ID": _TEST_USER_ID,
        "X-TEST-USER-EMAIL": _TEST_USER_EMAIL,
        "X-TEST-USER-ROLE": role,
    }


def test_health_endpoint_reports_service_identity() -> None:
    """Health endpoint should expose the harness service identity."""
    client = _build_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "MED13 Graph Harness API"


def test_list_harnesses_returns_registry_templates() -> None:
    """Harness discovery should return the static registry."""
    client = _build_client()

    response = client.get("/v1/harnesses", headers=_auth_headers(role="viewer"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 9
    harness_ids = {item["id"] for item in payload["harnesses"]}
    assert "graph-chat" in harness_ids
    assert "graph-connections" in harness_ids
    assert "graph-search" in harness_ids
    assert "hypotheses" in harness_ids
    assert "research-bootstrap" in harness_ids
    assert "supervisor" in harness_ids
    continuous_learning = next(
        item for item in payload["harnesses"] if item["id"] == "continuous-learning"
    )
    assert continuous_learning["default_run_budget"]["max_tool_calls"] == 100
    assert continuous_learning["preloaded_skill_names"] == [
        "graph_harness.graph_grounding",
        "graph_harness.evidence_diffing",
    ]
    assert (
        "graph_harness.relation_discovery" in continuous_learning["allowed_skill_names"]
    )


def test_get_harness_returns_one_template() -> None:
    """Fetching one harness should return the requested template."""
    client = _build_client()

    response = client.get(
        "/v1/harnesses/graph-chat",
        headers=_auth_headers(role="viewer"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "graph-chat"
    assert "graph" in payload["summary"].lower()
    assert payload["preloaded_skill_names"] == [
        "graph_harness.graph_grounding",
        "graph_harness.graph_write_review",
    ]
    assert payload["allowed_skill_names"] == [
        "graph_harness.graph_grounding",
        "graph_harness.graph_write_review",
        "graph_harness.literature_refresh",
        "graph_harness.relation_discovery",
    ]


def test_research_bootstrap_run_persists_research_state_and_snapshot() -> None:
    """Research bootstrap should capture graph memory and stage candidate claims."""
    client = _build_client()
    space_id = str(uuid4())
    seed_entity_id = "11111111-1111-1111-1111-111111111111"

    response = client.post(
        f"/v1/spaces/{space_id}/agents/research-bootstrap/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["run"]["harness_id"] == "research-bootstrap"
    assert payload["proposal_count"] == 1
    assert payload["graph_snapshot"]["space_id"] == space_id
    assert payload["graph_snapshot"]["graph_document_hash"] != ""
    assert payload["research_state"]["objective"] == "Map MED13 mechanism evidence."
    assert (
        payload["research_state"]["last_graph_snapshot_id"]
        == payload["graph_snapshot"]["id"]
    )
    assert payload["research_state"]["pending_questions"]
    assert payload["graph_summary"]["claim_count"] == 1
    assert payload["source_inventory"]["graph_claim_count"] == 1
    assert payload["research_brief"]["proposal_count"] == 1

    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{payload['run']['id']}/artifacts",
        headers=_auth_headers(role="viewer"),
    )
    assert artifacts_response.status_code == 200
    artifact_keys = {
        artifact["key"] for artifact in artifacts_response.json()["artifacts"]
    }
    assert {
        "run_manifest",
        "graph_context_snapshot",
        "graph_summary",
        "source_inventory",
        "candidate_claim_pack",
        "research_brief",
    }.issubset(artifact_keys)

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{payload['run']['id']}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    assert workspace_response.status_code == 200
    workspace_payload = workspace_response.json()
    assert workspace_payload["snapshot"]["status"] == "completed"
    assert (
        workspace_payload["snapshot"]["last_graph_snapshot_id"]
        == payload["graph_snapshot"]["id"]
    )
    assert workspace_payload["snapshot"]["last_candidate_claim_pack_key"] == (
        "candidate_claim_pack"
    )
    assert workspace_payload["snapshot"]["pending_question_count"] == len(
        payload["pending_questions"],
    )


def test_supervisor_run_composes_bootstrap_chat_and_curation() -> None:
    """Supervisor creation should pause the parent at the child approval gate."""
    client = _build_client()
    space_id = str(uuid4())
    seed_entity_id = "11111111-1111-1111-1111-111111111111"

    response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["run"]["harness_id"] == "supervisor"
    assert payload["run"]["status"] == "paused"
    assert payload["bootstrap"]["run"]["harness_id"] == "research-bootstrap"
    assert payload["chat"] is not None
    assert payload["chat"]["run"]["harness_id"] == "graph-chat"
    assert payload["curation"] is not None
    assert payload["curation"]["run"]["harness_id"] == "claim-curation"
    assert payload["curation"]["run"]["status"] == "paused"
    assert payload["chat_graph_write_review_count"] == 0
    assert payload["latest_chat_graph_write_review"] is None
    assert payload["chat_graph_write_reviews"] == []
    assert payload["briefing_question"] is not None
    assert len(payload["selected_curation_proposal_ids"]) == 1
    assert payload["steps"] == [
        {
            "step": "bootstrap",
            "status": "completed",
            "harness_id": "research-bootstrap",
            "run_id": payload["bootstrap"]["run"]["id"],
            "detail": "Bootstrap completed with 1 proposal(s).",
        },
        {
            "step": "chat",
            "status": "completed",
            "harness_id": "graph-chat",
            "run_id": payload["chat"]["run"]["id"],
            "detail": "Briefing chat completed.",
        },
        {
            "step": "curation",
            "status": "paused",
            "harness_id": "claim-curation",
            "run_id": payload["curation"]["run"]["id"],
            "detail": "Claim-curation run created and paused for approval.",
        },
    ]

    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{payload['run']['id']}/artifacts",
        headers=_auth_headers(role="viewer"),
    )
    assert artifacts_response.status_code == 200
    artifact_keys = {
        artifact["key"] for artifact in artifacts_response.json()["artifacts"]
    }
    assert {
        "run_manifest",
        "supervisor_plan",
        "supervisor_summary",
        "child_run_links",
    }.issubset(artifact_keys)

    progress_response = client.get(
        f"/v1/spaces/{space_id}/runs/{payload['run']['id']}/progress",
        headers=_auth_headers(role="viewer"),
    )
    assert progress_response.status_code == 200
    progress_payload = progress_response.json()
    assert progress_payload["status"] == "paused"
    assert progress_payload["phase"] == "approval"
    assert progress_payload["resume_point"] == "supervisor_child_approval_gate"

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{payload['run']['id']}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    assert workspace_response.status_code == 200
    workspace_payload = workspace_response.json()
    assert workspace_payload["snapshot"]["status"] == "paused"
    assert (
        workspace_payload["snapshot"]["bootstrap_run_id"]
        == payload["bootstrap"]["run"]["id"]
    )
    assert workspace_payload["snapshot"]["chat_run_id"] == payload["chat"]["run"]["id"]
    assert (
        workspace_payload["snapshot"]["curation_run_id"]
        == payload["curation"]["run"]["id"]
    )
    assert (
        workspace_payload["snapshot"]["resume_point"]
        == "supervisor_child_approval_gate"
    )
    assert workspace_payload["snapshot"]["pending_approvals"] == 1
    assert workspace_payload["snapshot"]["selected_curation_proposal_ids"] == (
        payload["selected_curation_proposal_ids"]
    )

    capabilities_response = client.get(
        f"/v1/spaces/{space_id}/runs/{payload['run']['id']}/capabilities",
        headers=_auth_headers(role="viewer"),
    )
    assert capabilities_response.status_code == 200
    capabilities_payload = capabilities_response.json()
    assert capabilities_payload["preloaded_skill_names"] == [
        "graph_harness.supervisor_coordination",
    ]
    assert capabilities_payload["active_skill_names"] == [
        "graph_harness.supervisor_coordination",
        "graph_harness.graph_grounding",
        "graph_harness.relation_discovery",
        "graph_harness.graph_write_review",
        "graph_harness.claim_validation",
    ]

    policy_response = client.get(
        f"/v1/spaces/{space_id}/runs/{payload['run']['id']}/policy-decisions",
        headers=_auth_headers(role="viewer"),
    )
    assert policy_response.status_code == 200
    policy_payload = policy_response.json()
    assert policy_payload["summary"]["tool_record_count"] == 0
    assert policy_payload["summary"]["manual_review_count"] == 0
    assert policy_payload["summary"]["skill_record_count"] == 6


def test_supervisor_run_requires_child_approvals_before_parent_resume() -> None:
    """Supervisor resume should block until child curation approvals are resolved."""
    client = _build_client()
    space_id = str(uuid4())
    seed_entity_id = "11111111-1111-1111-1111-111111111111"

    create_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
        },
        headers=_auth_headers(),
    )
    assert create_response.status_code == 201
    supervisor_run_id = create_response.json()["run"]["id"]

    resume_response = client.post(
        f"/v1/spaces/{space_id}/runs/{supervisor_run_id}/resume",
        json={"reason": "Resume parent run"},
        headers=_auth_headers(),
    )

    assert resume_response.status_code == 409
    assert "pending approvals" in resume_response.json()["detail"]


def test_get_supervisor_run_detail_returns_typed_composed_state() -> None:
    """Supervisor detail should reload the persisted composed state for viewer clients."""
    client = _build_client()
    space_id = str(uuid4())
    seed_entity_id = "11111111-1111-1111-1111-111111111111"

    create_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
        },
        headers=_auth_headers(),
    )
    assert create_response.status_code == 201
    create_payload = create_response.json()
    supervisor_run_id = create_payload["run"]["id"]

    detail_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs/{supervisor_run_id}",
        headers=_auth_headers(role="viewer"),
    )

    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["run"]["id"] == supervisor_run_id
    assert payload["run"]["status"] == "paused"
    assert payload["progress"]["status"] == "paused"
    assert payload["progress"]["resume_point"] == "supervisor_child_approval_gate"
    assert payload["workflow"] == "bootstrap_chat_curation"
    assert payload["bootstrap"]["run"]["id"] == create_payload["bootstrap"]["run"]["id"]
    assert (
        payload["bootstrap"]["proposal_count"]
        == create_payload["bootstrap"]["proposal_count"]
    )
    assert payload["chat"]["run"]["id"] == create_payload["chat"]["run"]["id"]
    assert payload["chat"]["session"]["id"] == create_payload["chat"]["session"]["id"]
    assert payload["curation"]["run"]["id"] == create_payload["curation"]["run"]["id"]
    assert payload["curation"]["run"]["status"] == "paused"
    assert payload["curation"]["pending_approval_count"] == 1
    assert payload["bootstrap_run_id"] == create_payload["bootstrap"]["run"]["id"]
    assert payload["chat_run_id"] == create_payload["chat"]["run"]["id"]
    assert payload["chat_session_id"] == create_payload["chat"]["session"]["id"]
    assert payload["curation_run_id"] == create_payload["curation"]["run"]["id"]
    assert payload["curation_status"] == "paused"
    assert payload["curation_source"] == create_payload["curation_source"]
    assert payload["chat_graph_write_proposal_ids"] == []
    assert payload["selected_curation_proposal_ids"] == (
        create_payload["selected_curation_proposal_ids"]
    )
    assert payload["skipped_steps"] == []
    assert payload["chat_graph_write_review_count"] == 0
    assert payload["latest_chat_graph_write_review"] is None
    assert payload["chat_graph_write_reviews"] == []
    assert payload["completed_at"] is None
    assert payload["artifact_keys"]["supervisor_plan"] == "supervisor_plan"
    assert payload["artifact_keys"]["supervisor_summary"] == "supervisor_summary"
    assert payload["artifact_keys"]["child_run_links"] == "child_run_links"
    assert payload["artifact_keys"]["bootstrap"]["graph_context_snapshot"] == (
        "graph_context_snapshot"
    )
    assert payload["artifact_keys"]["chat"]["graph_chat_result"] == "graph_chat_result"
    assert payload["artifact_keys"]["curation"]["review_plan"] == "review_plan"
    assert payload["artifact_keys"]["curation"]["curation_summary"] is None
    assert payload["artifact_keys"]["curation"]["curation_actions"] is None
    assert payload["curation_summary"] is None
    assert payload["curation_actions"] is None
    assert payload["steps"] == create_payload["steps"]


def test_list_supervisor_runs_returns_typed_child_summaries_and_artifact_keys() -> None:
    """Supervisor list should filter to supervisor runs and expose typed child state."""
    client = _build_client()
    space_id = str(uuid4())
    seed_entity_id = "11111111-1111-1111-1111-111111111111"

    create_supervisor_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
        },
        headers=_auth_headers(),
    )
    assert create_supervisor_response.status_code == 201
    supervisor_payload = create_supervisor_response.json()

    create_generic_response = client.post(
        f"/v1/spaces/{space_id}/runs",
        json={
            "harness_id": "graph-chat",
            "title": "Generic graph chat run",
            "input_payload": {"question": "Ignored by supervisor list"},
        },
        headers=_auth_headers(),
    )
    assert create_generic_response.status_code == 201

    list_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        headers=_auth_headers(role="viewer"),
    )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["summary"]["total_runs"] == 1
    assert payload["summary"]["paused_run_count"] == 1
    assert payload["summary"]["completed_run_count"] == 0
    assert payload["summary"]["reviewed_run_count"] == 0
    assert payload["summary"]["unreviewed_run_count"] == 1
    assert payload["summary"]["bootstrap_curation_run_count"] == 1
    assert payload["summary"]["chat_graph_write_curation_run_count"] == 0
    assert payload["summary"]["trends"]["recent_24h_count"] == 1
    assert payload["summary"]["trends"]["recent_7d_count"] == 1
    assert payload["summary"]["trends"]["recent_completed_24h_count"] == 0
    assert payload["summary"]["trends"]["recent_completed_7d_count"] == 0
    assert payload["summary"]["trends"]["recent_reviewed_24h_count"] == 0
    assert payload["summary"]["trends"]["recent_reviewed_7d_count"] == 0
    assert payload["summary"]["trends"]["daily_created_counts"] == [
        {
            "day": supervisor_payload["run"]["created_at"][:10],
            "count": 1,
        },
    ]
    assert payload["summary"]["trends"]["daily_completed_counts"] == []
    assert payload["summary"]["trends"]["daily_reviewed_counts"] == []
    assert payload["summary"]["trends"]["daily_unreviewed_counts"] == [
        {
            "day": supervisor_payload["run"]["created_at"][:10],
            "count": 1,
        },
    ]
    assert payload["summary"]["trends"]["daily_bootstrap_curation_counts"] == [
        {
            "day": supervisor_payload["run"]["created_at"][:10],
            "count": 1,
        },
    ]
    assert payload["summary"]["trends"]["daily_chat_graph_write_curation_counts"] == []
    assert len(payload["runs"]) == 1
    listed_run = payload["runs"][0]
    assert listed_run["completed_at"] is None
    assert listed_run["run"]["id"] == supervisor_payload["run"]["id"]
    assert (
        listed_run["bootstrap"]["run"]["id"]
        == supervisor_payload["bootstrap"]["run"]["id"]
    )
    assert listed_run["chat"]["run"]["id"] == supervisor_payload["chat"]["run"]["id"]
    assert (
        listed_run["curation"]["run"]["id"]
        == supervisor_payload["curation"]["run"]["id"]
    )
    assert listed_run["artifact_keys"]["bootstrap"]["candidate_claim_pack"] == (
        "candidate_claim_pack"
    )
    assert listed_run["artifact_keys"]["chat"]["chat_summary"] == "chat_summary"
    assert listed_run["artifact_keys"]["curation"]["approval_intent"] == (
        "approval_intent"
    )


def test_list_supervisor_runs_supports_status_source_and_review_filters() -> None:
    """Supervisor list filters should narrow typed workflow runs by parent state."""
    client = _build_client()
    space_id = str(uuid4())
    seed_entity_id = "11111111-1111-1111-1111-111111111111"

    paused_bootstrap_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
        },
        headers=_auth_headers(),
    )
    assert paused_bootstrap_response.status_code == 201
    paused_bootstrap_id = paused_bootstrap_response.json()["run"]["id"]

    paused_chat_graph_write_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
            "curation_source": "chat_graph_write",
        },
        headers=_auth_headers(),
    )
    assert paused_chat_graph_write_response.status_code == 201
    paused_chat_graph_write_id = paused_chat_graph_write_response.json()["run"]["id"]

    completed_reviewed_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "include_curation": False,
        },
        headers=_auth_headers(),
    )
    assert completed_reviewed_response.status_code == 201
    completed_reviewed_payload = completed_reviewed_response.json()
    completed_reviewed_id = completed_reviewed_payload["run"]["id"]

    review_response = client.post(
        (
            f"/v1/spaces/{space_id}/agents/supervisor/runs/{completed_reviewed_id}/"
            "chat-graph-write-candidates/0/review"
        ),
        json={"decision": "promote", "reason": "Promote directly from supervisor."},
        headers=_auth_headers(),
    )
    assert review_response.status_code == 200

    completed_filter_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        params={"status": "completed"},
        headers=_auth_headers(role="viewer"),
    )
    assert completed_filter_response.status_code == 200
    completed_filter_payload = completed_filter_response.json()
    assert completed_filter_payload["total"] == 1
    assert completed_filter_payload["summary"]["total_runs"] == 1
    assert completed_filter_payload["summary"]["completed_run_count"] == 1
    assert completed_filter_payload["summary"]["reviewed_run_count"] == 1
    assert completed_filter_payload["summary"]["trends"]["recent_24h_count"] == 1
    assert (
        completed_filter_payload["summary"]["trends"]["recent_completed_24h_count"] == 1
    )
    assert (
        completed_filter_payload["summary"]["trends"]["recent_completed_7d_count"] == 1
    )
    assert (
        completed_filter_payload["summary"]["trends"]["recent_reviewed_24h_count"] == 1
    )
    assert (
        completed_filter_payload["summary"]["trends"]["recent_reviewed_7d_count"] == 1
    )
    assert completed_filter_payload["summary"]["trends"]["daily_reviewed_counts"] == [
        {
            "day": review_response.json()["latest_chat_graph_write_review"][
                "reviewed_at"
            ][:10],
            "count": 1,
        },
    ]
    assert (
        completed_filter_payload["summary"]["trends"]["daily_unreviewed_counts"] == []
    )
    assert completed_filter_payload["summary"]["trends"]["daily_completed_counts"] == [
        {
            "day": review_response.json()["run"]["updated_at"][:10],
            "count": 1,
        },
    ]
    assert completed_filter_payload["summary"]["trends"][
        "daily_bootstrap_curation_counts"
    ] == [
        {
            "day": completed_reviewed_payload["run"]["created_at"][:10],
            "count": 1,
        },
    ]
    assert (
        completed_filter_payload["summary"]["trends"][
            "daily_chat_graph_write_curation_counts"
        ]
        == []
    )
    assert [run["run"]["id"] for run in completed_filter_payload["runs"]] == [
        completed_reviewed_id,
    ]

    paused_filter_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        params={"status": "paused"},
        headers=_auth_headers(role="viewer"),
    )
    assert paused_filter_response.status_code == 200
    paused_filter_payload = paused_filter_response.json()
    assert paused_filter_payload["total"] == 2
    assert paused_filter_payload["summary"]["total_runs"] == 2
    assert paused_filter_payload["summary"]["paused_run_count"] == 2
    assert paused_filter_payload["summary"]["completed_run_count"] == 0
    assert paused_filter_payload["summary"]["trends"]["recent_24h_count"] == 2
    assert paused_filter_payload["summary"]["trends"]["recent_completed_24h_count"] == 0
    assert paused_filter_payload["summary"]["trends"]["recent_completed_7d_count"] == 0
    assert paused_filter_payload["summary"]["trends"]["recent_reviewed_24h_count"] == 0
    assert paused_filter_payload["summary"]["trends"]["recent_reviewed_7d_count"] == 0
    assert paused_filter_payload["summary"]["trends"]["daily_completed_counts"] == []
    assert paused_filter_payload["summary"]["trends"]["daily_reviewed_counts"] == []
    assert paused_filter_payload["summary"]["trends"]["daily_unreviewed_counts"] == [
        {
            "day": paused_bootstrap_response.json()["run"]["created_at"][:10],
            "count": 2,
        },
    ]
    assert paused_filter_payload["summary"]["trends"][
        "daily_bootstrap_curation_counts"
    ] == [
        {
            "day": paused_bootstrap_response.json()["run"]["created_at"][:10],
            "count": 1,
        },
    ]
    assert paused_filter_payload["summary"]["trends"][
        "daily_chat_graph_write_curation_counts"
    ] == [
        {
            "day": paused_chat_graph_write_response.json()["run"]["created_at"][:10],
            "count": 1,
        },
    ]
    assert {run["run"]["id"] for run in paused_filter_payload["runs"]} == {
        paused_bootstrap_id,
        paused_chat_graph_write_id,
    }

    source_filter_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        params={"curation_source": "chat_graph_write"},
        headers=_auth_headers(role="viewer"),
    )
    assert source_filter_response.status_code == 200
    source_filter_payload = source_filter_response.json()
    assert source_filter_payload["total"] == 1
    assert source_filter_payload["summary"]["chat_graph_write_curation_run_count"] == 1
    assert source_filter_payload["summary"]["bootstrap_curation_run_count"] == 0
    assert source_filter_payload["summary"]["trends"]["recent_completed_24h_count"] == 0
    assert source_filter_payload["summary"]["trends"]["recent_completed_7d_count"] == 0
    assert source_filter_payload["summary"]["trends"]["recent_reviewed_24h_count"] == 0
    assert source_filter_payload["summary"]["trends"]["recent_reviewed_7d_count"] == 0
    assert source_filter_payload["summary"]["trends"]["daily_completed_counts"] == []
    assert source_filter_payload["summary"]["trends"]["daily_reviewed_counts"] == []
    assert source_filter_payload["summary"]["trends"]["daily_unreviewed_counts"] == [
        {
            "day": paused_chat_graph_write_response.json()["run"]["created_at"][:10],
            "count": 1,
        },
    ]
    assert (
        source_filter_payload["summary"]["trends"]["daily_bootstrap_curation_counts"]
        == []
    )
    assert source_filter_payload["summary"]["trends"][
        "daily_chat_graph_write_curation_counts"
    ] == [
        {
            "day": paused_chat_graph_write_response.json()["run"]["created_at"][:10],
            "count": 1,
        },
    ]
    assert source_filter_payload["runs"][0]["run"]["id"] == paused_chat_graph_write_id

    reviewed_filter_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        params={"has_chat_graph_write_reviews": "true"},
        headers=_auth_headers(role="viewer"),
    )
    assert reviewed_filter_response.status_code == 200
    reviewed_filter_payload = reviewed_filter_response.json()
    assert reviewed_filter_payload["total"] == 1
    assert reviewed_filter_payload["summary"]["reviewed_run_count"] == 1
    assert reviewed_filter_payload["summary"]["unreviewed_run_count"] == 0
    assert (
        reviewed_filter_payload["summary"]["trends"]["recent_completed_24h_count"] == 1
    )
    assert (
        reviewed_filter_payload["summary"]["trends"]["recent_completed_7d_count"] == 1
    )
    assert (
        reviewed_filter_payload["summary"]["trends"]["recent_reviewed_24h_count"] == 1
    )
    assert reviewed_filter_payload["summary"]["trends"]["recent_reviewed_7d_count"] == 1
    assert reviewed_filter_payload["summary"]["trends"]["daily_completed_counts"] == [
        {
            "day": review_response.json()["run"]["updated_at"][:10],
            "count": 1,
        },
    ]
    assert reviewed_filter_payload["summary"]["trends"]["daily_reviewed_counts"] == [
        {
            "day": review_response.json()["latest_chat_graph_write_review"][
                "reviewed_at"
            ][:10],
            "count": 1,
        },
    ]
    assert reviewed_filter_payload["summary"]["trends"]["daily_unreviewed_counts"] == []
    assert reviewed_filter_payload["summary"]["trends"][
        "daily_bootstrap_curation_counts"
    ] == [
        {
            "day": completed_reviewed_payload["run"]["created_at"][:10],
            "count": 1,
        },
    ]
    assert (
        reviewed_filter_payload["summary"]["trends"][
            "daily_chat_graph_write_curation_counts"
        ]
        == []
    )
    assert reviewed_filter_payload["runs"][0]["run"]["id"] == completed_reviewed_id

    unreviewed_filter_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        params={"has_chat_graph_write_reviews": "false"},
        headers=_auth_headers(role="viewer"),
    )
    assert unreviewed_filter_response.status_code == 200
    unreviewed_filter_payload = unreviewed_filter_response.json()
    assert unreviewed_filter_payload["total"] == 2
    assert unreviewed_filter_payload["summary"]["reviewed_run_count"] == 0
    assert unreviewed_filter_payload["summary"]["unreviewed_run_count"] == 2
    assert (
        unreviewed_filter_payload["summary"]["trends"]["recent_completed_24h_count"]
        == 0
    )
    assert (
        unreviewed_filter_payload["summary"]["trends"]["recent_completed_7d_count"] == 0
    )
    assert (
        unreviewed_filter_payload["summary"]["trends"]["recent_reviewed_24h_count"] == 0
    )
    assert (
        unreviewed_filter_payload["summary"]["trends"]["recent_reviewed_7d_count"] == 0
    )
    assert (
        unreviewed_filter_payload["summary"]["trends"]["daily_completed_counts"] == []
    )
    assert unreviewed_filter_payload["summary"]["trends"]["daily_reviewed_counts"] == []
    assert unreviewed_filter_payload["summary"]["trends"][
        "daily_unreviewed_counts"
    ] == [
        {
            "day": paused_bootstrap_response.json()["run"]["created_at"][:10],
            "count": 2,
        },
    ]
    assert unreviewed_filter_payload["summary"]["trends"][
        "daily_bootstrap_curation_counts"
    ] == [
        {
            "day": paused_bootstrap_response.json()["run"]["created_at"][:10],
            "count": 1,
        },
    ]
    assert unreviewed_filter_payload["summary"]["trends"][
        "daily_chat_graph_write_curation_counts"
    ] == [
        {
            "day": paused_chat_graph_write_response.json()["run"]["created_at"][:10],
            "count": 1,
        },
    ]
    assert {run["run"]["id"] for run in unreviewed_filter_payload["runs"]} == {
        paused_bootstrap_id,
        paused_chat_graph_write_id,
    }


def test_list_supervisor_runs_supports_sorting_and_pagination() -> None:
    """Supervisor list should support stable sorting and filtered pagination."""
    client = _build_client()
    space_id = str(uuid4())
    seed_entity_id = "11111111-1111-1111-1111-111111111111"

    first_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "First supervisor run.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
        },
        headers=_auth_headers(),
    )
    assert first_response.status_code == 201
    first_run_id = first_response.json()["run"]["id"]

    second_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Second supervisor run.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
            "curation_source": "chat_graph_write",
        },
        headers=_auth_headers(),
    )
    assert second_response.status_code == 201
    second_run_id = second_response.json()["run"]["id"]

    third_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Third supervisor run.",
            "seed_entity_ids": [seed_entity_id],
            "include_curation": False,
        },
        headers=_auth_headers(),
    )
    assert third_response.status_code == 201
    third_payload = third_response.json()
    third_run_id = third_payload["run"]["id"]

    review_response = client.post(
        (
            f"/v1/spaces/{space_id}/agents/supervisor/runs/{third_run_id}/"
            "chat-graph-write-candidates/0/review"
        ),
        json={"decision": "promote", "reason": "Promote for review-count sorting."},
        headers=_auth_headers(),
    )
    assert review_response.status_code == 200

    created_sort_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        params={
            "sort_by": "created_at",
            "sort_direction": "asc",
            "offset": 1,
            "limit": 1,
        },
        headers=_auth_headers(role="viewer"),
    )
    assert created_sort_response.status_code == 200
    created_sort_payload = created_sort_response.json()
    assert created_sort_payload["total"] == 3
    assert created_sort_payload["summary"]["total_runs"] == 3
    assert created_sort_payload["summary"]["paused_run_count"] == 2
    assert created_sort_payload["summary"]["completed_run_count"] == 1
    assert created_sort_payload["summary"]["reviewed_run_count"] == 1
    assert created_sort_payload["summary"]["trends"]["recent_24h_count"] == 3
    assert created_sort_payload["summary"]["trends"]["recent_7d_count"] == 3
    assert created_sort_payload["summary"]["trends"]["recent_completed_24h_count"] == 1
    assert created_sort_payload["summary"]["trends"]["recent_completed_7d_count"] == 1
    assert created_sort_payload["summary"]["trends"]["recent_reviewed_24h_count"] == 1
    assert created_sort_payload["summary"]["trends"]["recent_reviewed_7d_count"] == 1
    assert created_sort_payload["summary"]["trends"]["daily_created_counts"] == [
        {
            "day": first_response.json()["run"]["created_at"][:10],
            "count": 3,
        },
    ]
    assert created_sort_payload["summary"]["trends"]["daily_completed_counts"] == [
        {
            "day": review_response.json()["run"]["updated_at"][:10],
            "count": 1,
        },
    ]
    assert created_sort_payload["summary"]["trends"]["daily_reviewed_counts"] == [
        {
            "day": review_response.json()["latest_chat_graph_write_review"][
                "reviewed_at"
            ][:10],
            "count": 1,
        },
    ]
    assert created_sort_payload["summary"]["trends"]["daily_unreviewed_counts"] == [
        {
            "day": first_response.json()["run"]["created_at"][:10],
            "count": 2,
        },
    ]
    assert created_sort_payload["summary"]["trends"][
        "daily_bootstrap_curation_counts"
    ] == [
        {
            "day": first_response.json()["run"]["created_at"][:10],
            "count": 2,
        },
    ]
    assert created_sort_payload["summary"]["trends"][
        "daily_chat_graph_write_curation_counts"
    ] == [
        {
            "day": second_response.json()["run"]["created_at"][:10],
            "count": 1,
        },
    ]
    assert len(created_sort_payload["runs"]) == 1
    assert created_sort_payload["runs"][0]["run"]["id"] == second_run_id

    review_sort_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        params={
            "sort_by": "chat_graph_write_review_count",
            "sort_direction": "desc",
        },
        headers=_auth_headers(role="viewer"),
    )
    assert review_sort_response.status_code == 200
    review_sort_payload = review_sort_response.json()
    assert review_sort_payload["total"] == 3
    assert review_sort_payload["summary"]["bootstrap_curation_run_count"] == 2
    assert review_sort_payload["summary"]["chat_graph_write_curation_run_count"] == 1
    assert review_sort_payload["runs"][0]["run"]["id"] == third_run_id
    assert review_sort_payload["runs"][0]["chat_graph_write_review_count"] == 1
    assert {run["run"]["id"] for run in review_sort_payload["runs"][1:]} == {
        first_run_id,
        second_run_id,
    }


def test_list_supervisor_runs_supports_created_and_updated_time_windows() -> None:
    """Supervisor list should support created/updated time-window filters."""
    client = _build_client()
    space_id = str(uuid4())
    seed_entity_id = "11111111-1111-1111-1111-111111111111"

    first_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "First supervisor run.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
        },
        headers=_auth_headers(),
    )
    assert first_response.status_code == 201

    second_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Second supervisor run.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
            "curation_source": "chat_graph_write",
        },
        headers=_auth_headers(),
    )
    assert second_response.status_code == 201
    second_payload = second_response.json()
    second_run_id = second_payload["run"]["id"]
    second_created_at = second_payload["run"]["created_at"]

    third_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Third supervisor run.",
            "seed_entity_ids": [seed_entity_id],
            "include_curation": False,
        },
        headers=_auth_headers(),
    )
    assert third_response.status_code == 201
    third_payload = third_response.json()
    third_run_id = third_payload["run"]["id"]

    review_response = client.post(
        (
            f"/v1/spaces/{space_id}/agents/supervisor/runs/{third_run_id}/"
            "chat-graph-write-candidates/0/review"
        ),
        json={"decision": "promote", "reason": "Promote for updated-window filter."},
        headers=_auth_headers(),
    )
    assert review_response.status_code == 200
    reviewed_updated_at = review_response.json()["run"]["updated_at"]

    created_window_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        params={
            "created_after": second_created_at,
            "created_before": second_created_at,
        },
        headers=_auth_headers(role="viewer"),
    )
    assert created_window_response.status_code == 200
    created_window_payload = created_window_response.json()
    assert created_window_payload["total"] == 1
    assert created_window_payload["summary"]["total_runs"] == 1
    assert created_window_payload["summary"]["trends"]["recent_24h_count"] == 1
    assert (
        created_window_payload["summary"]["trends"]["recent_completed_24h_count"] == 0
    )
    assert created_window_payload["summary"]["trends"]["recent_completed_7d_count"] == 0
    assert created_window_payload["summary"]["trends"]["recent_reviewed_24h_count"] == 0
    assert created_window_payload["summary"]["trends"]["recent_reviewed_7d_count"] == 0
    assert created_window_payload["summary"]["trends"]["daily_created_counts"] == [
        {
            "day": second_created_at[:10],
            "count": 1,
        },
    ]
    assert created_window_payload["summary"]["trends"]["daily_completed_counts"] == []
    assert created_window_payload["summary"]["trends"]["daily_reviewed_counts"] == []
    assert created_window_payload["summary"]["trends"]["daily_unreviewed_counts"] == [
        {
            "day": second_created_at[:10],
            "count": 1,
        },
    ]
    assert (
        created_window_payload["summary"]["trends"]["daily_bootstrap_curation_counts"]
        == []
    )
    assert created_window_payload["summary"]["trends"][
        "daily_chat_graph_write_curation_counts"
    ] == [
        {
            "day": second_created_at[:10],
            "count": 1,
        },
    ]
    assert created_window_payload["runs"][0]["run"]["id"] == second_run_id

    updated_window_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        params={
            "updated_after": reviewed_updated_at,
            "updated_before": reviewed_updated_at,
        },
        headers=_auth_headers(role="viewer"),
    )
    assert updated_window_response.status_code == 200
    updated_window_payload = updated_window_response.json()
    assert updated_window_payload["total"] == 1
    assert updated_window_payload["summary"]["total_runs"] == 1
    assert updated_window_payload["summary"]["completed_run_count"] == 1
    assert updated_window_payload["summary"]["reviewed_run_count"] == 1
    assert updated_window_payload["summary"]["trends"]["recent_24h_count"] == 1
    assert (
        updated_window_payload["summary"]["trends"]["recent_completed_24h_count"] == 1
    )
    assert updated_window_payload["summary"]["trends"]["recent_completed_7d_count"] == 1
    assert updated_window_payload["summary"]["trends"]["recent_reviewed_24h_count"] == 1
    assert updated_window_payload["summary"]["trends"]["recent_reviewed_7d_count"] == 1
    assert updated_window_payload["summary"]["trends"]["daily_completed_counts"] == [
        {
            "day": reviewed_updated_at[:10],
            "count": 1,
        },
    ]
    assert updated_window_payload["summary"]["trends"]["daily_reviewed_counts"] == [
        {
            "day": review_response.json()["latest_chat_graph_write_review"][
                "reviewed_at"
            ][:10],
            "count": 1,
        },
    ]
    assert updated_window_payload["summary"]["trends"]["daily_unreviewed_counts"] == []
    assert updated_window_payload["summary"]["trends"][
        "daily_bootstrap_curation_counts"
    ] == [
        {
            "day": third_payload["run"]["created_at"][:10],
            "count": 1,
        },
    ]
    assert (
        updated_window_payload["summary"]["trends"][
            "daily_chat_graph_write_curation_counts"
        ]
        == []
    )
    assert updated_window_payload["runs"][0]["run"]["id"] == third_run_id


def test_get_supervisor_dashboard_returns_summary_without_paginated_runs() -> None:
    """Supervisor dashboard should reuse the typed list summary without row payload."""
    client = _build_client()
    space_id = str(uuid4())
    seed_entity_id = "11111111-1111-1111-1111-111111111111"

    paused_bootstrap_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
        },
        headers=_auth_headers(),
    )
    assert paused_bootstrap_response.status_code == 201

    paused_chat_graph_write_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
            "curation_source": "chat_graph_write",
        },
        headers=_auth_headers(),
    )
    assert paused_chat_graph_write_response.status_code == 201

    completed_reviewed_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "include_curation": False,
        },
        headers=_auth_headers(),
    )
    assert completed_reviewed_response.status_code == 201
    completed_reviewed_id = completed_reviewed_response.json()["run"]["id"]

    review_response = client.post(
        (
            f"/v1/spaces/{space_id}/agents/supervisor/runs/{completed_reviewed_id}/"
            "chat-graph-write-candidates/0/review"
        ),
        json={"decision": "promote", "reason": "Promote for dashboard summary."},
        headers=_auth_headers(),
    )
    assert review_response.status_code == 200

    dashboard_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/dashboard",
        headers=_auth_headers(role="viewer"),
    )
    list_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        headers=_auth_headers(role="viewer"),
    )

    assert dashboard_response.status_code == 200
    assert list_response.status_code == 200
    dashboard_payload = dashboard_response.json()
    list_payload = list_response.json()
    assert set(dashboard_payload.keys()) == {"summary", "highlights"}
    assert dashboard_payload["summary"] == list_payload["summary"]
    assert dashboard_payload["highlights"]["latest_completed_run"]["run_id"] == (
        completed_reviewed_id
    )
    assert dashboard_payload["highlights"]["latest_completed_run"]["timestamp"] == (
        completed_reviewed_response.json()["run"]["updated_at"]
    )
    assert dashboard_payload["highlights"]["latest_reviewed_run"]["run_id"] == (
        completed_reviewed_id
    )
    assert dashboard_payload["highlights"]["latest_reviewed_run"]["timestamp"] == (
        review_response.json()["latest_chat_graph_write_review"]["reviewed_at"]
    )
    assert dashboard_payload["highlights"]["oldest_paused_run"]["run_id"] == (
        paused_bootstrap_response.json()["run"]["id"]
    )
    assert dashboard_payload["highlights"]["oldest_paused_run"]["timestamp"] == (
        paused_bootstrap_response.json()["run"]["created_at"]
    )
    assert dashboard_payload["highlights"]["latest_bootstrap_run"]["run_id"] == (
        completed_reviewed_id
    )
    assert dashboard_payload["highlights"]["latest_bootstrap_run"]["timestamp"] == (
        completed_reviewed_response.json()["run"]["created_at"]
    )
    assert dashboard_payload["highlights"]["latest_chat_graph_write_run"]["run_id"] == (
        paused_chat_graph_write_response.json()["run"]["id"]
    )
    assert (
        dashboard_payload["highlights"]["latest_chat_graph_write_run"]["timestamp"]
        == paused_chat_graph_write_response.json()["run"]["created_at"]
    )
    assert (
        dashboard_payload["highlights"]["latest_approval_paused_run"]["run_id"]
        == paused_chat_graph_write_response.json()["run"]["id"]
    )
    assert (
        dashboard_payload["highlights"]["latest_approval_paused_run"][
            "pending_approval_count"
        ]
        == 1
    )
    assert (
        dashboard_payload["highlights"]["latest_approval_paused_run"]["curation_run_id"]
        == paused_chat_graph_write_response.json()["curation"]["run"]["id"]
    )
    assert (
        dashboard_payload["highlights"]["latest_approval_paused_run"][
            "curation_packet_key"
        ]
        == "curation_packet"
    )
    assert (
        dashboard_payload["highlights"]["latest_approval_paused_run"]["review_plan_key"]
        == "review_plan"
    )
    assert (
        dashboard_payload["highlights"]["latest_approval_paused_run"][
            "approval_intent_key"
        ]
        == "approval_intent"
    )
    assert (
        dashboard_payload["highlights"]["largest_pending_review_run"]["run_id"]
        == paused_chat_graph_write_response.json()["run"]["id"]
    )
    assert (
        dashboard_payload["highlights"]["largest_pending_review_run"][
            "pending_approval_count"
        ]
        == 1
    )
    assert (
        dashboard_payload["highlights"]["largest_pending_review_run"]["curation_run_id"]
        == paused_chat_graph_write_response.json()["curation"]["run"]["id"]
    )
    assert (
        dashboard_payload["highlights"]["largest_pending_bootstrap_review_run"][
            "run_id"
        ]
        == paused_bootstrap_response.json()["run"]["id"]
    )
    assert (
        dashboard_payload["highlights"]["largest_pending_bootstrap_review_run"][
            "pending_approval_count"
        ]
        == 1
    )
    assert (
        dashboard_payload["highlights"]["largest_pending_bootstrap_review_run"][
            "curation_run_id"
        ]
        == paused_bootstrap_response.json()["curation"]["run"]["id"]
    )
    assert (
        dashboard_payload["highlights"]["largest_pending_chat_graph_write_review_run"][
            "run_id"
        ]
        == paused_chat_graph_write_response.json()["run"]["id"]
    )
    assert (
        dashboard_payload["highlights"]["largest_pending_chat_graph_write_review_run"][
            "pending_approval_count"
        ]
        == 1
    )
    assert (
        dashboard_payload["highlights"]["largest_pending_chat_graph_write_review_run"][
            "curation_run_id"
        ]
        == paused_chat_graph_write_response.json()["curation"]["run"]["id"]
    )

    filtered_dashboard_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/dashboard",
        params={
            "status": "completed",
            "has_chat_graph_write_reviews": "true",
        },
        headers=_auth_headers(role="viewer"),
    )
    filtered_list_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        params={
            "status": "completed",
            "has_chat_graph_write_reviews": "true",
        },
        headers=_auth_headers(role="viewer"),
    )

    assert filtered_dashboard_response.status_code == 200
    assert filtered_list_response.status_code == 200
    filtered_dashboard_payload = filtered_dashboard_response.json()
    filtered_list_payload = filtered_list_response.json()
    assert filtered_dashboard_payload["summary"] == filtered_list_payload["summary"]
    assert filtered_dashboard_payload["summary"]["total_runs"] == 1
    assert filtered_dashboard_payload["summary"]["completed_run_count"] == 1
    assert filtered_dashboard_payload["summary"]["reviewed_run_count"] == 1
    assert filtered_dashboard_payload["highlights"]["latest_completed_run"][
        "run_id"
    ] == (completed_reviewed_id)
    assert filtered_dashboard_payload["highlights"]["latest_reviewed_run"][
        "run_id"
    ] == (completed_reviewed_id)
    assert filtered_dashboard_payload["highlights"]["oldest_paused_run"] is None
    assert filtered_dashboard_payload["highlights"]["latest_bootstrap_run"][
        "run_id"
    ] == (completed_reviewed_id)
    assert (
        filtered_dashboard_payload["highlights"]["latest_chat_graph_write_run"] is None
    )
    assert (
        filtered_dashboard_payload["highlights"]["latest_approval_paused_run"] is None
    )
    assert (
        filtered_dashboard_payload["highlights"]["largest_pending_review_run"] is None
    )
    assert (
        filtered_dashboard_payload["highlights"]["largest_pending_bootstrap_review_run"]
        is None
    )
    assert (
        filtered_dashboard_payload["highlights"][
            "largest_pending_chat_graph_write_review_run"
        ]
        is None
    )


def test_supervisor_can_auto_derive_chat_graph_write_proposals() -> None:
    """Supervisor should auto-derive chat graph-write proposals from verified evidence."""
    client = _build_client()
    space_id = str(uuid4())
    seed_entity_id = "11111111-1111-1111-1111-111111111111"

    create_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
            "curation_source": "chat_graph_write",
        },
        headers=_auth_headers(),
    )

    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["run"]["status"] == "paused"
    assert payload["curation_source"] == "chat_graph_write"
    assert len(payload["chat_graph_write_proposal_ids"]) == 1
    assert (
        payload["selected_curation_proposal_ids"]
        == payload["chat_graph_write_proposal_ids"]
    )

    selected_proposal_response = client.get(
        f"/v1/spaces/{space_id}/proposals/{payload['selected_curation_proposal_ids'][0]}",
        headers=_auth_headers(role="viewer"),
    )
    assert selected_proposal_response.status_code == 200
    selected_proposal_payload = selected_proposal_response.json()
    assert selected_proposal_payload["source_kind"] == "chat_graph_write"
    assert selected_proposal_payload["run_id"] == payload["chat"]["run"]["id"]
    assert selected_proposal_payload["payload"]["proposed_subject"] == (
        _GRAPH_CHAT_EVIDENCE_ENTITY_ID
    )
    assert selected_proposal_payload["payload"]["proposed_object"] == (
        _GRAPH_CHAT_SUGGESTION_TARGET_ID
    )

    chat_artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{payload['chat']['run']['id']}/artifacts",
        headers=_auth_headers(role="viewer"),
    )
    assert chat_artifacts_response.status_code == 200
    chat_artifact_keys = {
        artifact["key"] for artifact in chat_artifacts_response.json()["artifacts"]
    }
    assert "graph_write_proposals" in chat_artifact_keys

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{payload['run']['id']}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    assert workspace_response.status_code == 200
    workspace_payload = workspace_response.json()
    assert workspace_payload["snapshot"]["curation_source"] == "chat_graph_write"
    assert workspace_payload["snapshot"]["chat_graph_write_proposal_ids"] == (
        payload["chat_graph_write_proposal_ids"]
    )


def test_supervisor_can_directly_review_briefing_chat_candidate() -> None:
    """Supervisor runs should promote briefing-chat candidates without child curation."""
    client = _build_client()
    space_id = str(uuid4())
    seed_entity_id = "11111111-1111-1111-1111-111111111111"

    create_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "include_curation": False,
        },
        headers=_auth_headers(),
    )

    assert create_response.status_code == 201
    create_payload = create_response.json()
    supervisor_run_id = create_payload["run"]["id"]
    chat_run_id = create_payload["chat"]["run"]["id"]
    chat_session_id = create_payload["chat"]["session"]["id"]

    review_response = client.post(
        (
            f"/v1/spaces/{space_id}/agents/supervisor/runs/{supervisor_run_id}/"
            "chat-graph-write-candidates/0/review"
        ),
        json={"decision": "promote", "reason": "Promote directly from supervisor."},
        headers=_auth_headers(),
    )

    assert review_response.status_code == 200
    payload = review_response.json()
    assert payload["run"]["id"] == supervisor_run_id
    assert payload["chat_run_id"] == chat_run_id
    assert payload["chat_session_id"] == chat_session_id
    assert payload["candidate_index"] == 0
    assert payload["candidate"]["target_entity_id"] == _GRAPH_CHAT_SUGGESTION_TARGET_ID
    assert payload["proposal"]["status"] == "promoted"
    assert payload["proposal"]["metadata"]["graph_claim_id"] is not None
    assert payload["proposal"]["metadata"]["supervisor_run_id"] == supervisor_run_id
    assert payload["chat_graph_write_review_count"] == 1
    assert len(payload["chat_graph_write_reviews"]) == 1
    assert payload["latest_chat_graph_write_review"]["reviewed_at"] is not None
    assert payload["latest_chat_graph_write_review"]["candidate_index"] == 0
    assert payload["latest_chat_graph_write_review"]["proposal_status"] == "promoted"

    proposals_response = client.get(
        f"/v1/spaces/{space_id}/proposals",
        params={"run_id": chat_run_id},
        headers=_auth_headers(role="viewer"),
    )
    assert proposals_response.status_code == 200
    proposals_payload = proposals_response.json()
    assert proposals_payload["total"] == 1
    assert proposals_payload["proposals"][0]["status"] == "promoted"

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{supervisor_run_id}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    assert workspace_response.status_code == 200
    workspace_payload = workspace_response.json()["snapshot"]
    assert workspace_payload["last_supervisor_chat_graph_write_candidate_index"] == 0
    assert workspace_payload["last_supervisor_chat_graph_write_candidate_decision"] == (
        "promote"
    )
    assert (
        workspace_payload["last_supervisor_chat_graph_write_chat_run_id"] == chat_run_id
    )
    assert workspace_payload["last_supervisor_chat_graph_write_chat_session_id"] == (
        chat_session_id
    )
    assert (
        workspace_payload["last_supervisor_chat_graph_write_graph_claim_id"] is not None
    )
    assert workspace_payload["last_supervisor_chat_graph_write_review_key"] == (
        "supervisor_chat_graph_write_review"
    )

    summary_response = client.get(
        f"/v1/spaces/{space_id}/runs/{supervisor_run_id}/artifacts/supervisor_summary",
        headers=_auth_headers(role="viewer"),
    )
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()["content"]
    assert summary_payload["completed_at"] is not None
    assert summary_payload["chat_graph_write_review_count"] == 1
    assert len(summary_payload["chat_graph_write_reviews"]) == 1
    assert summary_payload["latest_chat_graph_write_review"]["reviewed_at"] is not None
    assert summary_payload["latest_chat_graph_write_review"]["candidate_index"] == 0
    assert (
        summary_payload["latest_chat_graph_write_review"]["proposal_status"]
        == "promoted"
    )
    assert (
        summary_payload["latest_chat_graph_write_review"]["graph_claim_id"] is not None
    )
    assert summary_payload["steps"][-1]["step"] == "chat_graph_write_review"
    assert summary_payload["steps"][-1]["status"] == "completed"

    detail_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs/{supervisor_run_id}",
        headers=_auth_headers(role="viewer"),
    )
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert (
        detail_payload["bootstrap"]["run"]["id"]
        == create_payload["bootstrap"]["run"]["id"]
    )
    assert detail_payload["chat"]["run"]["id"] == chat_run_id
    assert detail_payload["curation"] is None
    assert detail_payload["artifact_keys"]["curation"] is None
    assert detail_payload["completed_at"] is not None
    assert detail_payload["chat_graph_write_review_count"] == 1
    assert len(detail_payload["chat_graph_write_reviews"]) == 1
    assert detail_payload["latest_chat_graph_write_review"]["reviewed_at"] is not None
    assert detail_payload["latest_chat_graph_write_review"]["candidate_index"] == 0
    assert detail_payload["latest_chat_graph_write_review"]["proposal_status"] == (
        "promoted"
    )
    assert detail_payload["curation_run_id"] is None
    assert detail_payload["curation_status"] is None
    assert detail_payload["progress"]["status"] == "completed"


def test_supervisor_summary_accumulates_direct_chat_review_history() -> None:
    """Supervisor summary should keep direct briefing-chat review history."""
    client = _build_client(
        graph_chat_runner_dependency=_FakeMultiEvidenceGraphChatRunner,
        graph_api_gateway_dependency=_FakeRankedSuggestionGraphApiGateway,
    )
    space_id = str(uuid4())
    seed_entity_id = "11111111-1111-1111-1111-111111111111"

    create_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "include_curation": False,
        },
        headers=_auth_headers(),
    )

    assert create_response.status_code == 201
    supervisor_run_id = create_response.json()["run"]["id"]

    first_review_response = client.post(
        (
            f"/v1/spaces/{space_id}/agents/supervisor/runs/{supervisor_run_id}/"
            "chat-graph-write-candidates/0/review"
        ),
        json={"decision": "promote", "reason": "Promote the top suggestion."},
        headers=_auth_headers(),
    )
    assert first_review_response.status_code == 200

    second_review_response = client.post(
        (
            f"/v1/spaces/{space_id}/agents/supervisor/runs/{supervisor_run_id}/"
            "chat-graph-write-candidates/1/review"
        ),
        json={"decision": "reject", "reason": "Reject the second suggestion."},
        headers=_auth_headers(),
    )
    assert second_review_response.status_code == 200
    second_review_payload = second_review_response.json()
    assert second_review_payload["chat_graph_write_review_count"] == 2
    assert len(second_review_payload["chat_graph_write_reviews"]) == 2
    assert (
        second_review_payload["latest_chat_graph_write_review"]["reviewed_at"]
        is not None
    )
    assert (
        second_review_payload["latest_chat_graph_write_review"]["candidate_index"] == 1
    )
    assert second_review_payload["latest_chat_graph_write_review"][
        "proposal_status"
    ] == ("rejected")

    summary_response = client.get(
        f"/v1/spaces/{space_id}/runs/{supervisor_run_id}/artifacts/supervisor_summary",
        headers=_auth_headers(role="viewer"),
    )
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()["content"]
    assert summary_payload["chat_graph_write_review_count"] == 2
    assert len(summary_payload["chat_graph_write_reviews"]) == 2
    assert summary_payload["chat_graph_write_reviews"][0]["reviewed_at"] is not None
    assert summary_payload["chat_graph_write_reviews"][1]["reviewed_at"] is not None
    assert (
        summary_payload["chat_graph_write_reviews"][0]["decision_status"] == "promoted"
    )
    assert (
        summary_payload["chat_graph_write_reviews"][1]["decision_status"] == "rejected"
    )
    assert summary_payload["latest_chat_graph_write_review"]["candidate_index"] == 1
    assert (
        summary_payload["latest_chat_graph_write_review"]["proposal_status"]
        == "rejected"
    )
    assert summary_payload["steps"][-1]["step"] == "chat_graph_write_review"
    assert (
        "Latest decision: rejected candidate 1."
        in summary_payload["steps"][-1]["detail"]
    )


def test_supervisor_chat_candidate_review_blocks_when_child_curation_owns_chat_candidates() -> (
    None
):
    """Supervisor direct review should block once chat-derived candidates are delegated."""
    client = _build_client()
    space_id = str(uuid4())
    seed_entity_id = "11111111-1111-1111-1111-111111111111"

    create_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "curation_source": "chat_graph_write",
        },
        headers=_auth_headers(),
    )

    assert create_response.status_code == 201
    supervisor_run_id = create_response.json()["run"]["id"]

    review_response = client.post(
        (
            f"/v1/spaces/{space_id}/agents/supervisor/runs/{supervisor_run_id}/"
            "chat-graph-write-candidates/0/review"
        ),
        json={"decision": "reject", "reason": "Do not bypass child curation."},
        headers=_auth_headers(),
    )

    assert review_response.status_code == 409
    assert (
        "already delegated chat graph-write review" in review_response.json()["detail"]
    )


def test_supervisor_run_completes_after_child_curation_resume() -> None:
    """Supervisor resume should reconcile the child curation run and complete the parent."""
    client = _build_client()
    space_id = str(uuid4())
    seed_entity_id = "11111111-1111-1111-1111-111111111111"

    create_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
        },
        headers=_auth_headers(),
    )
    assert create_response.status_code == 201
    create_payload = create_response.json()
    supervisor_run_id = create_payload["run"]["id"]
    curation_run_id = create_payload["curation"]["run"]["id"]
    proposal_id = create_payload["selected_curation_proposal_ids"][0]

    approvals_response = client.get(
        f"/v1/spaces/{space_id}/runs/{curation_run_id}/approvals",
        headers=_auth_headers(role="viewer"),
    )
    assert approvals_response.status_code == 200
    approval_key = approvals_response.json()["approvals"][0]["approval_key"]

    approve_response = client.post(
        f"/v1/spaces/{space_id}/runs/{curation_run_id}/approvals/{approval_key}",
        json={"decision": "approved", "reason": "Promote through supervisor."},
        headers=_auth_headers(),
    )
    assert approve_response.status_code == 200

    resume_response = client.post(
        f"/v1/spaces/{space_id}/runs/{supervisor_run_id}/resume",
        json={"reason": "Child approvals resolved"},
        headers=_auth_headers(),
    )

    assert resume_response.status_code == 200
    resume_payload = resume_response.json()
    assert resume_payload["run"]["status"] == "completed"
    assert resume_payload["progress"]["phase"] == "completed"
    assert (
        resume_payload["progress"]["metadata"]["child_curation_run_id"]
        == curation_run_id
    )
    assert resume_payload["progress"]["metadata"]["promoted_count"] == 1
    assert resume_payload["progress"]["metadata"]["rejected_count"] == 0

    parent_workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{supervisor_run_id}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    assert parent_workspace_response.status_code == 200
    parent_workspace_payload = parent_workspace_response.json()
    assert parent_workspace_payload["snapshot"]["status"] == "completed"
    assert parent_workspace_payload["snapshot"]["curation_run_id"] == curation_run_id
    assert parent_workspace_payload["snapshot"]["last_child_curation_summary_key"] == (
        "curation_summary"
    )
    assert parent_workspace_payload["snapshot"]["last_child_curation_actions_key"] == (
        "curation_actions"
    )

    parent_artifact_response = client.get(
        f"/v1/spaces/{space_id}/runs/{supervisor_run_id}/artifacts/supervisor_summary",
        headers=_auth_headers(role="viewer"),
    )
    assert parent_artifact_response.status_code == 200
    parent_summary = parent_artifact_response.json()["content"]
    assert parent_summary["curation_status"] == "completed"
    assert parent_summary["curation_summary"]["promoted_count"] == 1
    assert parent_summary["steps"][-1]["status"] == "completed"

    detail_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs/{supervisor_run_id}",
        headers=_auth_headers(role="viewer"),
    )
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["run"]["status"] == "completed"
    assert detail_payload["progress"]["phase"] == "completed"
    assert (
        detail_payload["bootstrap"]["run"]["id"]
        == create_payload["bootstrap"]["run"]["id"]
    )
    assert detail_payload["chat"]["run"]["id"] == create_payload["chat"]["run"]["id"]
    assert detail_payload["curation"]["run"]["id"] == curation_run_id
    assert detail_payload["curation"]["run"]["status"] == "completed"
    assert detail_payload["curation"]["pending_approval_count"] == 0
    assert detail_payload["artifact_keys"]["curation"]["curation_summary"] == (
        "curation_summary"
    )
    assert detail_payload["artifact_keys"]["curation"]["curation_actions"] == (
        "curation_actions"
    )
    assert detail_payload["curation_run_id"] == curation_run_id
    assert detail_payload["curation_status"] == "completed"
    assert detail_payload["curation_summary"]["promoted_count"] == 1
    assert detail_payload["curation_summary"]["applied_proposal_ids"] == [proposal_id]

    capabilities_response = client.get(
        f"/v1/spaces/{space_id}/runs/{supervisor_run_id}/capabilities",
        headers=_auth_headers(role="viewer"),
    )
    assert capabilities_response.status_code == 200
    capabilities_payload = capabilities_response.json()
    assert capabilities_payload["active_skill_names"] == [
        "graph_harness.supervisor_coordination",
        "graph_harness.graph_grounding",
        "graph_harness.relation_discovery",
        "graph_harness.graph_write_review",
        "graph_harness.claim_validation",
        "graph_harness.governed_graph_write",
    ]

    policy_response = client.get(
        f"/v1/spaces/{space_id}/runs/{supervisor_run_id}/policy-decisions",
        headers=_auth_headers(role="viewer"),
    )
    assert policy_response.status_code == 200
    policy_payload = policy_response.json()
    assert policy_payload["summary"]["tool_record_count"] == 0
    assert policy_payload["summary"]["manual_review_count"] == 0
    assert policy_payload["summary"]["skill_record_count"] == 7
    assert detail_payload["curation_actions"]["action_count"] == 1
    assert (
        detail_payload["curation_actions"]["actions"][0]["proposal_id"] == proposal_id
    )
    assert detail_payload["steps"][-1]["status"] == "completed"

    curation_run_response = client.get(
        f"/v1/spaces/{space_id}/runs/{curation_run_id}",
        headers=_auth_headers(role="viewer"),
    )
    assert curation_run_response.status_code == 200
    assert curation_run_response.json()["status"] == "completed"

    proposal_response = client.get(
        f"/v1/spaces/{space_id}/proposals/{proposal_id}",
        headers=_auth_headers(role="viewer"),
    )
    assert proposal_response.status_code == 200
    assert proposal_response.json()["status"] == "promoted"


def test_create_and_list_runs_returns_queued_run() -> None:
    """Creating a run should validate graph health and store queued metadata."""
    client = _build_client()
    space_id = str(uuid4())

    create_response = client.post(
        f"/v1/spaces/{space_id}/runs",
        json={
            "harness_id": "graph-chat",
            "title": "Ask about MED13",
            "input_payload": {"question": "What is already known?"},
        },
        headers=_auth_headers(),
    )

    assert create_response.status_code == 201
    created_payload = create_response.json()
    assert created_payload["space_id"] == space_id
    assert created_payload["status"] == "queued"
    assert created_payload["graph_service_version"] == "test-graph"

    list_response = client.get(
        f"/v1/spaces/{space_id}/runs",
        headers=_auth_headers(role="viewer"),
    )

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["runs"][0]["id"] == created_payload["id"]

    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{created_payload['id']}/artifacts",
        headers=_auth_headers(role="viewer"),
    )

    assert artifacts_response.status_code == 200
    artifacts_payload = artifacts_response.json()
    assert artifacts_payload["total"] == 3
    assert artifacts_payload["artifacts"][0]["key"] == "run_manifest"

    artifact_response = client.get(
        f"/v1/spaces/{space_id}/runs/{created_payload['id']}/artifacts/run_manifest",
        headers=_auth_headers(role="viewer"),
    )

    assert artifact_response.status_code == 200
    artifact_payload = artifact_response.json()
    assert artifact_payload["content"]["run_id"] == created_payload["id"]

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{created_payload['id']}/workspace",
        headers=_auth_headers(role="viewer"),
    )

    assert workspace_response.status_code == 200
    workspace_payload = workspace_response.json()
    assert workspace_payload["snapshot"]["run_id"] == created_payload["id"]
    assert workspace_payload["snapshot"]["artifact_keys"] == [
        "run_manifest",
        "run_capabilities",
        "policy_decisions",
    ]

    progress_response = client.get(
        f"/v1/spaces/{space_id}/runs/{created_payload['id']}/progress",
        headers=_auth_headers(role="viewer"),
    )

    assert progress_response.status_code == 200
    progress_payload = progress_response.json()
    assert progress_payload["status"] == "queued"
    assert progress_payload["phase"] == "queued"
    assert progress_payload["progress_percent"] == 0.0

    events_response = client.get(
        f"/v1/spaces/{space_id}/runs/{created_payload['id']}/events",
        headers=_auth_headers(role="viewer"),
    )

    assert events_response.status_code == 200
    events_payload = events_response.json()
    assert events_payload["total"] == 1
    assert events_payload["events"][0]["event_type"] == "run.created"


def test_run_transparency_endpoints_expose_capabilities_and_tool_decisions() -> None:
    """Capabilities and policy decisions should expose declared and observed tools."""
    client = _build_client(graph_chat_runner_dependency=_FakeNeedsReviewGraphChatRunner)
    space_id = str(uuid4())

    session_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions",
        json={},
        headers=_auth_headers(),
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    chat_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages",
        json={"content": "What does the graph say about MED13?"},
        headers=_auth_headers(),
    )
    assert chat_response.status_code == 201
    run_id = chat_response.json()["run"]["id"]

    capabilities_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/capabilities",
        headers=_auth_headers(role="viewer"),
    )
    assert capabilities_response.status_code == 200
    capabilities_payload = capabilities_response.json()
    assert capabilities_payload["artifact_key"] == "run_capabilities"
    assert capabilities_payload["harness_id"] == "graph-chat"
    assert capabilities_payload["preloaded_skill_names"] == [
        "graph_harness.graph_grounding",
        "graph_harness.graph_write_review",
    ]
    assert capabilities_payload["allowed_skill_names"] == [
        "graph_harness.graph_grounding",
        "graph_harness.graph_write_review",
        "graph_harness.literature_refresh",
        "graph_harness.relation_discovery",
    ]
    assert capabilities_payload["active_skill_names"] == [
        "graph_harness.graph_grounding",
        "graph_harness.graph_write_review",
        "graph_harness.literature_refresh",
    ]
    visible_tool_names = {
        tool["tool_name"] for tool in capabilities_payload["visible_tools"]
    }
    filtered_tool_names = {
        tool["tool_name"] for tool in capabilities_payload["filtered_tools"]
    }
    assert "run_pubmed_search" in visible_tool_names
    assert "suggest_relations" in visible_tool_names
    assert "create_graph_claim" in filtered_tool_names

    policy_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/policy-decisions",
        headers=_auth_headers(role="viewer"),
    )
    assert policy_response.status_code == 200
    policy_payload = policy_response.json()
    assert policy_payload["artifact_key"] == "policy_decisions"
    assert policy_payload["summary"]["tool_record_count"] == 1
    assert policy_payload["summary"]["manual_review_count"] == 0
    assert policy_payload["summary"]["skill_record_count"] == 3
    assert {record["decision_source"] for record in policy_payload["records"]} == {
        "skill",
        "tool",
    }
    tool_records = [
        record
        for record in policy_payload["records"]
        if record["decision_source"] == "tool"
    ]
    assert len(tool_records) == 1
    assert tool_records[0]["tool_name"] == "run_pubmed_search"
    assert tool_records[0]["status"] == "success"


def test_create_run_rejects_unknown_harness() -> None:
    """Run creation should fail fast for unknown harness ids."""
    client = _build_client()

    response = client.post(
        f"/v1/spaces/{uuid4()}/runs",
        json={"harness_id": "unknown-harness"},
        headers=_auth_headers(),
    )

    assert response.status_code == 400


def test_get_missing_run_returns_not_found() -> None:
    """Fetching a missing run should return 404."""
    client = _build_client()

    response = client.get(
        f"/v1/spaces/{uuid4()}/runs/{uuid4()}",
        headers=_auth_headers(role="viewer"),
    )

    assert response.status_code == 404


def test_get_missing_artifact_returns_not_found() -> None:
    """Fetching a missing artifact should return 404."""
    client = _build_client()
    space_id = str(uuid4())
    create_response = client.post(
        f"/v1/spaces/{space_id}/runs",
        json={"harness_id": "graph-chat"},
        headers=_auth_headers(),
    )
    run_id = create_response.json()["id"]

    response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/artifacts/missing-artifact",
        headers=_auth_headers(role="viewer"),
    )

    assert response.status_code == 404


def test_record_intent_and_decide_approval() -> None:
    """Intent recording should create approvals that can be decided later."""
    client = _build_client()
    space_id = str(uuid4())
    create_response = client.post(
        f"/v1/spaces/{space_id}/runs",
        json={"harness_id": "claim-curation"},
        headers=_auth_headers(),
    )
    run_id = create_response.json()["id"]

    intent_response = client.post(
        f"/v1/spaces/{space_id}/runs/{run_id}/intent",
        json={
            "summary": "Review two proposed graph writes",
            "proposed_actions": [
                {
                    "approval_key": "promote-claim-1",
                    "title": "Promote claim candidate",
                    "risk_level": "high",
                    "target_type": "claim",
                    "target_id": "claim-1",
                    "requires_approval": True,
                    "metadata": {"origin": "chat"},
                },
                {
                    "approval_key": "draft-report",
                    "title": "Store draft report",
                    "risk_level": "low",
                    "target_type": "artifact",
                    "target_id": "report-1",
                    "requires_approval": False,
                    "metadata": {"origin": "run"},
                },
            ],
        },
        headers=_auth_headers(),
    )

    assert intent_response.status_code == 200
    intent_payload = intent_response.json()
    assert intent_payload["summary"] == "Review two proposed graph writes"
    assert len(intent_payload["proposed_actions"]) == 2

    progress_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/progress",
        headers=_auth_headers(role="viewer"),
    )

    assert progress_response.status_code == 200
    progress_payload = progress_response.json()
    assert progress_payload["status"] == "paused"
    assert progress_payload["phase"] == "approval"
    assert progress_payload["resume_point"] == "approval_gate"

    resume_blocked_response = client.post(
        f"/v1/spaces/{space_id}/runs/{run_id}/resume",
        json={},
        headers=_auth_headers(),
    )

    assert resume_blocked_response.status_code == 409

    approvals_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/approvals",
        headers=_auth_headers(role="viewer"),
    )

    assert approvals_response.status_code == 200
    approvals_payload = approvals_response.json()
    assert approvals_payload["total"] == 1
    assert approvals_payload["approvals"][0]["approval_key"] == "promote-claim-1"
    assert approvals_payload["approvals"][0]["status"] == "pending"

    decision_response = client.post(
        f"/v1/spaces/{space_id}/runs/{run_id}/approvals/promote-claim-1",
        json={"decision": "approved", "reason": "Evidence looks sufficient"},
        headers=_auth_headers(),
    )

    assert decision_response.status_code == 200
    decision_payload = decision_response.json()
    assert decision_payload["status"] == "approved"
    assert decision_payload["decision_reason"] == "Evidence looks sufficient"

    resume_response = client.post(
        f"/v1/spaces/{space_id}/runs/{run_id}/resume",
        json={"reason": "Approvals resolved"},
        headers=_auth_headers(),
    )

    assert resume_response.status_code == 200
    resume_payload = resume_response.json()
    assert resume_payload["run"]["status"] == "queued"
    assert resume_payload["progress"]["phase"] == "queued"
    assert resume_payload["progress"]["resume_point"] is None
    assert (
        resume_payload["progress"]["metadata"]["resume_reason"] == "Approvals resolved"
    )

    events_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/events",
        headers=_auth_headers(role="viewer"),
    )

    assert events_response.status_code == 200
    event_types = [event["event_type"] for event in events_response.json()["events"]]
    assert "run.intent_recorded" in event_types
    assert "run.paused" in event_types
    assert "run.approval_decided" in event_types
    assert "run.resumed" in event_types


def test_decide_missing_approval_returns_not_found() -> None:
    """Missing approvals should return 404."""
    client = _build_client()
    space_id = str(uuid4())
    create_response = client.post(
        f"/v1/spaces/{space_id}/runs",
        json={"harness_id": "claim-curation"},
        headers=_auth_headers(),
    )
    run_id = create_response.json()["id"]

    response = client.post(
        f"/v1/spaces/{space_id}/runs/{run_id}/approvals/missing-key",
        json={"decision": "approved"},
        headers=_auth_headers(),
    )

    assert response.status_code == 404


def test_graph_search_agent_run_completes_and_stores_result_artifact() -> None:
    """Harness-owned graph-search runs should complete and write result artifacts."""
    client = _build_client()
    space_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/graph-search/runs",
        json={
            "question": "What does the graph suggest about MED13 mechanisms?",
            "top_k": 5,
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 201
    payload = response.json()
    run_payload = payload["run"]
    result_payload = payload["result"]
    assert run_payload["harness_id"] == "graph-search"
    assert run_payload["status"] == "completed"
    assert result_payload["decision"] == "generated"
    assert result_payload["agent_run_id"] == "graph_search:test-run"

    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_payload['id']}/artifacts",
        headers=_auth_headers(role="viewer"),
    )
    artifacts_payload = artifacts_response.json()
    artifact_keys = {artifact["key"] for artifact in artifacts_payload["artifacts"]}
    assert "run_manifest" in artifact_keys
    assert "graph_search_result" in artifact_keys

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_payload['id']}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    workspace_payload = workspace_response.json()
    assert workspace_payload["snapshot"]["status"] == "completed"
    assert (
        workspace_payload["snapshot"]["last_graph_search_result_key"]
        == "graph_search_result"
    )


def test_graph_connection_agent_run_completes_and_stores_result_artifact() -> None:
    """Harness-owned graph-connection runs should complete and write result artifacts."""
    client = _build_client()
    space_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/graph-connections/runs",
        json={
            "seed_entity_ids": ["entity-1", "entity-2"],
            "source_type": "pubmed",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 201
    payload = response.json()
    run_payload = payload["run"]
    outcomes_payload = payload["outcomes"]
    assert run_payload["harness_id"] == "graph-connections"
    assert run_payload["status"] == "completed"
    assert len(outcomes_payload) == 2
    assert outcomes_payload[0]["agent_run_id"] == "graph_connection:test-run"

    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_payload['id']}/artifacts",
        headers=_auth_headers(role="viewer"),
    )
    artifacts_payload = artifacts_response.json()
    artifact_keys = {artifact["key"] for artifact in artifacts_payload["artifacts"]}
    assert "run_manifest" in artifact_keys
    assert "graph_connection_result" in artifact_keys

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_payload['id']}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    workspace_payload = workspace_response.json()
    assert workspace_payload["snapshot"]["status"] == "completed"
    assert (
        workspace_payload["snapshot"]["last_graph_connection_result_key"]
        == "graph_connection_result"
    )


def test_graph_chat_session_flow_persists_messages_and_artifacts() -> None:
    """Graph-chat sessions should store transcript state and run artifacts."""
    client = _build_client()
    space_id = str(uuid4())

    create_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions",
        json={},
        headers=_auth_headers(),
    )

    assert create_response.status_code == 201
    created_session = create_response.json()
    assert created_session["title"] == "New Graph Chat"
    session_id = created_session["id"]

    list_response = client.get(
        f"/v1/spaces/{space_id}/chat-sessions",
        headers=_auth_headers(role="viewer"),
    )

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    message_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages",
        json={"content": "What does MED13 do in this graph?"},
        headers=_auth_headers(),
    )

    assert message_response.status_code == 201
    payload = message_response.json()
    run_payload = payload["run"]
    assert run_payload["harness_id"] == "graph-chat"
    assert run_payload["status"] == "completed"
    assert payload["session"]["status"] == "active"
    assert payload["session"]["last_run_id"] == run_payload["id"]
    assert payload["session"]["title"] == "What does MED13 do in this graph?"
    assert payload["user_message"]["role"] == "user"
    assert payload["assistant_message"]["role"] == "assistant"
    assert payload["assistant_message"]["metadata"][
        "grounded_answer_verification_key"
    ] == ("grounded_answer_verification")
    assert (
        payload["assistant_message"]["metadata"]["memory_context_key"]
        == "memory_context"
    )
    assert (
        payload["assistant_message"]["metadata"][
            "graph_write_candidate_suggestions_key"
        ]
        == "graph_write_candidate_suggestions"
    )
    assert payload["result"]["chat_summary"] == (
        "Answered with 1 grounded graph match. Graph-write candidates: 1."
    )
    assert payload["result"]["verification"]["status"] == "verified"
    assert len(payload["result"]["graph_write_candidates"]) == 1
    assert payload["result"]["graph_write_candidates"][0]["source_entity_id"] == (
        _GRAPH_CHAT_EVIDENCE_ENTITY_ID
    )
    assert payload["result"]["graph_write_candidates"][0]["target_entity_id"] == (
        _GRAPH_CHAT_SUGGESTION_TARGET_ID
    )
    assert "Reviewable graph-write candidates:" in payload["result"]["answer_text"]
    assert (
        f"1. MED13 SUGGESTS {_GRAPH_CHAT_SUGGESTION_TARGET_ID} [score"
        in payload["result"]["answer_text"]
    )
    assert payload["result"]["search"]["agent_run_id"] == "graph_chat:test-search"

    detail_response = client.get(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}",
        headers=_auth_headers(role="viewer"),
    )

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["session"]["last_run_id"] == run_payload["id"]
    assert [message["role"] for message in detail_payload["messages"]] == [
        "user",
        "assistant",
    ]

    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_payload['id']}/artifacts",
        headers=_auth_headers(role="viewer"),
    )
    artifacts_payload = artifacts_response.json()
    artifact_keys = {artifact["key"] for artifact in artifacts_payload["artifacts"]}
    assert "run_manifest" in artifact_keys
    assert "grounded_answer_verification" in artifact_keys
    assert "memory_context" in artifact_keys
    assert "graph_write_candidate_suggestions" in artifact_keys
    assert "graph_chat_result" in artifact_keys
    assert "chat_summary" in artifact_keys

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_payload['id']}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    workspace_payload = workspace_response.json()
    assert workspace_payload["snapshot"]["status"] == "completed"
    assert workspace_payload["snapshot"]["chat_session_id"] == session_id
    assert (
        workspace_payload["snapshot"]["last_graph_chat_result_key"]
        == "graph_chat_result"
    )
    assert workspace_payload["snapshot"]["last_chat_summary_key"] == "chat_summary"
    assert (
        workspace_payload["snapshot"]["last_grounded_answer_verification_key"]
        == "grounded_answer_verification"
    )
    assert workspace_payload["snapshot"]["grounded_answer_verification_status"] == (
        "verified"
    )
    assert workspace_payload["snapshot"]["last_memory_context_key"] == "memory_context"
    assert workspace_payload["snapshot"][
        "last_graph_write_candidate_suggestions_key"
    ] == ("graph_write_candidate_suggestions")
    assert workspace_payload["snapshot"]["graph_write_candidate_count"] == 1
    assert workspace_payload["snapshot"]["pending_question_count"] == 0


def test_graph_chat_session_uses_bootstrap_research_memory() -> None:
    """Graph chat should reuse stored research memory from prior bootstrap runs."""
    client = _build_client()
    space_id = str(uuid4())
    seed_entity_id = "11111111-1111-1111-1111-111111111111"

    bootstrap_response = client.post(
        f"/v1/spaces/{space_id}/agents/research-bootstrap/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [seed_entity_id],
            "max_hypotheses": 3,
        },
        headers=_auth_headers(),
    )

    assert bootstrap_response.status_code == 201
    bootstrap_payload = bootstrap_response.json()

    create_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions",
        json={},
        headers=_auth_headers(),
    )
    session_id = create_response.json()["id"]

    message_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages",
        json={"content": "What should we investigate next for MED13?"},
        headers=_auth_headers(),
    )

    assert message_response.status_code == 201
    payload = message_response.json()
    run_id = payload["run"]["id"]
    assert payload["result"]["verification"]["status"] == "verified"
    assert (
        payload["assistant_message"]["metadata"]["memory_context_key"]
        == "memory_context"
    )

    memory_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/artifacts/memory_context",
        headers=_auth_headers(role="viewer"),
    )

    assert memory_response.status_code == 200
    memory_payload = memory_response.json()["content"]
    assert memory_payload["objective"] == "Map MED13 mechanism evidence."
    assert (
        memory_payload["last_graph_snapshot_id"]
        == bootstrap_payload["graph_snapshot"]["id"]
    )
    assert (
        "What should we investigate next for MED13?"
        in memory_payload["explored_questions"]
    )
    assert memory_payload["pending_questions"] == bootstrap_payload["pending_questions"]

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/workspace",
        headers=_auth_headers(role="viewer"),
    )

    assert workspace_response.status_code == 200
    workspace_payload = workspace_response.json()["snapshot"]
    assert workspace_payload["research_objective"] == "Map MED13 mechanism evidence."
    assert workspace_payload["research_state_last_graph_snapshot_id"] == (
        bootstrap_payload["graph_snapshot"]["id"]
    )
    assert workspace_payload["pending_question_count"] == len(
        bootstrap_payload["pending_questions"],
    )


def test_graph_chat_session_ranks_and_caps_graph_write_candidates() -> None:
    """Verified chat runs should surface only the top-ranked graph-write candidates."""
    client = _build_client(
        graph_chat_runner_dependency=_FakeMultiEvidenceGraphChatRunner,
        graph_api_gateway_dependency=_FakeRankedSuggestionGraphApiGateway,
    )
    space_id = str(uuid4())

    create_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions",
        json={},
        headers=_auth_headers(),
    )
    session_id = create_response.json()["id"]

    message_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages",
        json={"content": "Which graph writes should we review next for MED13?"},
        headers=_auth_headers(),
    )

    assert message_response.status_code == 201
    payload = message_response.json()
    candidates = payload["result"]["graph_write_candidates"]
    assert len(candidates) == 3
    assert candidates[0]["target_entity_id"] == _GRAPH_CHAT_SUGGESTION_TARGET_ID
    assert candidates[1]["target_entity_id"] == _GRAPH_CHAT_SECOND_SUGGESTION_TARGET_ID
    assert candidates[2]["target_entity_id"] == _GRAPH_CHAT_THIRD_SUGGESTION_TARGET_ID
    assert candidates[0]["ranking_score"] > candidates[1]["ranking_score"]
    assert candidates[1]["ranking_score"] > candidates[2]["ranking_score"]
    assert candidates[0]["ranking_metadata"]["suggestion_final_score"] == 0.96
    assert candidates[1]["ranking_metadata"]["evidence_relevance"] == 0.88
    assert payload["result"]["chat_summary"] == (
        "Answered with 2 grounded graph matches. Graph-write candidates: 3."
    )
    assert "Reviewable graph-write candidates:" in payload["result"]["answer_text"]
    assert (
        f"1. MED13 SUGGESTS {_GRAPH_CHAT_SUGGESTION_TARGET_ID} [score"
        in payload["result"]["answer_text"]
    )
    assert (
        f"2. CDK8 SUGGESTS {_GRAPH_CHAT_SECOND_SUGGESTION_TARGET_ID} [score"
        in payload["result"]["answer_text"]
    )
    assert (
        f"3. MED13 SUGGESTS {_GRAPH_CHAT_THIRD_SUGGESTION_TARGET_ID} [score"
        in payload["result"]["answer_text"]
    )
    assert (
        _GRAPH_CHAT_FOURTH_SUGGESTION_TARGET_ID not in payload["result"]["answer_text"]
    )

    run_id = payload["run"]["id"]
    artifact_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/artifacts/graph_write_candidate_suggestions",
        headers=_auth_headers(role="viewer"),
    )
    assert artifact_response.status_code == 200
    artifact_payload = artifact_response.json()["content"]
    assert artifact_payload["candidate_count"] == 3
    assert artifact_payload["candidates"][0]["target_entity_id"] == (
        _GRAPH_CHAT_SUGGESTION_TARGET_ID
    )

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    assert workspace_response.status_code == 200
    workspace_payload = workspace_response.json()["snapshot"]
    assert workspace_payload["graph_write_candidate_count"] == 3


def test_chat_graph_write_endpoint_rejects_unverified_chat_result() -> None:
    """Chat graph-write should reject latest answers that failed verification."""
    client = _build_client(graph_chat_runner_dependency=_FakeNeedsReviewGraphChatRunner)
    space_id = str(uuid4())

    session_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions",
        json={},
        headers=_auth_headers(),
    )
    session_id = session_response.json()["id"]

    chat_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages",
        json={"content": "What does the graph say about MED13?"},
        headers=_auth_headers(),
    )
    assert chat_response.status_code == 201
    chat_payload = chat_response.json()
    run_id = chat_payload["run"]["id"]
    assert chat_payload["result"]["verification"]["status"] == "needs_review"
    assert chat_payload["result"]["fresh_literature"]["source"] == "pubmed"
    assert chat_payload["result"]["fresh_literature"]["total_results"] == 5
    assert (
        "Literature refresh: 5 PubMed results."
        in chat_payload["result"]["chat_summary"]
    )
    assert "Fresh literature to review:" in chat_payload["result"]["answer_text"]
    assert "Synthetic PubMed result 1 (pmid-1)" in chat_payload["result"]["answer_text"]

    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/artifacts",
        headers=_auth_headers(role="viewer"),
    )
    artifact_keys = {
        artifact["key"] for artifact in artifacts_response.json()["artifacts"]
    }
    assert "fresh_literature" in artifact_keys

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    workspace_payload = workspace_response.json()["snapshot"]
    assert workspace_payload["last_fresh_literature_key"] == "fresh_literature"
    assert workspace_payload["fresh_literature_result_count"] == 5

    proposal_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/proposals/graph-write",
        json={},
        headers=_auth_headers(),
    )

    assert proposal_response.status_code == 409
    assert (
        "not verified for graph-write proposals" in proposal_response.json()["detail"]
    )


def test_chat_graph_write_endpoint_auto_derives_proposals_from_latest_chat_run() -> (
    None
):
    """Chat graph-write should auto-derive proposals from the latest verified chat run."""
    _FakeSingleDerivationGraphApiGateway.suggest_relations_call_count = 0
    client = _build_client(
        graph_api_gateway_dependency=_FakeSingleDerivationGraphApiGateway,
    )
    space_id = str(uuid4())

    session_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions",
        json={},
        headers=_auth_headers(),
    )
    session_id = session_response.json()["id"]

    chat_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages",
        json={"content": "What does the graph say about MED13?"},
        headers=_auth_headers(),
    )
    assert chat_response.status_code == 201
    chat_payload = chat_response.json()
    run_id = chat_payload["run"]["id"]
    assert len(chat_payload["result"]["graph_write_candidates"]) == 1

    proposal_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/proposals/graph-write",
        json={},
        headers=_auth_headers(),
    )

    assert proposal_response.status_code == 201
    payload = proposal_response.json()
    assert payload["run"]["id"] == run_id
    assert payload["proposal_count"] == 1
    assert payload["proposals"][0]["payload"]["proposed_subject"] == (
        _GRAPH_CHAT_EVIDENCE_ENTITY_ID
    )
    assert payload["proposals"][0]["payload"]["proposed_object"] == (
        _GRAPH_CHAT_SUGGESTION_TARGET_ID
    )
    assert _FakeSingleDerivationGraphApiGateway.suggest_relations_call_count == 1


def test_chat_graph_write_endpoint_stages_proposals_from_latest_chat_run() -> None:
    """Chat graph-write endpoint should convert the latest chat findings into proposals."""
    client = _build_client()
    space_id = str(uuid4())
    source_entity_id = str(uuid4())
    target_entity_id = str(uuid4())

    session_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions",
        json={},
        headers=_auth_headers(),
    )
    session_id = session_response.json()["id"]

    chat_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages",
        json={"content": "What does the graph say about MED13?"},
        headers=_auth_headers(),
    )
    assert chat_response.status_code == 201
    run_id = chat_response.json()["run"]["id"]

    proposal_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/proposals/graph-write",
        json={
            "candidates": [
                {
                    "source_entity_id": source_entity_id,
                    "relation_type": "SUGGESTS",
                    "target_entity_id": target_entity_id,
                    "evidence_entity_ids": [_GRAPH_CHAT_EVIDENCE_ENTITY_ID],
                },
            ],
        },
        headers=_auth_headers(),
    )

    assert proposal_response.status_code == 201
    payload = proposal_response.json()
    assert payload["run"]["id"] == run_id
    assert payload["session"]["id"] == session_id
    assert payload["proposal_count"] == 1
    assert payload["proposals"][0]["proposal_type"] == "candidate_claim"
    assert payload["proposals"][0]["status"] == "pending_review"
    assert payload["proposals"][0]["payload"]["proposed_subject"] == source_entity_id
    assert payload["proposals"][0]["payload"]["proposed_object"] == target_entity_id

    proposals_response = client.get(
        f"/v1/spaces/{space_id}/proposals",
        params={"run_id": run_id},
        headers=_auth_headers(role="viewer"),
    )
    proposals_payload = proposals_response.json()
    assert proposals_payload["total"] == 1
    assert proposals_payload["proposals"][0]["source_kind"] == "chat_graph_write"

    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/artifacts",
        headers=_auth_headers(role="viewer"),
    )
    artifact_keys = {
        artifact["key"] for artifact in artifacts_response.json()["artifacts"]
    }
    assert "graph_write_proposals" in artifact_keys

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    workspace_payload = workspace_response.json()
    assert workspace_payload["snapshot"]["last_graph_write_proposals_key"] == (
        "graph_write_proposals"
    )
    assert workspace_payload["snapshot"]["chat_graph_write_proposal_count"] == 1
    assert workspace_payload["snapshot"]["proposal_counts"] == {
        "pending_review": 1,
        "promoted": 0,
        "rejected": 0,
    }


def test_chat_graph_write_candidate_review_promotes_inline_candidate() -> None:
    """Chat sessions should promote one inline graph-write candidate directly."""
    client = _build_client()
    space_id = str(uuid4())

    session_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions",
        json={},
        headers=_auth_headers(),
    )
    session_id = session_response.json()["id"]

    chat_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages",
        json={"content": "What does the graph say about MED13?"},
        headers=_auth_headers(),
    )
    assert chat_response.status_code == 201
    run_id = chat_response.json()["run"]["id"]

    review_response = client.post(
        (
            f"/v1/spaces/{space_id}/chat-sessions/{session_id}/"
            "graph-write-candidates/0/review"
        ),
        json={"decision": "promote", "reason": "Promote directly from chat."},
        headers=_auth_headers(),
    )

    assert review_response.status_code == 200
    payload = review_response.json()
    assert payload["run"]["id"] == run_id
    assert payload["candidate_index"] == 0
    assert payload["candidate"]["target_entity_id"] == _GRAPH_CHAT_SUGGESTION_TARGET_ID
    assert payload["proposal"]["status"] == "promoted"
    assert payload["proposal"]["metadata"]["graph_claim_id"] is not None
    assert payload["proposal"]["metadata"]["chat_candidate_index"] == 0

    proposals_response = client.get(
        f"/v1/spaces/{space_id}/proposals",
        params={"run_id": run_id},
        headers=_auth_headers(role="viewer"),
    )
    assert proposals_response.status_code == 200
    proposals_payload = proposals_response.json()
    assert proposals_payload["total"] == 1
    assert proposals_payload["proposals"][0]["status"] == "promoted"

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    assert workspace_response.status_code == 200
    workspace_payload = workspace_response.json()["snapshot"]
    assert workspace_payload["last_chat_graph_write_candidate_index"] == 0
    assert workspace_payload["last_chat_graph_write_candidate_decision"] == "promote"
    assert workspace_payload["last_promoted_graph_claim_id"] is not None
    assert workspace_payload["proposal_counts"] == {
        "pending_review": 0,
        "promoted": 1,
        "rejected": 0,
    }


def test_chat_graph_write_candidate_review_reuses_pending_proposal_for_rejection() -> (
    None
):
    """Direct chat candidate review should reuse an existing staged pending proposal."""
    client = _build_client()
    space_id = str(uuid4())

    session_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions",
        json={},
        headers=_auth_headers(),
    )
    session_id = session_response.json()["id"]

    chat_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages",
        json={"content": "What does the graph say about MED13?"},
        headers=_auth_headers(),
    )
    assert chat_response.status_code == 201
    run_id = chat_response.json()["run"]["id"]

    staged_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/proposals/graph-write",
        json={},
        headers=_auth_headers(),
    )
    assert staged_response.status_code == 201
    staged_payload = staged_response.json()
    assert staged_payload["proposal_count"] == 1
    staged_proposal_id = staged_payload["proposals"][0]["id"]

    review_response = client.post(
        (
            f"/v1/spaces/{space_id}/chat-sessions/{session_id}/"
            "graph-write-candidates/0/review"
        ),
        json={"decision": "reject", "reason": "Reject directly from chat."},
        headers=_auth_headers(),
    )

    assert review_response.status_code == 200
    payload = review_response.json()
    assert payload["proposal"]["id"] == staged_proposal_id
    assert payload["proposal"]["status"] == "rejected"
    assert payload["proposal"]["metadata"]["chat_candidate_index"] == 0

    proposals_response = client.get(
        f"/v1/spaces/{space_id}/proposals",
        params={"run_id": run_id},
        headers=_auth_headers(role="viewer"),
    )
    assert proposals_response.status_code == 200
    proposals_payload = proposals_response.json()
    assert proposals_payload["total"] == 1
    assert proposals_payload["proposals"][0]["id"] == staged_proposal_id
    assert proposals_payload["proposals"][0]["status"] == "rejected"

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    assert workspace_response.status_code == 200
    workspace_payload = workspace_response.json()["snapshot"]
    assert workspace_payload["last_chat_graph_write_candidate_index"] == 0
    assert workspace_payload["last_chat_graph_write_candidate_decision"] == "reject"
    assert workspace_payload["proposal_counts"] == {
        "pending_review": 0,
        "promoted": 0,
        "rejected": 1,
    }


def test_chat_candidate_review_is_reflected_in_policy_decisions() -> None:
    """Direct chat review should append a manual-review trace record to the source run."""
    client = _build_client()
    space_id = str(uuid4())

    session_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions",
        json={},
        headers=_auth_headers(),
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    chat_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages",
        json={"content": "What does the graph say about MED13?"},
        headers=_auth_headers(),
    )
    assert chat_response.status_code == 201
    run_id = chat_response.json()["run"]["id"]

    review_response = client.post(
        (
            f"/v1/spaces/{space_id}/chat-sessions/{session_id}/"
            "graph-write-candidates/0/review"
        ),
        json={"decision": "promote", "reason": "Grounded evidence is sufficient"},
        headers=_auth_headers(),
    )
    assert review_response.status_code == 200

    policy_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/policy-decisions",
        headers=_auth_headers(role="viewer"),
    )
    assert policy_response.status_code == 200
    policy_payload = policy_response.json()
    assert policy_payload["summary"]["manual_review_count"] == 1
    manual_records = [
        record
        for record in policy_payload["records"]
        if record["decision_source"] == "manual_review"
    ]
    assert len(manual_records) == 1
    assert manual_records[0]["tool_name"] == "create_graph_claim"
    assert manual_records[0]["decision"] == "promote"
    assert manual_records[0]["artifact_key"] == "graph_write_candidate_suggestions"


def test_chat_graph_write_endpoint_returns_zero_proposals_when_no_suggestions_exist() -> (
    None
):
    """Chat graph-write auto-derivation should succeed cleanly when no suggestions exist."""
    client = _build_client(
        graph_api_gateway_dependency=_FakeNoSuggestionGraphApiGateway,
    )
    space_id = str(uuid4())

    session_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions",
        json={},
        headers=_auth_headers(),
    )
    session_id = session_response.json()["id"]

    chat_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages",
        json={"content": "What does the graph say about MED13?"},
        headers=_auth_headers(),
    )
    assert chat_response.status_code == 201
    chat_payload = chat_response.json()
    run_id = chat_payload["run"]["id"]
    assert chat_payload["result"]["graph_write_candidates"] == []
    assert (
        "Reviewable graph-write candidates:"
        not in chat_payload["result"]["answer_text"]
    )

    proposal_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/proposals/graph-write",
        json={},
        headers=_auth_headers(),
    )

    assert proposal_response.status_code == 201
    payload = proposal_response.json()
    assert payload["run"]["id"] == run_id
    assert payload["proposal_count"] == 0
    assert payload["proposals"] == []

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    workspace_payload = workspace_response.json()
    assert workspace_payload["snapshot"]["chat_graph_write_proposal_count"] == 0
    assert workspace_payload["snapshot"]["graph_write_candidate_count"] == 0


def test_continuous_learning_run_completes_and_stages_net_new_proposals() -> None:
    """Continuous-learning runs should write cycle artifacts and stage proposals."""
    client = _build_client()
    space_id = str(uuid4())
    first_seed_id = str(uuid4())
    second_seed_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/continuous-learning/runs",
        json={
            "seed_entity_ids": [first_seed_id, second_seed_id],
            "source_type": "pubmed",
            "max_new_proposals": 5,
            "max_next_questions": 3,
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 201
    payload = response.json()
    run_payload = payload["run"]
    assert run_payload["harness_id"] == "continuous-learning"
    assert run_payload["status"] == "completed"
    assert payload["candidate_count"] == 2
    assert payload["proposal_count"] == 2
    assert payload["delta_report"]["new_candidate_count"] == 2
    assert payload["delta_report"]["already_reviewed_candidate_count"] == 0
    assert len(payload["next_questions"]) == 2
    assert payload["run_budget"]["max_tool_calls"] == 100
    assert payload["budget_status"]["status"] == "completed"
    assert payload["budget_status"]["usage"]["tool_calls"] == 2
    assert payload["budget_status"]["usage"]["new_proposals"] == 2

    proposals_response = client.get(
        f"/v1/spaces/{space_id}/proposals",
        params={"run_id": run_payload["id"]},
        headers=_auth_headers(role="viewer"),
    )
    assert proposals_response.status_code == 200
    proposals_payload = proposals_response.json()
    assert proposals_payload["total"] == 2
    assert all(
        proposal["source_kind"] == "continuous_learning_run"
        for proposal in proposals_payload["proposals"]
    )

    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_payload['id']}/artifacts",
        headers=_auth_headers(role="viewer"),
    )
    artifact_keys = {
        artifact["key"] for artifact in artifacts_response.json()["artifacts"]
    }
    assert "delta_report" in artifact_keys
    assert "new_paper_list" in artifact_keys
    assert "candidate_claims" in artifact_keys
    assert "next_questions" in artifact_keys
    assert "graph_context_snapshot" in artifact_keys
    assert "research_state_snapshot" in artifact_keys
    assert "run_budget" in artifact_keys
    assert "budget_status" in artifact_keys

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_payload['id']}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    workspace_payload = workspace_response.json()
    assert workspace_payload["snapshot"]["last_delta_report_key"] == "delta_report"
    assert workspace_payload["snapshot"]["last_candidate_claims_key"] == (
        "candidate_claims"
    )
    assert workspace_payload["snapshot"]["last_graph_context_snapshot_key"] == (
        "graph_context_snapshot"
    )
    assert workspace_payload["snapshot"]["last_research_state_snapshot_key"] == (
        "research_state_snapshot"
    )
    assert workspace_payload["snapshot"]["last_graph_snapshot_id"] is not None
    assert workspace_payload["snapshot"]["budget_status"]["status"] == "completed"
    assert workspace_payload["snapshot"]["proposal_counts"] == {
        "pending_review": 2,
        "promoted": 0,
        "rejected": 0,
    }


def test_continuous_learning_run_reuses_bootstrap_memory_context() -> None:
    """Continuous learning should carry forward stored research memory and refresh it."""
    client = _build_client()
    space_id = str(uuid4())
    first_seed_id = str(uuid4())
    second_seed_id = str(uuid4())

    bootstrap_response = client.post(
        f"/v1/spaces/{space_id}/agents/research-bootstrap/runs",
        json={
            "objective": "Map MED13 mechanism evidence.",
            "seed_entity_ids": [first_seed_id],
            "max_hypotheses": 3,
        },
        headers=_auth_headers(),
    )

    assert bootstrap_response.status_code == 201
    bootstrap_payload = bootstrap_response.json()

    response = client.post(
        f"/v1/spaces/{space_id}/agents/continuous-learning/runs",
        json={
            "seed_entity_ids": [first_seed_id, second_seed_id],
            "source_type": "pubmed",
            "max_new_proposals": 5,
            "max_next_questions": 3,
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 201
    payload = response.json()
    run_payload = payload["run"]
    assert payload["delta_report"]["previous_graph_snapshot_id"] == (
        bootstrap_payload["graph_snapshot"]["id"]
    )
    assert payload["delta_report"]["research_objective"] == (
        "Map MED13 mechanism evidence."
    )
    assert payload["delta_report"]["carried_forward_pending_question_count"] == len(
        bootstrap_payload["pending_questions"],
    )
    assert len(payload["next_questions"]) == 3

    graph_snapshot_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_payload['id']}/artifacts/graph_context_snapshot",
        headers=_auth_headers(role="viewer"),
    )
    assert graph_snapshot_response.status_code == 200
    graph_snapshot_payload = graph_snapshot_response.json()["content"]
    assert (
        graph_snapshot_payload["snapshot_id"]
        != bootstrap_payload["graph_snapshot"]["id"]
    )
    assert (
        graph_snapshot_payload["summary"]["objective"]
        == "Map MED13 mechanism evidence."
    )

    research_state_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_payload['id']}/artifacts/research_state_snapshot",
        headers=_auth_headers(role="viewer"),
    )
    assert research_state_response.status_code == 200
    research_state_payload = research_state_response.json()["content"]
    assert research_state_payload["objective"] == "Map MED13 mechanism evidence."
    assert (
        research_state_payload["last_graph_snapshot_id"]
        == graph_snapshot_payload["snapshot_id"]
    )
    assert first_seed_id in run_payload["input_payload"]["seed_entity_ids"]


def test_continuous_learning_run_fails_when_budget_is_exhausted() -> None:
    """Budget caps should fail the run and emit budget artifacts."""
    client = _build_client()
    space_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/continuous-learning/runs",
        json={
            "seed_entity_ids": [str(uuid4()), str(uuid4())],
            "source_type": "pubmed",
            "max_new_proposals": 5,
            "run_budget": {
                "max_tool_calls": 1,
                "max_external_queries": 2,
                "max_new_proposals": 5,
                "max_runtime_seconds": 300,
                "max_cost_usd": 5.0,
            },
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 409
    assert "max_tool_calls" in response.text

    runs_response = client.get(
        f"/v1/spaces/{space_id}/runs",
        headers=_auth_headers(role="viewer"),
    )
    runs_payload = runs_response.json()
    assert runs_payload["total"] == 1
    run_id = runs_payload["runs"][0]["id"]
    assert runs_payload["runs"][0]["status"] == "failed"

    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/artifacts",
        headers=_auth_headers(role="viewer"),
    )
    artifact_keys = {
        artifact["key"] for artifact in artifacts_response.json()["artifacts"]
    }
    assert "run_budget" in artifact_keys
    assert "budget_status" in artifact_keys
    assert "continuous_learning_error" in artifact_keys

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    workspace_payload = workspace_response.json()
    assert workspace_payload["snapshot"]["status"] == "failed"
    assert workspace_payload["snapshot"]["budget_status"]["status"] == "exhausted"
    assert (
        workspace_payload["snapshot"]["budget_status"]["exhausted_limit"]
        == "max_tool_calls"
    )


def test_schedule_lifecycle_and_run_now_execute_continuous_learning() -> None:
    """Schedules should persist config, expose lifecycle routes, and run now."""
    client = _build_client()
    space_id = str(uuid4())

    create_response = client.post(
        f"/v1/spaces/{space_id}/schedules",
        json={
            "cadence": "daily",
            "seed_entity_ids": [str(uuid4())],
            "source_type": "pubmed",
            "max_new_proposals": 3,
            "max_next_questions": 2,
        },
        headers=_auth_headers(),
    )
    assert create_response.status_code == 201
    created_schedule = create_response.json()
    schedule_id = created_schedule["id"]
    assert created_schedule["harness_id"] == "continuous-learning"
    assert created_schedule["status"] == "active"
    assert created_schedule["configuration"]["run_budget"]["max_tool_calls"] == 100

    list_response = client.get(
        f"/v1/spaces/{space_id}/schedules",
        headers=_auth_headers(role="viewer"),
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    detail_response = client.get(
        f"/v1/spaces/{space_id}/schedules/{schedule_id}",
        headers=_auth_headers(role="viewer"),
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["schedule"]["id"] == schedule_id
    assert detail_response.json()["recent_runs"] == []

    update_response = client.patch(
        f"/v1/spaces/{space_id}/schedules/{schedule_id}",
        json={"title": "Daily MED13 refresh", "cadence": "weekday"},
        headers=_auth_headers(),
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Daily MED13 refresh"
    assert update_response.json()["cadence"] == "weekday"

    pause_response = client.post(
        f"/v1/spaces/{space_id}/schedules/{schedule_id}/pause",
        headers=_auth_headers(),
    )
    assert pause_response.status_code == 200
    assert pause_response.json()["status"] == "paused"

    resume_response = client.post(
        f"/v1/spaces/{space_id}/schedules/{schedule_id}/resume",
        headers=_auth_headers(),
    )
    assert resume_response.status_code == 200
    assert resume_response.json()["status"] == "active"

    run_now_response = client.post(
        f"/v1/spaces/{space_id}/schedules/{schedule_id}/run-now",
        headers=_auth_headers(),
    )
    assert run_now_response.status_code == 201
    run_now_payload = run_now_response.json()
    assert run_now_payload["schedule"]["id"] == schedule_id
    assert run_now_payload["schedule"]["last_run_id"] is not None
    assert run_now_payload["result"]["run"]["harness_id"] == "continuous-learning"
    assert run_now_payload["result"]["proposal_count"] == 1

    refreshed_detail_response = client.get(
        f"/v1/spaces/{space_id}/schedules/{schedule_id}",
        headers=_auth_headers(role="viewer"),
    )
    assert refreshed_detail_response.status_code == 200
    refreshed_detail_payload = refreshed_detail_response.json()
    assert len(refreshed_detail_payload["recent_runs"]) == 1
    assert (
        refreshed_detail_payload["recent_runs"][0]["id"]
        == run_now_payload["result"]["run"]["id"]
    )


def test_create_schedule_rejects_unsupported_cadence() -> None:
    client = _build_client()
    space_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/schedules",
        json={
            "title": "Unsupported schedule",
            "cadence": "monthly",
            "seed_entity_ids": ["11111111-1111-1111-1111-111111111111"],
            "source_type": "pubmed",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 422
    assert "Unsupported cadence" in response.text


def test_send_chat_message_rejects_missing_session() -> None:
    """Sending a chat message to a missing session should return 404."""
    client = _build_client()

    response = client.post(
        f"/v1/spaces/{uuid4()}/chat-sessions/{uuid4()}/messages",
        json={"content": "What does the graph say?"},
        headers=_auth_headers(),
    )

    assert response.status_code == 404


def test_hypothesis_agent_run_completes_and_stages_candidates() -> None:
    """Harness-owned hypothesis runs should stage candidate artifacts."""
    client = _build_client()
    space_id = str(uuid4())
    first_seed_id = str(uuid4())
    second_seed_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/hypotheses/runs",
        json={
            "seed_entity_ids": [first_seed_id, second_seed_id],
            "source_type": "pubmed",
            "max_hypotheses": 5,
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 201
    payload = response.json()
    run_payload = payload["run"]
    assert run_payload["harness_id"] == "hypotheses"
    assert run_payload["status"] == "completed"
    assert payload["candidate_count"] == 2
    assert payload["candidates"][0]["seed_entity_id"] == first_seed_id
    assert payload["candidates"][0]["relation_type"] == "SUGGESTS"

    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_payload['id']}/artifacts",
        headers=_auth_headers(role="viewer"),
    )
    artifacts_payload = artifacts_response.json()
    artifact_keys = {artifact["key"] for artifact in artifacts_payload["artifacts"]}
    assert "hypothesis_candidates" in artifact_keys
    assert "proposal_pack" in artifact_keys

    proposals_response = client.get(
        f"/v1/spaces/{space_id}/proposals",
        params={"run_id": run_payload["id"]},
        headers=_auth_headers(role="viewer"),
    )
    assert proposals_response.status_code == 200
    proposals_payload = proposals_response.json()
    assert proposals_payload["total"] == 2
    proposal_ids = [proposal["id"] for proposal in proposals_payload["proposals"]]
    assert all(
        proposal["proposal_type"] == "candidate_claim"
        for proposal in proposals_payload["proposals"]
    )
    assert all(
        proposal["status"] == "pending_review"
        for proposal in proposals_payload["proposals"]
    )

    proposal_detail_response = client.get(
        f"/v1/spaces/{space_id}/proposals/{proposal_ids[0]}",
        headers=_auth_headers(role="viewer"),
    )
    assert proposal_detail_response.status_code == 200
    proposal_detail_payload = proposal_detail_response.json()
    assert proposal_detail_payload["run_id"] == run_payload["id"]
    assert proposal_detail_payload["ranking_score"] > 0.0

    promote_response = client.post(
        f"/v1/spaces/{space_id}/proposals/{proposal_ids[0]}/promote",
        json={"reason": "Escalate into reviewed claim flow."},
        headers=_auth_headers(),
    )
    assert promote_response.status_code == 200
    promoted_payload = promote_response.json()
    assert promoted_payload["status"] == "promoted"
    assert promoted_payload["metadata"]["graph_claim_id"] is not None
    assert promoted_payload["metadata"]["graph_claim_status"] == "OPEN"

    reject_response = client.post(
        f"/v1/spaces/{space_id}/proposals/{proposal_ids[1]}/reject",
        json={"reason": "Insufficient support for now."},
        headers=_auth_headers(),
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_payload['id']}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    workspace_payload = workspace_response.json()
    assert workspace_payload["snapshot"]["status"] == "completed"
    assert (
        workspace_payload["snapshot"]["last_hypothesis_candidates_key"]
        == "hypothesis_candidates"
    )
    assert workspace_payload["snapshot"]["last_proposal_pack_key"] == "proposal_pack"
    assert workspace_payload["snapshot"]["proposal_count"] == 2
    assert workspace_payload["snapshot"]["last_promoted_graph_claim_id"] is not None
    assert workspace_payload["snapshot"]["proposal_counts"] == {
        "pending_review": 0,
        "promoted": 1,
        "rejected": 1,
    }


def test_mechanism_discovery_run_ranks_candidates_and_stages_hypotheses() -> None:
    """Mechanism-discovery runs should rank converging paths and stage reviewable hypotheses."""
    client = _build_client()
    space_id = str(uuid4())
    first_seed_id = str(uuid4())
    second_seed_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/mechanism-discovery/runs",
        json={
            "seed_entity_ids": [first_seed_id, second_seed_id],
            "max_candidates": 5,
            "max_reasoning_paths": 5,
            "max_path_depth": 2,
            "min_path_confidence": 0.5,
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 201
    payload = response.json()
    run_payload = payload["run"]
    assert run_payload["harness_id"] == "mechanism-discovery"
    assert run_payload["status"] == "completed"
    assert payload["candidate_count"] == 1
    assert payload["proposal_count"] == 1
    assert payload["scanned_path_count"] == 2
    assert payload["candidates"][0]["relation_type"] == "ACTIVATES"
    assert payload["candidates"][0]["target_label"] == "Shared mechanism target"
    assert payload["candidates"][0]["path_count"] == 2

    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_payload['id']}/artifacts",
        headers=_auth_headers(role="viewer"),
    )
    assert artifacts_response.status_code == 200
    artifact_keys = {
        artifact["key"] for artifact in artifacts_response.json()["artifacts"]
    }
    assert "mechanism_candidates" in artifact_keys
    assert "mechanism_score_report" in artifact_keys
    assert "candidate_hypothesis_pack" in artifact_keys

    proposals_response = client.get(
        f"/v1/spaces/{space_id}/proposals",
        params={"run_id": run_payload["id"]},
        headers=_auth_headers(role="viewer"),
    )
    assert proposals_response.status_code == 200
    proposals_payload = proposals_response.json()
    assert proposals_payload["total"] == 1
    proposal_id = proposals_payload["proposals"][0]["id"]
    assert proposals_payload["proposals"][0]["proposal_type"] == "mechanism_candidate"
    assert proposals_payload["proposals"][0]["status"] == "pending_review"

    promote_response = client.post(
        f"/v1/spaces/{space_id}/proposals/{proposal_id}/promote",
        json={"reason": "Promote this converging mechanism to a graph hypothesis."},
        headers=_auth_headers(),
    )
    assert promote_response.status_code == 200
    promoted_payload = promote_response.json()
    assert promoted_payload["status"] == "promoted"
    assert promoted_payload["metadata"]["graph_hypothesis_claim_id"] is not None
    assert promoted_payload["metadata"]["graph_hypothesis_claim_status"] == "OPEN"

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_payload['id']}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    assert workspace_response.status_code == 200
    workspace_payload = workspace_response.json()
    assert workspace_payload["snapshot"]["status"] == "completed"
    assert (
        workspace_payload["snapshot"]["last_mechanism_candidates_key"]
        == "mechanism_candidates"
    )
    assert (
        workspace_payload["snapshot"]["last_mechanism_score_report_key"]
        == "mechanism_score_report"
    )
    assert (
        workspace_payload["snapshot"]["last_candidate_hypothesis_pack_key"]
        == "candidate_hypothesis_pack"
    )
    assert (
        workspace_payload["snapshot"]["last_promoted_hypothesis_claim_id"] is not None
    )
    assert workspace_payload["snapshot"]["proposal_counts"] == {
        "pending_review": 0,
        "promoted": 1,
        "rejected": 0,
    }

    capabilities_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_payload['id']}/capabilities",
        headers=_auth_headers(role="viewer"),
    )
    assert capabilities_response.status_code == 200
    capabilities_payload = capabilities_response.json()
    assert capabilities_payload["active_skill_names"] == [
        "graph_harness.path_analysis",
        "graph_harness.hypothesis_staging",
    ]


def test_claim_curation_run_applies_approved_actions_on_resume() -> None:
    """Claim-curation runs should pause for approval and apply decisions on resume."""
    client = _build_client()
    space_id = str(uuid4())

    hypothesis_response = client.post(
        f"/v1/spaces/{space_id}/agents/hypotheses/runs",
        json={
            "seed_entity_ids": [str(uuid4()), str(uuid4())],
            "source_type": "pubmed",
            "max_hypotheses": 5,
        },
        headers=_auth_headers(),
    )
    assert hypothesis_response.status_code == 201
    proposal_run_id = hypothesis_response.json()["run"]["id"]

    proposals_response = client.get(
        f"/v1/spaces/{space_id}/proposals",
        params={"run_id": proposal_run_id},
        headers=_auth_headers(role="viewer"),
    )
    assert proposals_response.status_code == 200
    proposal_ids = [
        proposal["id"] for proposal in proposals_response.json()["proposals"]
    ]
    assert len(proposal_ids) == 2

    curation_response = client.post(
        f"/v1/spaces/{space_id}/agents/graph-curation/runs",
        json={"proposal_ids": proposal_ids},
        headers=_auth_headers(),
    )

    assert curation_response.status_code == 201
    curation_payload = curation_response.json()
    curation_run_id = curation_payload["run"]["id"]
    assert curation_payload["run"]["harness_id"] == "claim-curation"
    assert curation_payload["run"]["status"] == "paused"
    assert curation_payload["curation_packet_key"] == "curation_packet"
    assert curation_payload["proposal_count"] == 2
    assert curation_payload["blocked_proposal_count"] == 0
    assert curation_payload["pending_approval_count"] == 2
    assert all(
        proposal["eligible_for_approval"] is True
        for proposal in curation_payload["proposals"]
    )

    paused_capabilities_response = client.get(
        f"/v1/spaces/{space_id}/runs/{curation_run_id}/capabilities",
        headers=_auth_headers(role="viewer"),
    )
    assert paused_capabilities_response.status_code == 200
    paused_capabilities_payload = paused_capabilities_response.json()
    assert paused_capabilities_payload["active_skill_names"] == [
        "graph_harness.claim_validation",
    ]

    approvals_response = client.get(
        f"/v1/spaces/{space_id}/runs/{curation_run_id}/approvals",
        headers=_auth_headers(role="viewer"),
    )
    assert approvals_response.status_code == 200
    approvals_payload = approvals_response.json()
    assert approvals_payload["total"] == 2
    approvals_by_target = {
        approval["target_id"]: approval for approval in approvals_payload["approvals"]
    }

    approve_response = client.post(
        (
            f"/v1/spaces/{space_id}/runs/{curation_run_id}/approvals/"
            f"{approvals_by_target[proposal_ids[0]]['approval_key']}"
        ),
        json={"decision": "approved", "reason": "Promote this proposal."},
        headers=_auth_headers(),
    )
    assert approve_response.status_code == 200

    reject_response = client.post(
        (
            f"/v1/spaces/{space_id}/runs/{curation_run_id}/approvals/"
            f"{approvals_by_target[proposal_ids[1]]['approval_key']}"
        ),
        json={"decision": "rejected", "reason": "Reject this proposal."},
        headers=_auth_headers(),
    )
    assert reject_response.status_code == 200

    resume_response = client.post(
        f"/v1/spaces/{space_id}/runs/{curation_run_id}/resume",
        json={"reason": "Curator decisions recorded"},
        headers=_auth_headers(),
    )

    assert resume_response.status_code == 200
    resume_payload = resume_response.json()
    assert resume_payload["run"]["status"] == "completed"
    assert resume_payload["progress"]["phase"] == "completed"
    assert resume_payload["progress"]["metadata"]["action_count"] == 2
    assert resume_payload["progress"]["metadata"]["promoted_count"] == 1
    assert resume_payload["progress"]["metadata"]["rejected_count"] == 1

    promoted_proposal_response = client.get(
        f"/v1/spaces/{space_id}/proposals/{proposal_ids[0]}",
        headers=_auth_headers(role="viewer"),
    )
    rejected_proposal_response = client.get(
        f"/v1/spaces/{space_id}/proposals/{proposal_ids[1]}",
        headers=_auth_headers(role="viewer"),
    )
    assert promoted_proposal_response.status_code == 200
    assert rejected_proposal_response.status_code == 200
    promoted_payload = promoted_proposal_response.json()
    rejected_payload = rejected_proposal_response.json()
    assert promoted_payload["status"] == "promoted"
    assert promoted_payload["metadata"]["graph_claim_id"] is not None
    assert rejected_payload["status"] == "rejected"

    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{curation_run_id}/artifacts",
        headers=_auth_headers(role="viewer"),
    )
    assert artifacts_response.status_code == 200
    artifact_keys = {
        artifact["key"] for artifact in artifacts_response.json()["artifacts"]
    }
    assert "curation_packet" in artifact_keys
    assert "review_plan" in artifact_keys
    assert "approval_intent" in artifact_keys
    assert "curation_actions" in artifact_keys
    assert "curation_summary" in artifact_keys

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{curation_run_id}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    assert workspace_response.status_code == 200
    workspace_payload = workspace_response.json()
    assert workspace_payload["snapshot"]["status"] == "completed"
    assert workspace_payload["snapshot"]["last_curation_packet_key"] == (
        "curation_packet"
    )
    assert workspace_payload["snapshot"]["last_curation_actions_key"] == (
        "curation_actions"
    )
    assert workspace_payload["snapshot"]["last_curation_summary_key"] == (
        "curation_summary"
    )
    assert workspace_payload["snapshot"]["curation_action_counts"] == {
        "promoted": 1,
        "rejected": 1,
    }

    completed_capabilities_response = client.get(
        f"/v1/spaces/{space_id}/runs/{curation_run_id}/capabilities",
        headers=_auth_headers(role="viewer"),
    )
    assert completed_capabilities_response.status_code == 200
    completed_capabilities_payload = completed_capabilities_response.json()
    assert completed_capabilities_payload["active_skill_names"] == [
        "graph_harness.claim_validation",
        "graph_harness.governed_graph_write",
    ]

    events_response = client.get(
        f"/v1/spaces/{space_id}/runs/{curation_run_id}/events",
        headers=_auth_headers(role="viewer"),
    )
    assert events_response.status_code == 200
    event_types = [event["event_type"] for event in events_response.json()["events"]]
    assert "claim_curation.review_built" in event_types
    assert "claim_curation.applied" in event_types


def test_claim_curation_preflight_blocks_graph_duplicates() -> None:
    """Claim-curation runs should exclude proposals blocked by graph-side duplicates."""
    client = _build_client()
    space_id = str(uuid4())
    clean_seed_id = str(uuid4())

    hypothesis_response = client.post(
        f"/v1/spaces/{space_id}/agents/hypotheses/runs",
        json={
            "seed_entity_ids": [_CURATION_DUPLICATE_SOURCE_ID, clean_seed_id],
            "source_type": "pubmed",
            "max_hypotheses": 5,
        },
        headers=_auth_headers(),
    )
    assert hypothesis_response.status_code == 201
    proposal_run_id = hypothesis_response.json()["run"]["id"]

    proposals_response = client.get(
        f"/v1/spaces/{space_id}/proposals",
        params={"run_id": proposal_run_id},
        headers=_auth_headers(role="viewer"),
    )
    assert proposals_response.status_code == 200
    proposal_ids = [
        proposal["id"] for proposal in proposals_response.json()["proposals"]
    ]

    curation_response = client.post(
        f"/v1/spaces/{space_id}/agents/graph-curation/runs",
        json={"proposal_ids": proposal_ids},
        headers=_auth_headers(),
    )
    assert curation_response.status_code == 201
    curation_payload = curation_response.json()
    assert curation_payload["proposal_count"] == 2
    assert curation_payload["blocked_proposal_count"] == 1
    assert curation_payload["pending_approval_count"] == 1

    blocked = [
        proposal
        for proposal in curation_payload["proposals"]
        if proposal["eligible_for_approval"] is False
    ]
    assert len(blocked) == 1
    assert blocked[0]["graph_duplicate_claim_ids"] == [
        str(_CURATION_DUPLICATE_CLAIM_ID),
    ]
    assert blocked[0]["conflicting_relation_ids"] == [
        str(_CURATION_DUPLICATE_RELATION_ID),
    ]
    assert blocked[0]["blocker_reasons"]

    approvals_response = client.get(
        f"/v1/spaces/{space_id}/runs/{curation_payload['run']['id']}/approvals",
        headers=_auth_headers(role="viewer"),
    )
    assert approvals_response.status_code == 200
    approvals_payload = approvals_response.json()
    assert approvals_payload["total"] == 1

    review_plan_response = client.get(
        f"/v1/spaces/{space_id}/runs/{curation_payload['run']['id']}/artifacts/review_plan",
        headers=_auth_headers(role="viewer"),
    )
    assert review_plan_response.status_code == 200
    review_plan = review_plan_response.json()["content"]
    assert review_plan["blocked_proposal_count"] == 1
    assert review_plan["warning_count"] >= 2

    curation_packet_response = client.get(
        f"/v1/spaces/{space_id}/runs/{curation_payload['run']['id']}/artifacts/curation_packet",
        headers=_auth_headers(role="viewer"),
    )
    assert curation_packet_response.status_code == 200
    curation_packet = curation_packet_response.json()["content"]
    assert curation_packet["eligible_proposal_count"] == 1
    assert curation_packet["blocked_proposal_count"] == 1
    assert curation_packet["graph_duplicate_claim_count"] == 1
    assert curation_packet["graph_conflict_count"] == 1

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{curation_payload['run']['id']}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    assert workspace_response.status_code == 200
    workspace = workspace_response.json()["snapshot"]
    assert workspace["blocked_proposal_count"] == 1
    assert workspace["last_curation_packet_key"] == "curation_packet"


def test_harness_endpoints_require_authentication() -> None:
    """Protected harness endpoints should reject anonymous callers."""
    client = _build_client()

    response = client.get("/v1/harnesses")

    assert response.status_code == 401


def test_write_endpoints_reject_viewer_role() -> None:
    """Viewer users should not be allowed to start harness runs."""
    client = _build_client()

    response = client.post(
        f"/v1/spaces/{uuid4()}/runs",
        json={"harness_id": "graph-chat"},
        headers=_auth_headers(role="viewer"),
    )

    assert response.status_code == 403
