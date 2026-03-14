"""Integration coverage for Artana-backed graph-harness runtime paths."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from services.graph_harness_api.app import create_app
from services.graph_harness_api.approval_store import HarnessApprovalAction
from services.graph_harness_api.artana_stores import (
    ArtanaBackedHarnessArtifactStore,
    ArtanaBackedHarnessRunRegistry,
)
from services.graph_harness_api.claim_curation_workflow import ClaimCurationRunExecution
from services.graph_harness_api.dependencies import (
    get_approval_store,
    get_artifact_store,
    get_chat_session_store,
    get_graph_api_gateway,
    get_graph_snapshot_store,
    get_harness_execution_services,
    get_proposal_store,
    get_research_state_store,
    get_run_registry,
    get_schedule_store,
)
from services.graph_harness_api.graph_chat_runtime import HarnessGraphChatRunner
from services.graph_harness_api.graph_connection_runtime import (
    HarnessGraphConnectionRunner,
)
from services.graph_harness_api.harness_runtime import (
    HarnessExecutionResult,
    HarnessExecutionServices,
)
from services.graph_harness_api.proposal_store import HarnessProposalDraft
from services.graph_harness_api.research_bootstrap_runtime import (
    ResearchBootstrapExecutionResult,
)
from services.graph_harness_api.run_registry import HarnessRunRecord
from services.graph_harness_api.schedule_store import HarnessScheduleStore
from services.graph_harness_api.scheduler import run_scheduler_tick
from services.graph_harness_api.sqlalchemy_stores import (
    SqlAlchemyHarnessApprovalStore,
    SqlAlchemyHarnessChatSessionStore,
    SqlAlchemyHarnessGraphSnapshotStore,
    SqlAlchemyHarnessProposalStore,
    SqlAlchemyHarnessResearchStateStore,
    SqlAlchemyHarnessScheduleStore,
)
from services.graph_harness_api.supervisor_runtime import SupervisorExecutionResult
from services.graph_harness_api.tool_catalog import RunPubMedSearchToolArgs
from services.graph_harness_api.transparency import append_manual_review_decision
from services.graph_harness_api.worker import list_queued_worker_runs, run_worker_tick
from tests.graph_harness_api_support import (
    FakeGraphApiGateway,
    FakeKernelRuntime,
    auth_headers,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

    from services.graph_harness_api.composition import GraphHarnessKernelRuntime
    from src.application.services.pubmed_discovery_service import PubMedDiscoveryService


@contextmanager
def _fake_pubmed_discovery_context() -> Iterator[PubMedDiscoveryService]:
    yield cast("PubMedDiscoveryService", object())


ExecutionOverride = Callable[
    [HarnessRunRecord, HarnessExecutionServices],
    Awaitable[HarnessExecutionResult],
]


async def _complete_run(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=run.id,
        status="running",
    )
    services.run_registry.set_progress(
        space_id=run.space_id,
        run_id=run.id,
        phase="execute",
        message="Worker executed the queued run.",
        progress_percent=0.6,
        completed_steps=1,
        total_steps=2,
        metadata={"executor": "integration-test"},
    )
    services.run_registry.record_event(
        space_id=run.space_id,
        run_id=run.id,
        event_type="run.executed",
        message="Integration worker execution completed.",
        payload={"executor": "integration-test"},
        progress_percent=0.6,
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="integration_result",
        media_type="application/json",
        content={"run_id": run.id, "harness_id": run.harness_id},
    )
    services.artifact_store.patch_workspace(
        space_id=run.space_id,
        run_id=run.id,
        patch={
            "status": "completed",
            "integration_result_key": "integration_result",
        },
    )
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=run.id,
        status="completed",
    )
    services.run_registry.set_progress(
        space_id=run.space_id,
        run_id=run.id,
        phase="completed",
        message="Run completed through the Artana-backed worker path.",
        progress_percent=1.0,
        completed_steps=2,
        total_steps=2,
        clear_resume_point=True,
        metadata={"executor": "integration-test", "result_key": "integration_result"},
    )
    return services.run_registry.get_run(space_id=run.space_id, run_id=run.id) or run


def _candidate_claim_payload(
    *,
    source_entity_id: str,
    target_entity_id: str,
    relation_type: str = "REGULATES",
) -> dict[str, object]:
    return {
        "proposed_subject": source_entity_id,
        "proposed_object": target_entity_id,
        "proposed_claim_type": relation_type,
    }


async def _bootstrap_execution_override(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    if run.harness_id != "research-bootstrap":
        return await _complete_run(run, services)
    objective = run.input_payload.get("objective")
    objective_text = objective if isinstance(objective, str) else "Synthetic objective"
    seed_entity_id = str(uuid4())
    target_entity_id = str(uuid4())
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=run.id,
        status="running",
    )
    graph_snapshot = services.graph_snapshot_store.create_snapshot(
        space_id=run.space_id,
        source_run_id=run.id,
        claim_ids=["claim-bootstrap-1"],
        relation_ids=["relation-bootstrap-1"],
        graph_document_hash="bootstrap-hash",
        summary={
            "objective": objective_text,
            "claim_count": 1,
            "relation_count": 1,
        },
        metadata={"source": "integration-bootstrap"},
    )
    research_state = services.research_state_store.upsert_state(
        space_id=run.space_id,
        objective=objective_text,
        pending_questions=["What should be validated next?"],
        current_hypotheses=["MED13 regulates transcription."],
        last_graph_snapshot_id=graph_snapshot.id,
        metadata={"source": "integration-bootstrap"},
    )
    proposal_records = services.proposal_store.create_proposals(
        space_id=run.space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="research_bootstrap",
                source_key=f"{seed_entity_id}:REGULATES:{target_entity_id}",
                title="MED13 regulates transcription",
                summary="Synthetic bootstrap proposal.",
                confidence=0.82,
                ranking_score=0.91,
                reasoning_path={"reasoning": "Synthetic bootstrap reasoning."},
                evidence_bundle=[{"source_type": "db", "locator": seed_entity_id}],
                payload=_candidate_claim_payload(
                    source_entity_id=seed_entity_id,
                    target_entity_id=target_entity_id,
                ),
                metadata={"agent_run_id": "integration-bootstrap"},
            ),
        ),
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="graph_context_snapshot",
        media_type="application/json",
        content={
            "snapshot_id": graph_snapshot.id,
            "claim_ids": graph_snapshot.claim_ids,
            "relation_ids": graph_snapshot.relation_ids,
        },
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="research_brief",
        media_type="application/json",
        content={"objective": objective_text},
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="graph_summary",
        media_type="application/json",
        content={"claim_count": 1, "relation_count": 1},
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="source_inventory",
        media_type="application/json",
        content={"source_type": "pubmed", "source_count": 1},
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="candidate_claim_pack",
        media_type="application/json",
        content={
            "proposal_count": len(proposal_records),
            "proposal_ids": [proposal.id for proposal in proposal_records],
        },
    )
    services.artifact_store.patch_workspace(
        space_id=run.space_id,
        run_id=run.id,
        patch={
            "status": "completed",
            "graph_snapshot_id": graph_snapshot.id,
            "proposal_count": len(proposal_records),
        },
    )
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=run.id,
        status="completed",
    )
    services.run_registry.set_progress(
        space_id=run.space_id,
        run_id=run.id,
        phase="completed",
        message="Research bootstrap completed.",
        progress_percent=1.0,
        completed_steps=4,
        total_steps=4,
        clear_resume_point=True,
        metadata={"proposal_count": len(proposal_records)},
    )
    completed_run = services.run_registry.get_run(space_id=run.space_id, run_id=run.id)
    if completed_run is None:
        msg = "Failed to reload completed research-bootstrap run."
        raise RuntimeError(msg)
    return ResearchBootstrapExecutionResult(
        run=completed_run,
        graph_snapshot=graph_snapshot,
        research_state=research_state,
        research_brief={"objective": objective_text},
        graph_summary={"claim_count": 1, "relation_count": 1},
        source_inventory={"source_type": "pubmed", "source_count": 1},
        proposal_records=proposal_records,
        pending_questions=["What should be validated next?"],
        errors=[],
    )


async def _supervisor_execution_override(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    if run.harness_id != "supervisor":
        return await _complete_run(run, services)
    workspace = services.artifact_store.get_workspace(
        space_id=run.space_id,
        run_id=run.id,
    )
    workspace_snapshot = workspace.snapshot if workspace is not None else {}
    curation_run_id = workspace_snapshot.get("curation_run_id")
    if not isinstance(curation_run_id, str) or curation_run_id == "":
        bootstrap_parent_run = HarnessRunRecord(
            id=run.id,
            space_id=run.space_id,
            harness_id="research-bootstrap",
            title="Supervisor Bootstrap",
            status="queued",
            input_payload={"objective": run.input_payload.get("objective")},
            graph_service_status=run.graph_service_status,
            graph_service_version=run.graph_service_version,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
        bootstrap_result = cast(
            "ResearchBootstrapExecutionResult",
            await _bootstrap_execution_override(bootstrap_parent_run, services),
        )
        curation_run = services.run_registry.create_run(
            space_id=run.space_id,
            harness_id="claim-curation",
            title="Supervisor Curation",
            input_payload={"workflow": "claim_curation", "proposal_ids": []},
            graph_service_status="ok",
            graph_service_version="test-graph",
        )
        services.artifact_store.seed_for_run(run=curation_run)
        selected_proposal = bootstrap_result.proposal_records[0]
        approval_key = f"promote:{selected_proposal.id}"
        review_plan = {
            "proposals": [
                {
                    "proposal_id": selected_proposal.id,
                    "title": selected_proposal.title,
                    "summary": selected_proposal.summary,
                    "source_key": selected_proposal.source_key,
                    "confidence": selected_proposal.confidence,
                    "ranking_score": selected_proposal.ranking_score,
                    "approval_key": approval_key,
                    "duplicate_selected_count": 0,
                    "existing_promoted_proposal_ids": [],
                    "graph_duplicate_claim_ids": [],
                    "conflicting_relation_ids": [],
                    "invariant_issues": [],
                    "blocker_reasons": [],
                    "eligible_for_approval": True,
                },
            ],
        }
        curation_packet = {"proposal_ids": [selected_proposal.id]}
        approval_intent = {"summary": "Review supervisor curation."}
        services.approval_store.upsert_intent(
            space_id=run.space_id,
            run_id=curation_run.id,
            summary="Review supervisor curation.",
            proposed_actions=(
                HarnessApprovalAction(
                    approval_key=approval_key,
                    title="Promote bootstrap proposal",
                    risk_level="high",
                    target_type="proposal",
                    target_id=selected_proposal.id,
                    requires_approval=True,
                    metadata={"proposal_id": selected_proposal.id},
                ),
            ),
            metadata={"workflow": "claim_curation"},
        )
        services.artifact_store.put_artifact(
            space_id=run.space_id,
            run_id=curation_run.id,
            artifact_key="curation_packet",
            media_type="application/json",
            content=curation_packet,
        )
        services.artifact_store.put_artifact(
            space_id=run.space_id,
            run_id=curation_run.id,
            artifact_key="review_plan",
            media_type="application/json",
            content=review_plan,
        )
        services.artifact_store.put_artifact(
            space_id=run.space_id,
            run_id=curation_run.id,
            artifact_key="approval_intent",
            media_type="application/json",
            content=approval_intent,
        )
        services.artifact_store.patch_workspace(
            space_id=run.space_id,
            run_id=curation_run.id,
            patch={"status": "paused", "pending_approvals": 1},
        )
        services.run_registry.set_run_status(
            space_id=run.space_id,
            run_id=curation_run.id,
            status="paused",
        )
        services.run_registry.set_progress(
            space_id=run.space_id,
            run_id=curation_run.id,
            phase="approval",
            message="Child curation paused pending approval.",
            progress_percent=0.5,
            completed_steps=1,
            total_steps=2,
            resume_point="approval_gate",
            metadata={"pending_approvals": 1},
        )
        curation_execution = ClaimCurationRunExecution(
            run=services.run_registry.get_run(
                space_id=run.space_id,
                run_id=curation_run.id,
            )
            or curation_run,
            curation_packet=curation_packet,
            review_plan=review_plan,
            approval_intent=approval_intent,
            proposal_count=1,
            blocked_proposal_count=0,
            pending_approval_count=1,
        )
        services.artifact_store.patch_workspace(
            space_id=run.space_id,
            run_id=run.id,
            patch={
                "status": "paused",
                "curation_run_id": curation_run.id,
                "selected_curation_proposal_ids": [selected_proposal.id],
            },
        )
        services.run_registry.set_run_status(
            space_id=run.space_id,
            run_id=run.id,
            status="paused",
        )
        services.run_registry.set_progress(
            space_id=run.space_id,
            run_id=run.id,
            phase="approval",
            message="Supervisor paused pending child approval.",
            progress_percent=0.75,
            completed_steps=2,
            total_steps=3,
            resume_point="supervisor_child_approval_gate",
            metadata={"curation_run_id": curation_run.id},
        )
        paused_parent = services.run_registry.get_run(
            space_id=run.space_id,
            run_id=run.id,
        )
        if paused_parent is None:
            msg = "Failed to reload paused supervisor run."
            raise RuntimeError(msg)
        return SupervisorExecutionResult(
            run=paused_parent,
            bootstrap=bootstrap_result,
            chat_session=None,
            chat=None,
            curation=curation_execution,
            briefing_question=None,
            curation_source="bootstrap",
            chat_graph_write=None,
            selected_curation_proposal_ids=(selected_proposal.id,),
            steps=(
                {
                    "step": "bootstrap",
                    "status": "completed",
                    "harness_id": "research-bootstrap",
                    "run_id": bootstrap_result.run.id,
                    "detail": "Bootstrap finished.",
                },
                {
                    "step": "curation",
                    "status": "paused",
                    "harness_id": "claim-curation",
                    "run_id": curation_run.id,
                    "detail": "Awaiting approval.",
                },
            ),
        )
    approvals = services.approval_store.list_approvals(
        space_id=run.space_id,
        run_id=curation_run_id,
    )
    pending_approval_keys = [
        approval.approval_key for approval in approvals if approval.status == "pending"
    ]
    if pending_approval_keys:
        msg = f"Supervisor child approvals still pending: {', '.join(pending_approval_keys)}"
        raise RuntimeError(msg)
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=curation_run_id,
        status="completed",
    )
    services.run_registry.set_progress(
        space_id=run.space_id,
        run_id=curation_run_id,
        phase="completed",
        message="Child curation completed.",
        progress_percent=1.0,
        completed_steps=2,
        total_steps=2,
        clear_resume_point=True,
        metadata={"pending_approvals": 0},
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=curation_run_id,
        artifact_key="curation_summary",
        media_type="application/json",
        content={"applied": True},
    )
    services.artifact_store.patch_workspace(
        space_id=run.space_id,
        run_id=curation_run_id,
        patch={"status": "completed", "pending_approvals": 0},
    )
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=run.id,
        status="completed",
    )
    services.run_registry.set_progress(
        space_id=run.space_id,
        run_id=run.id,
        phase="completed",
        message="Supervisor completed after child approval resolution.",
        progress_percent=1.0,
        completed_steps=3,
        total_steps=3,
        clear_resume_point=True,
        metadata={"curation_run_id": curation_run_id},
    )
    services.artifact_store.patch_workspace(
        space_id=run.space_id,
        run_id=run.id,
        patch={"status": "completed"},
    )
    return services.run_registry.get_run(space_id=run.space_id, run_id=run.id) or run


def _build_services(
    *,
    session: Session,
    runtime: FakeKernelRuntime,
    execution_override: ExecutionOverride = _complete_run,
) -> HarnessExecutionServices:
    return HarnessExecutionServices(
        runtime=cast("GraphHarnessKernelRuntime", runtime),
        run_registry=ArtanaBackedHarnessRunRegistry(
            session=session,
            runtime=cast("GraphHarnessKernelRuntime", runtime),
        ),
        artifact_store=ArtanaBackedHarnessArtifactStore(
            runtime=cast("GraphHarnessKernelRuntime", runtime),
        ),
        chat_session_store=SqlAlchemyHarnessChatSessionStore(session),
        proposal_store=SqlAlchemyHarnessProposalStore(session),
        approval_store=SqlAlchemyHarnessApprovalStore(session),
        research_state_store=SqlAlchemyHarnessResearchStateStore(session),
        graph_snapshot_store=SqlAlchemyHarnessGraphSnapshotStore(session),
        schedule_store=SqlAlchemyHarnessScheduleStore(session),
        graph_connection_runner=HarnessGraphConnectionRunner(),
        graph_chat_runner=HarnessGraphChatRunner(),
        graph_api_gateway_factory=FakeGraphApiGateway,
        pubmed_discovery_service_factory=_fake_pubmed_discovery_context,
        execution_override=execution_override,
    )


def _build_client(
    *,
    session: Session,
    runtime: FakeKernelRuntime,
    services: HarnessExecutionServices | None = None,
    execution_override: ExecutionOverride = _complete_run,
) -> TestClient:
    resolved_services = services or _build_services(
        session=session,
        runtime=runtime,
        execution_override=execution_override,
    )
    app = create_app()
    app.dependency_overrides[get_run_registry] = lambda: resolved_services.run_registry
    app.dependency_overrides[get_artifact_store] = (
        lambda: resolved_services.artifact_store
    )
    app.dependency_overrides[get_approval_store] = (
        lambda: resolved_services.approval_store
    )
    app.dependency_overrides[get_chat_session_store] = lambda: (
        resolved_services.chat_session_store
    )
    app.dependency_overrides[get_graph_api_gateway] = FakeGraphApiGateway
    app.dependency_overrides[get_graph_snapshot_store] = (
        lambda: resolved_services.graph_snapshot_store
    )
    app.dependency_overrides[get_harness_execution_services] = lambda: resolved_services
    app.dependency_overrides[get_proposal_store] = (
        lambda: resolved_services.proposal_store
    )
    app.dependency_overrides[get_research_state_store] = (
        lambda: resolved_services.research_state_store
    )
    app.dependency_overrides[get_schedule_store] = (
        lambda: resolved_services.schedule_store
    )
    return TestClient(app)


@pytest.mark.integration
def test_run_api_uses_artana_backed_lifecycle_for_create_list_progress_events_and_resume(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    client = _build_client(session=db_session, runtime=runtime)
    space_id = str(uuid4())

    create_response = client.post(
        f"/v1/spaces/{space_id}/runs",
        headers=auth_headers(),
        json={
            "harness_id": "graph-chat",
            "title": "Integration Chat Run",
            "input_payload": {
                "session_id": str(uuid4()),
                "question": "What is known about MED13?",
            },
        },
    )
    assert create_response.status_code == 201
    run_payload = create_response.json()
    run_id = run_payload["id"]

    list_response = client.get(
        f"/v1/spaces/{space_id}/runs",
        headers=auth_headers(),
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    detail_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}",
        headers=auth_headers(),
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "queued"

    progress_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/progress",
        headers=auth_headers(),
    )
    assert progress_response.status_code == 200
    assert progress_response.json()["phase"] == "queued"

    events_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/events",
        headers=auth_headers(),
    )
    assert events_response.status_code == 200
    assert [event["event_type"] for event in events_response.json()["events"]] == [
        "run.created",
    ]

    services.run_registry.set_run_status(
        space_id=space_id,
        run_id=run_id,
        status="paused",
    )
    services.run_registry.set_progress(
        space_id=space_id,
        run_id=run_id,
        phase="approval",
        message="Paused pending resume.",
        progress_percent=0.4,
        completed_steps=1,
        total_steps=2,
        resume_point="approval_gate",
        metadata={"paused_by": "integration-test"},
    )

    resume_response = client.post(
        f"/v1/spaces/{space_id}/runs/{run_id}/resume",
        headers=auth_headers(),
        json={"reason": "integration resume", "metadata": {"source": "test"}},
    )
    assert resume_response.status_code == 200
    assert resume_response.json()["run"]["status"] == "completed"
    assert resume_response.json()["progress"]["progress_percent"] == 1.0

    final_events = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/events",
        headers=auth_headers(),
    )
    assert final_events.status_code == 200
    assert [event["event_type"] for event in final_events.json()["events"]] == [
        "run.created",
        "run.status_changed",
        "run.progress",
        "run.status_changed",
        "run.progress",
        "run.resumed",
        "run.status_changed",
        "run.progress",
        "run.executed",
        "run.status_changed",
        "run.progress",
    ]


@pytest.mark.integration
def test_transparency_endpoints_return_capabilities_and_policy_history(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    client = _build_client(session=db_session, runtime=runtime, services=services)
    space_id = str(uuid4())

    create_response = client.post(
        f"/v1/spaces/{space_id}/runs",
        headers=auth_headers(),
        json={
            "harness_id": "graph-chat",
            "title": "Transparency chat run",
            "input_payload": {
                "session_id": str(uuid4()),
                "question": "What is known about MED13?",
            },
        },
    )
    assert create_response.status_code == 201
    run_id = create_response.json()["id"]

    runtime.step_tool(
        run_id=run_id,
        tenant_id=space_id,
        tool_name="run_pubmed_search",
        arguments=RunPubMedSearchToolArgs(
            search_term="MED13 congenital heart disease",
            max_results=5,
        ),
        step_key="integration.pubmed_search",
    )
    append_manual_review_decision(
        space_id=UUID(space_id),
        run_id=run_id,
        tool_name="create_graph_claim",
        decision="promote",
        reason="Approved after integration review",
        artifact_key="graph_write_candidate_suggestions",
        metadata={"proposal_id": "proposal-integration-1"},
        artifact_store=services.artifact_store,
        run_registry=services.run_registry,
        runtime=runtime,
    )

    capabilities_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/capabilities",
        headers=auth_headers(role="viewer"),
    )
    assert capabilities_response.status_code == 200
    capabilities_payload = capabilities_response.json()
    assert capabilities_payload["artifact_key"] == "run_capabilities"
    visible_tool_names = {
        tool["tool_name"] for tool in capabilities_payload["visible_tools"]
    }
    assert "run_pubmed_search" in visible_tool_names

    policy_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/policy-decisions",
        headers=auth_headers(role="viewer"),
    )
    assert policy_response.status_code == 200
    policy_payload = policy_response.json()
    assert policy_payload["summary"]["tool_record_count"] == 1
    assert policy_payload["summary"]["manual_review_count"] == 1
    assert {record["decision_source"] for record in policy_payload["records"]} == {
        "tool",
        "manual_review",
    }


@pytest.mark.integration
def test_scheduler_tick_queues_runs_and_worker_executes_them_through_artana_lifecycle(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    schedule_store = cast("HarnessScheduleStore", services.schedule_store)
    run_registry = cast("ArtanaBackedHarnessRunRegistry", services.run_registry)
    artifact_store = cast("ArtanaBackedHarnessArtifactStore", services.artifact_store)
    space_id = str(uuid4())

    schedule = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Nightly refresh",
        cadence="daily",
        created_by=str(uuid4()),
        configuration={"seed_entity_ids": ["entity-1"], "source_type": "pubmed"},
        metadata={"owner": "integration-test"},
    )

    scheduler_result = asyncio.run(
        run_scheduler_tick(
            schedule_store=schedule_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            now=datetime(2026, 3, 14, 12, 0, tzinfo=UTC),
        ),
    )
    assert scheduler_result.due_schedule_count == 1
    assert len(scheduler_result.triggered_runs) == 1

    queued_runs = [
        run
        for run in list_queued_worker_runs(
            session=db_session,
            run_registry=run_registry,
        )
        if run.space_id == space_id
    ]
    assert len(queued_runs) == 1
    assert queued_runs[0].harness_id == "continuous-learning"

    worker_result = asyncio.run(
        run_worker_tick(
            candidate_runs=queued_runs,
            runtime=cast("GraphHarnessKernelRuntime", runtime),
            services=services,
        ),
    )
    assert worker_result.executed_run_count == 1
    assert worker_result.completed_run_count == 1
    assert worker_result.failed_run_count == 0

    refreshed_run = run_registry.get_run(
        space_id=space_id,
        run_id=queued_runs[0].id,
    )
    assert refreshed_run is not None
    assert refreshed_run.status == "completed"

    workspace = artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_runs[0].id,
    )
    assert workspace is not None
    assert workspace.snapshot["status"] == "completed"

    refreshed_schedule = schedule_store.get_schedule(
        space_id=space_id,
        schedule_id=schedule.id,
    )
    assert refreshed_schedule is not None
    assert refreshed_schedule.last_run_id == queued_runs[0].id


@pytest.mark.integration
def test_research_bootstrap_route_captures_graph_snapshot_and_stages_proposals(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(
        session=db_session,
        runtime=runtime,
        execution_override=_bootstrap_execution_override,
    )
    client = _build_client(session=db_session, runtime=runtime, services=services)
    space_id = str(uuid4())
    seed_entity_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/research-bootstrap/runs",
        headers=auth_headers(),
        json={
            "objective": "Bootstrap MED13 regulation evidence",
            "seed_entity_ids": [seed_entity_id],
        },
    )
    assert response.status_code == 201
    payload = response.json()
    run_id = payload["run"]["id"]
    assert payload["proposal_count"] == 1
    assert payload["graph_snapshot"]["source_run_id"] == run_id
    assert (
        payload["research_state"]["last_graph_snapshot_id"]
        == payload["graph_snapshot"]["id"]
    )
    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/artifacts",
        headers=auth_headers(),
    )
    assert artifacts_response.status_code == 200
    artifact_keys = {
        artifact["key"] for artifact in artifacts_response.json()["artifacts"]
    }
    assert {
        "graph_context_snapshot",
        "research_brief",
        "graph_summary",
        "source_inventory",
        "candidate_claim_pack",
    }.issubset(artifact_keys)


@pytest.mark.integration
def test_promote_proposal_creates_graph_claim_and_updates_artana_workspace(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    client = _build_client(session=db_session, runtime=runtime, services=services)
    space_id = str(uuid4())
    source_entity_id = str(uuid4())
    target_entity_id = str(uuid4())
    source_run = services.run_registry.create_run(
        space_id=space_id,
        harness_id="hypotheses",
        title="Promotion Source",
        input_payload={"seed_entity_ids": [source_entity_id]},
        graph_service_status="ok",
        graph_service_version="test-graph",
    )
    services.artifact_store.seed_for_run(run=source_run)
    proposal = services.proposal_store.create_proposals(
        space_id=space_id,
        run_id=source_run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="integration_test",
                source_key=f"{source_entity_id}:REGULATES:{target_entity_id}",
                title="Promote MED13 claim",
                summary="Synthetic promotion proposal.",
                confidence=0.88,
                ranking_score=0.95,
                reasoning_path={"reasoning": "Synthetic promotion reasoning."},
                evidence_bundle=[{"source_type": "db", "locator": source_entity_id}],
                payload=_candidate_claim_payload(
                    source_entity_id=source_entity_id,
                    target_entity_id=target_entity_id,
                ),
                metadata={"agent_run_id": "integration-promotion"},
            ),
        ),
    )[0]

    response = client.post(
        f"/v1/spaces/{space_id}/proposals/{proposal.id}/promote",
        headers=auth_headers(),
        json={"reason": "Integration promotion"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "promoted"
    graph_claim_id = payload["metadata"].get("graph_claim_id")
    assert isinstance(graph_claim_id, str)
    assert graph_claim_id != ""
    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=source_run.id,
    )
    assert workspace is not None
    assert workspace.snapshot["last_promoted_graph_claim_id"] == graph_claim_id


@pytest.mark.integration
def test_supervisor_parent_child_pause_and_resume_complete_through_child_approval(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(
        session=db_session,
        runtime=runtime,
        execution_override=_supervisor_execution_override,
    )
    client = _build_client(session=db_session, runtime=runtime, services=services)
    space_id = str(uuid4())
    seed_entity_id = str(uuid4())

    create_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        headers=auth_headers(),
        json={
            "objective": "Compose bootstrap and governed review",
            "seed_entity_ids": [seed_entity_id],
            "include_chat": False,
            "include_curation": True,
            "curation_source": "bootstrap",
        },
    )
    assert create_response.status_code == 201
    created_payload = create_response.json()
    parent_run_id = created_payload["run"]["id"]
    child_curation_run_id = created_payload["curation"]["run"]["id"]
    assert created_payload["run"]["status"] == "paused"
    assert created_payload["curation"]["pending_approval_count"] == 1

    approvals_response = client.get(
        f"/v1/spaces/{space_id}/runs/{child_curation_run_id}/approvals",
        headers=auth_headers(),
    )
    assert approvals_response.status_code == 200
    approval_key = approvals_response.json()["approvals"][0]["approval_key"]

    decide_response = client.post(
        f"/v1/spaces/{space_id}/runs/{child_curation_run_id}/approvals/{approval_key}",
        headers=auth_headers(),
        json={"decision": "approved", "reason": "Integration child approval"},
    )
    assert decide_response.status_code == 200

    resume_response = client.post(
        f"/v1/spaces/{space_id}/runs/{parent_run_id}/resume",
        headers=auth_headers(),
        json={"reason": "Resume parent after child approval"},
    )
    assert resume_response.status_code == 200
    assert resume_response.json()["run"]["status"] == "completed"
    child_run = services.run_registry.get_run(
        space_id=space_id,
        run_id=child_curation_run_id,
    )
    assert child_run is not None
    assert child_run.status == "completed"
