"""Unit tests for the graph-harness queued-run worker."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from services.graph_harness_api.approval_store import HarnessApprovalStore
from services.graph_harness_api.artifact_store import HarnessArtifactStore
from services.graph_harness_api.chat_sessions import HarnessChatSessionStore
from services.graph_harness_api.continuous_learning_runtime import (
    execute_continuous_learning_run,
    queue_continuous_learning_run,
)
from services.graph_harness_api.graph_chat_runtime import (
    GraphChatResult,
    HarnessGraphChatRequest,
    HarnessGraphChatRunner,
)
from services.graph_harness_api.graph_client import GraphApiGateway
from services.graph_harness_api.graph_connection_runtime import (
    HarnessGraphConnectionRequest,
    HarnessGraphConnectionResult,
    HarnessGraphConnectionRunner,
)
from services.graph_harness_api.graph_snapshot import HarnessGraphSnapshotStore
from services.graph_harness_api.harness_runtime import (
    HarnessExecutionResult,
    HarnessExecutionServices,
)
from services.graph_harness_api.proposal_store import HarnessProposalStore
from services.graph_harness_api.research_state import HarnessResearchStateStore
from services.graph_harness_api.run_budget import default_continuous_learning_run_budget
from services.graph_harness_api.run_registry import HarnessRunRecord, HarnessRunRegistry
from services.graph_harness_api.schedule_store import HarnessScheduleStore
from services.graph_harness_api.worker import run_worker_tick
from src.application.services.pubmed_discovery_service import PubMedDiscoveryService
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_connection import (
    GraphConnectionContract,
    ProposedRelation,
)
from src.infrastructure.graph_service.client import GraphServiceHealthResponse
from src.type_definitions.graph_service_contracts import (
    HypothesisListResponse,
    HypothesisResponse,
    KernelGraphDocumentCounts,
    KernelGraphDocumentEdge,
    KernelGraphDocumentMeta,
    KernelGraphDocumentNode,
    KernelGraphDocumentRequest,
    KernelGraphDocumentResponse,
    KernelRelationClaimListResponse,
    KernelRelationClaimResponse,
)
from tests.graph_harness_api_support import (
    FakeEvent,
    FakeEventType,
    FakePayload,
    FakeStepToolResult,
    fake_tool_allowlist,
    fake_tool_result_payload,
)

if TYPE_CHECKING:
    from services.graph_harness_api.composition import GraphHarnessKernelRuntime


class _FakeGraphApiGateway(GraphApiGateway):
    def __init__(self) -> None:
        self.closed = False

    def get_health(self) -> GraphServiceHealthResponse:
        return GraphServiceHealthResponse(status="ok", version="test-graph")

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
        relation_id = uuid5(NAMESPACE_URL, f"worker-relation:{space_id}")
        return KernelRelationClaimListResponse(
            claims=[
                KernelRelationClaimResponse(
                    id=uuid5(NAMESPACE_URL, f"worker-claim:{space_id}"),
                    research_space_id=UUID(str(space_id)),
                    source_document_id=None,
                    source_document_ref="pmid:1",
                    agent_run_id="continuous_learning:test-worker",
                    source_type="PUBMED",
                    relation_type="SUGGESTS",
                    target_type="GENE",
                    source_label="MED13",
                    target_label="Mediator complex",
                    confidence=0.72,
                    validation_state="ALLOWED",
                    validation_reason="test",
                    persistability="PERSISTABLE",
                    claim_status="OPEN",
                    polarity="SUPPORT",
                    claim_text="Synthetic worker claim",
                    claim_section=None,
                    linked_relation_id=relation_id,
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

    def list_hypotheses(
        self,
        *,
        space_id: UUID | str,
        limit: int = 25,
        offset: int = 0,
    ) -> HypothesisListResponse:
        del offset
        return HypothesisListResponse(
            hypotheses=[
                HypothesisResponse(
                    claim_id=uuid5(NAMESPACE_URL, f"worker-hypothesis:{space_id}"),
                    polarity="SUPPORT",
                    claim_status="OPEN",
                    validation_state="ALLOWED",
                    persistability="PERSISTABLE",
                    confidence=0.68,
                    source_label="MED13",
                    relation_type="REGULATES",
                    target_label="Transcriptional program",
                    claim_text="Synthetic worker hypothesis",
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
                    explanation="Synthetic worker hypothesis.",
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
        claim_id = uuid5(NAMESPACE_URL, f"worker-claim:{space_id}")
        relation_id = uuid5(NAMESPACE_URL, f"worker-relation:{space_id}")
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
                    id="CLAIM:worker",
                    resource_id=str(claim_id),
                    kind="CLAIM",
                    type_label="RELATION_CLAIM",
                    label="Synthetic worker claim",
                    confidence=0.72,
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
                    id="CANONICAL_RELATION:worker",
                    resource_id=str(relation_id),
                    kind="CANONICAL_RELATION",
                    source_id="ENTITY:seed",
                    target_id="CLAIM:worker",
                    type_label="SUGGESTS",
                    label="suggests",
                    confidence=0.72,
                    curation_status="accepted",
                    claim_id=None,
                    canonical_relation_id=relation_id,
                    evidence_id=None,
                    metadata={},
                    created_at=now,
                    updated_at=now,
                ),
            ],
            meta=KernelGraphDocumentMeta(
                mode=request.mode,
                seed_entity_ids=[UUID(seed_entity_id)],
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

    def close(self) -> None:
        self.closed = True


class _FakeGraphConnectionRunner(HarnessGraphConnectionRunner):
    async def run(
        self,
        request: HarnessGraphConnectionRequest,
    ) -> HarnessGraphConnectionResult:
        contract = GraphConnectionContract(
            decision="generated",
            confidence_score=0.72,
            rationale="Synthetic worker graph-connection result.",
            evidence=[
                EvidenceItem(
                    source_type="db",
                    locator=f"seed:{request.seed_entity_id}",
                    excerpt="Synthetic worker evidence",
                    relevance=0.72,
                ),
            ],
            source_type=request.source_type or "pubmed",
            research_space_id=request.research_space_id,
            seed_entity_id=request.seed_entity_id,
            proposed_relations=[
                ProposedRelation(
                    source_id=request.seed_entity_id,
                    relation_type="SUGGESTS",
                    target_id="33333333-3333-3333-3333-333333333333",
                    confidence=0.72,
                    evidence_summary="Synthetic worker hypothesis evidence",
                    supporting_document_count=2,
                    reasoning="Synthetic worker bridge.",
                ),
            ],
            rejected_candidates=[],
            shadow_mode=request.shadow_mode,
            agent_run_id="graph_connection:test-worker",
        )
        return HarnessGraphConnectionResult(
            contract=contract,
            agent_run_id=contract.agent_run_id,
            active_skill_names=(
                "graph_harness.graph_grounding",
                "graph_harness.relation_discovery",
            ),
        )


class _FakeKernelRuntime:
    def __init__(self) -> None:
        self._leases: dict[tuple[str, str], str] = {}
        self._events: dict[tuple[str, str], list[FakeEvent]] = {}
        self.acquired: list[tuple[str, str, str]] = []
        self.released: list[tuple[str, str, str]] = []

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
        self.acquired.append((tenant_id, run_id, worker_id))
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
        self.released.append((tenant_id, run_id, worker_id))
        return True

    def get_events(
        self,
        *,
        run_id: str,
        tenant_id: str,
    ) -> tuple[FakeEvent, ...]:
        return tuple(self._events.get((tenant_id, run_id), ()))

    def explain_tool_allowlist(
        self,
        *,
        tenant_id: str,
        run_id: str,
        visible_tool_names: set[str] | None = None,
    ) -> dict[str, object]:
        _ = tenant_id, run_id
        return fake_tool_allowlist(visible_tool_names=visible_tool_names)

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
        result_payload = fake_tool_result_payload(
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
            fake_tool_result_payload(tool_name=tool_name, arguments=arguments),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )


class _FakeGraphChatRunner(HarnessGraphChatRunner):
    async def run(self, request: HarnessGraphChatRequest) -> GraphChatResult:
        del request
        raise AssertionError("graph-chat execution is not expected in worker tests")


@contextmanager
def _fake_pubmed_discovery_context() -> Iterator[PubMedDiscoveryService]:
    yield cast("PubMedDiscoveryService", object())


def _payload_strings(payload: object) -> list[str]:
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, str)]


def _payload_int(payload: object, *, default: int) -> int:
    return (
        payload
        if isinstance(payload, int) and not isinstance(payload, bool)
        else default
    )


def _payload_string(payload: object) -> str | None:
    return payload if isinstance(payload, str) else None


async def _execute_continuous_learning_worker_run(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    payload = run.input_payload
    return await execute_continuous_learning_run(
        space_id=UUID(run.space_id),
        title=run.title,
        seed_entity_ids=_payload_strings(payload.get("seed_entity_ids")),
        source_type=str(payload.get("source_type", "pubmed")),
        relation_types=_payload_strings(payload.get("relation_types")) or None,
        max_depth=_payload_int(payload.get("max_depth"), default=2),
        max_new_proposals=_payload_int(payload.get("max_new_proposals"), default=20),
        max_next_questions=_payload_int(payload.get("max_next_questions"), default=5),
        model_id=_payload_string(payload.get("model_id")),
        schedule_id=_payload_string(payload.get("schedule_id")),
        run_budget=default_continuous_learning_run_budget(),
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


def test_run_worker_tick_executes_queued_continuous_learning_runs() -> None:
    runtime = _FakeKernelRuntime()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    chat_session_store = HarnessChatSessionStore()
    proposal_store = HarnessProposalStore()
    approval_store = HarnessApprovalStore()
    research_state_store = HarnessResearchStateStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    schedule_store = HarnessScheduleStore()
    space_id = uuid4()
    run = queue_continuous_learning_run(
        space_id=space_id,
        title="Daily refresh",
        seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_new_proposals=20,
        max_next_questions=5,
        model_id=None,
        schedule_id="schedule-1",
        run_budget=default_continuous_learning_run_budget(),
        graph_service_status="queued",
        graph_service_version="pending",
        previous_graph_snapshot_id=None,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    services = HarnessExecutionServices(
        runtime=cast("GraphHarnessKernelRuntime", runtime),
        run_registry=run_registry,
        artifact_store=artifact_store,
        chat_session_store=chat_session_store,
        proposal_store=proposal_store,
        approval_store=approval_store,
        research_state_store=research_state_store,
        graph_snapshot_store=graph_snapshot_store,
        schedule_store=schedule_store,
        graph_connection_runner=_FakeGraphConnectionRunner(),
        graph_chat_runner=_FakeGraphChatRunner(),
        graph_api_gateway_factory=_FakeGraphApiGateway,
        pubmed_discovery_service_factory=_fake_pubmed_discovery_context,
    )

    result = asyncio.run(
        run_worker_tick(
            candidate_runs=[run],
            runtime=cast("GraphHarnessKernelRuntime", runtime),
            services=services,
            worker_id="worker-1",
            lease_ttl_seconds=120,
            execute_run=_execute_continuous_learning_worker_run,
        ),
    )

    assert result.scanned_run_count == 1
    assert result.leased_run_count == 1
    assert result.executed_run_count == 1
    assert result.completed_run_count == 1
    assert result.failed_run_count == 0
    assert result.skipped_run_count == 0
    assert result.errors == ()
    assert result.results[0].outcome == "completed"
    assert runtime.acquired == [(str(space_id), run.id, "worker-1")]
    assert runtime.released == [(str(space_id), run.id, "worker-1")]

    updated_run = run_registry.get_run(space_id=space_id, run_id=run.id)
    assert updated_run is not None
    assert updated_run.status == "completed"
    research_state = research_state_store.get_state(space_id=space_id)
    assert research_state is not None
    assert research_state.last_graph_snapshot_id is not None
    assert len(graph_snapshot_store.list_snapshots(space_id=space_id)) == 1


def test_run_worker_tick_skips_runs_without_a_lease() -> None:
    runtime = _FakeKernelRuntime()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    chat_session_store = HarnessChatSessionStore()
    proposal_store = HarnessProposalStore()
    approval_store = HarnessApprovalStore()
    research_state_store = HarnessResearchStateStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    schedule_store = HarnessScheduleStore()
    space_id = uuid4()
    run = queue_continuous_learning_run(
        space_id=space_id,
        title="Daily refresh",
        seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_new_proposals=20,
        max_next_questions=5,
        model_id=None,
        schedule_id="schedule-1",
        run_budget=default_continuous_learning_run_budget(),
        graph_service_status="queued",
        graph_service_version="pending",
        previous_graph_snapshot_id=None,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    runtime.acquire_run_lease(
        run_id=run.id,
        tenant_id=str(space_id),
        worker_id="another-worker",
        ttl_seconds=120,
    )
    services = HarnessExecutionServices(
        runtime=cast("GraphHarnessKernelRuntime", runtime),
        run_registry=run_registry,
        artifact_store=artifact_store,
        chat_session_store=chat_session_store,
        proposal_store=proposal_store,
        approval_store=approval_store,
        research_state_store=research_state_store,
        graph_snapshot_store=graph_snapshot_store,
        schedule_store=schedule_store,
        graph_connection_runner=_FakeGraphConnectionRunner(),
        graph_chat_runner=_FakeGraphChatRunner(),
        graph_api_gateway_factory=_FakeGraphApiGateway,
        pubmed_discovery_service_factory=_fake_pubmed_discovery_context,
    )

    result = asyncio.run(
        run_worker_tick(
            candidate_runs=[run],
            runtime=cast("GraphHarnessKernelRuntime", runtime),
            services=services,
            worker_id="worker-1",
            lease_ttl_seconds=120,
            execute_run=_execute_continuous_learning_worker_run,
        ),
    )

    assert result.scanned_run_count == 1
    assert result.leased_run_count == 0
    assert result.executed_run_count == 0
    assert result.completed_run_count == 0
    assert result.failed_run_count == 0
    assert result.skipped_run_count == 1
    assert result.results[0].outcome == "lease_skipped"

    updated_run = run_registry.get_run(space_id=space_id, run_id=run.id)
    assert updated_run is not None
    assert updated_run.status == "queued"
