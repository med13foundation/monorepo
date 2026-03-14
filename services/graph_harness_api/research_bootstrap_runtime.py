"""Research-bootstrap runtime for graph-harness workflows."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from fastapi import HTTPException, status

from services.graph_harness_api.graph_connection_runtime import (
    HarnessGraphConnectionRequest,
)
from services.graph_harness_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,
)
from services.graph_harness_api.ranking import rank_candidate_claim
from services.graph_harness_api.tool_runtime import (
    run_capture_graph_snapshot,
    run_list_graph_claims,
    run_list_graph_hypotheses,
)
from services.graph_harness_api.transparency import ensure_run_transparency_seed
from src.infrastructure.graph_service.errors import GraphServiceClientError
from src.type_definitions.graph_service_contracts import KernelGraphDocumentResponse

if TYPE_CHECKING:
    from services.graph_harness_api.artifact_store import HarnessArtifactStore
    from services.graph_harness_api.composition import GraphHarnessKernelRuntime
    from services.graph_harness_api.graph_client import GraphApiGateway
    from services.graph_harness_api.graph_connection_runtime import (
        HarnessGraphConnectionRunner,
    )
    from services.graph_harness_api.graph_snapshot import (
        HarnessGraphSnapshotRecord,
        HarnessGraphSnapshotStore,
    )
    from services.graph_harness_api.proposal_store import HarnessProposalStore
    from services.graph_harness_api.research_state import (
        HarnessResearchStateRecord,
        HarnessResearchStateStore,
    )
    from services.graph_harness_api.run_registry import (
        HarnessRunRecord,
        HarnessRunRegistry,
    )
    from services.graph_harness_api.schedule_store import HarnessScheduleStore
    from src.domain.agents.contracts.graph_connection import GraphConnectionContract
    from src.type_definitions.common import JSONObject
    from src.type_definitions.graph_service_contracts import (
        HypothesisResponse,
        KernelRelationClaimResponse,
    )

_TOTAL_PROGRESS_STEPS = 4
_BLANK_SEED_ENTITY_IDS_ERROR = "seed_entity_ids cannot contain blank values"
_INVALID_SEED_ENTITY_IDS_ERROR = "seed_entity_ids must contain valid UUID values"


@dataclass(frozen=True, slots=True)
class ResearchBootstrapExecutionResult:
    """One completed research-bootstrap execution result."""

    run: HarnessRunRecord
    graph_snapshot: HarnessGraphSnapshotRecord
    research_state: HarnessResearchStateRecord
    research_brief: JSONObject
    graph_summary: JSONObject
    source_inventory: JSONObject
    proposal_records: list[HarnessProposalRecord]
    pending_questions: list[str]
    errors: list[str]


def build_research_bootstrap_run_input_payload(  # noqa: PLR0913
    *,
    objective: str | None,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_hypotheses: int,
    model_id: str | None,
) -> JSONObject:
    """Build the canonical queued-run payload for research bootstrap."""
    return {
        "objective": objective,
        "seed_entity_ids": list(seed_entity_ids),
        "source_type": source_type,
        "relation_types": list(relation_types or []),
        "max_depth": max_depth,
        "max_hypotheses": max_hypotheses,
        "model_id": model_id,
    }


def queue_research_bootstrap_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    title: str,
    objective: str | None,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_hypotheses: int,
    model_id: str | None,
    graph_service_status: str,
    graph_service_version: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessRunRecord:
    """Create a queued research-bootstrap run without executing it yet."""
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="research-bootstrap",
        title=title,
        input_payload=build_research_bootstrap_run_input_payload(
            objective=objective,
            seed_entity_ids=seed_entity_ids,
            source_type=source_type,
            relation_types=relation_types,
            max_depth=max_depth,
            max_hypotheses=max_hypotheses,
            model_id=model_id,
        ),
        graph_service_status=graph_service_status,
        graph_service_version=graph_service_version,
    )
    artifact_store.seed_for_run(run=run)
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "queued",
            "objective": objective,
            "seed_entity_ids": list(seed_entity_ids),
        },
    )
    return run


def normalize_bootstrap_seed_entity_ids(seed_entity_ids: list[str] | None) -> list[str]:
    """Return normalized seed entity identifiers for bootstrap runs."""
    if seed_entity_ids is None:
        return []
    normalized_ids: list[str] = []
    seen_ids: set[str] = set()
    for value in seed_entity_ids:
        normalized = value.strip()
        if normalized == "":
            raise ValueError(_BLANK_SEED_ENTITY_IDS_ERROR)
        try:
            UUID(normalized)
        except ValueError as exc:
            raise ValueError(_INVALID_SEED_ENTITY_IDS_ERROR) from exc
        if normalized in seen_ids:
            continue
        normalized_ids.append(normalized)
        seen_ids.add(normalized)
    return normalized_ids


def _serialize_hypothesis_text(hypothesis: HypothesisResponse) -> str:
    if isinstance(hypothesis.claim_text, str) and hypothesis.claim_text.strip() != "":
        return hypothesis.claim_text.strip()
    source_label = hypothesis.source_label or "Unknown source"
    target_label = hypothesis.target_label or "Unknown target"
    return f"{source_label} {hypothesis.relation_type} {target_label}"


def _normalized_unique_strings(values: list[str]) -> list[str]:
    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        normalized = value.strip()
        if normalized == "" or normalized in seen_values:
            continue
        normalized_values.append(normalized)
        seen_values.add(normalized)
    return normalized_values


def _collect_candidate_claims(
    outcomes: list[GraphConnectionContract],
    *,
    max_candidates: int,
) -> tuple[list[JSONObject], list[str]]:
    candidates: list[JSONObject] = []
    errors: list[str] = []
    for outcome in outcomes:
        if outcome.decision != "generated" and not outcome.proposed_relations:
            errors.append(
                f"seed:{outcome.seed_entity_id}:no_generated_relations:{outcome.decision}",
            )
        for relation in outcome.proposed_relations:
            if len(candidates) >= max_candidates:
                break
            candidates.append(
                {
                    "seed_entity_id": outcome.seed_entity_id,
                    "source_entity_id": relation.source_id,
                    "relation_type": relation.relation_type,
                    "target_entity_id": relation.target_id,
                    "confidence": relation.confidence,
                    "evidence_summary": relation.evidence_summary,
                    "reasoning": relation.reasoning,
                    "agent_run_id": outcome.agent_run_id,
                    "source_type": outcome.source_type,
                },
            )
    return candidates, errors


def _build_candidate_claim_proposals(
    outcomes: list[GraphConnectionContract],
    *,
    max_candidates: int,
) -> tuple[HarnessProposalDraft, ...]:
    proposals: list[HarnessProposalDraft] = []
    for outcome in outcomes:
        for relation in outcome.proposed_relations:
            if len(proposals) >= max_candidates:
                break
            ranking = rank_candidate_claim(
                confidence=relation.confidence,
                supporting_document_count=relation.supporting_document_count,
                evidence_reference_count=len(relation.supporting_provenance_ids),
            )
            evidence_bundle: list[JSONObject] = [
                evidence.model_dump(mode="json") for evidence in outcome.evidence
            ]
            evidence_bundle.append(
                {
                    "source_type": "bootstrap_relation",
                    "locator": (
                        f"{relation.source_id}:{relation.relation_type}:"
                        f"{relation.target_id}"
                    ),
                    "excerpt": relation.evidence_summary,
                    "relevance": relation.confidence,
                },
            )
            proposals.append(
                HarnessProposalDraft(
                    proposal_type="candidate_claim",
                    source_kind="research_bootstrap",
                    source_key=(
                        f"{outcome.seed_entity_id}:{relation.source_id}:"
                        f"{relation.relation_type}:{relation.target_id}"
                    ),
                    title=(
                        f"Candidate claim: {relation.source_id} "
                        f"{relation.relation_type} {relation.target_id}"
                    ),
                    summary=relation.evidence_summary,
                    confidence=relation.confidence,
                    ranking_score=ranking.score,
                    reasoning_path={
                        "seed_entity_id": outcome.seed_entity_id,
                        "source_entity_id": relation.source_id,
                        "relation_type": relation.relation_type,
                        "target_entity_id": relation.target_id,
                        "reasoning": relation.reasoning,
                        "agent_run_id": outcome.agent_run_id,
                    },
                    evidence_bundle=evidence_bundle,
                    payload={
                        "proposed_claim_type": relation.relation_type,
                        "proposed_subject": relation.source_id,
                        "proposed_object": relation.target_id,
                        "evidence_tier": relation.evidence_tier,
                        "supporting_document_count": relation.supporting_document_count,
                        "supporting_provenance_ids": relation.supporting_provenance_ids,
                    },
                    metadata={
                        "seed_entity_id": outcome.seed_entity_id,
                        "agent_run_id": outcome.agent_run_id,
                        "source_type": outcome.source_type,
                        **ranking.metadata,
                    },
                ),
            )
    return tuple(proposals)


def _proposal_artifact_payload(
    proposals: list[HarnessProposalRecord],
) -> JSONObject:
    return {
        "proposal_count": len(proposals),
        "proposal_ids": [proposal.id for proposal in proposals],
        "proposals": [
            {
                "id": proposal.id,
                "run_id": proposal.run_id,
                "proposal_type": proposal.proposal_type,
                "source_kind": proposal.source_kind,
                "source_key": proposal.source_key,
                "title": proposal.title,
                "summary": proposal.summary,
                "status": proposal.status,
                "confidence": proposal.confidence,
                "ranking_score": proposal.ranking_score,
                "payload": proposal.payload,
                "metadata": proposal.metadata,
                "created_at": proposal.created_at.isoformat(),
            }
            for proposal in proposals
        ],
    }


def _graph_summary_payload(  # noqa: PLR0913
    *,
    objective: str | None,
    seed_entity_ids: list[str],
    graph_document: KernelGraphDocumentResponse,
    claims: list[KernelRelationClaimResponse],
    current_hypotheses: list[str],
) -> JSONObject:
    counts = graph_document.meta.counts.model_dump(mode="json")
    return {
        "objective": objective,
        "mode": graph_document.meta.mode,
        "seed_entity_ids": seed_entity_ids,
        "graph_document_counts": counts,
        "graph_node_count": len(graph_document.nodes),
        "graph_edge_count": len(graph_document.edges),
        "claim_count": len(claims),
        "hypothesis_count": len(current_hypotheses),
        "hypotheses": current_hypotheses[:10],
        "sample_labels": [node.label for node in graph_document.nodes[:10]],
    }


def _graph_snapshot_payload(
    *,
    snapshot: HarnessGraphSnapshotRecord,
    graph_summary: JSONObject,
) -> JSONObject:
    return {
        "snapshot_id": snapshot.id,
        "space_id": snapshot.space_id,
        "source_run_id": snapshot.source_run_id,
        "claim_ids": list(snapshot.claim_ids),
        "relation_ids": list(snapshot.relation_ids),
        "graph_document_hash": snapshot.graph_document_hash,
        "summary": graph_summary,
        "metadata": snapshot.metadata,
        "created_at": snapshot.created_at.isoformat(),
        "updated_at": snapshot.updated_at.isoformat(),
    }


def _build_pending_questions(
    *,
    objective: str | None,
    proposals: list[HarnessProposalRecord],
    max_questions: int,
) -> list[str]:
    questions: list[str] = []
    if isinstance(objective, str) and objective.strip() != "":
        questions.append(f"What evidence most directly advances: {objective.strip()}?")
    for proposal in proposals:
        subject = proposal.payload.get("proposed_subject")
        relation_type = proposal.payload.get("proposed_claim_type")
        target = proposal.payload.get("proposed_object")
        if not (
            isinstance(subject, str)
            and isinstance(relation_type, str)
            and isinstance(target, str)
        ):
            continue
        questions.append(
            f"What evidence best supports {subject} {relation_type} {target}?",
        )
        if len(questions) >= max_questions:
            break
    if not questions:
        questions.append("Which seed entities should be expanded next?")
    return _normalized_unique_strings(questions)[:max_questions]


def _source_inventory_payload(
    *,
    claims: list[KernelRelationClaimResponse],
    current_hypotheses: list[str],
    outcomes: list[GraphConnectionContract],
) -> JSONObject:
    agent_run_ids = _normalized_unique_strings(
        [
            outcome.agent_run_id
            for outcome in outcomes
            if isinstance(outcome.agent_run_id, str)
        ],
    )
    source_types = _normalized_unique_strings(
        [claim.source_type for claim in claims]
        + [outcome.source_type for outcome in outcomes],
    )
    supporting_document_count = sum(
        relation.supporting_document_count
        for outcome in outcomes
        for relation in outcome.proposed_relations
    )
    return {
        "graph_claim_count": len(claims),
        "current_hypothesis_count": len(current_hypotheses),
        "source_types": source_types,
        "agent_run_ids": agent_run_ids,
        "supporting_document_count": supporting_document_count,
    }


def _research_brief_payload(  # noqa: PLR0913
    *,
    objective: str | None,
    graph_summary: JSONObject,
    proposals: list[HarnessProposalRecord],
    pending_questions: list[str],
    source_inventory: JSONObject,
) -> JSONObject:
    return {
        "objective": objective,
        "graph_summary": graph_summary,
        "source_inventory": source_inventory,
        "proposal_count": len(proposals),
        "top_candidate_claims": [
            {
                "proposal_id": proposal.id,
                "title": proposal.title,
                "summary": proposal.summary,
                "ranking_score": proposal.ranking_score,
            }
            for proposal in proposals[:5]
        ],
        "pending_questions": pending_questions,
    }


def _snapshot_claim_ids(
    *,
    graph_document: KernelGraphDocumentResponse,
    claims: list[KernelRelationClaimResponse],
    current_hypotheses: list[HypothesisResponse],
) -> list[str]:
    candidate_ids = [
        node.resource_id for node in graph_document.nodes if node.kind == "CLAIM"
    ]
    candidate_ids.extend(str(claim.id) for claim in claims)
    candidate_ids.extend(str(hypothesis.claim_id) for hypothesis in current_hypotheses)
    return _normalized_unique_strings(candidate_ids)


def _snapshot_relation_ids(graph_document: KernelGraphDocumentResponse) -> list[str]:
    candidate_ids = [
        edge.resource_id
        for edge in graph_document.edges
        if edge.kind == "CANONICAL_RELATION" and isinstance(edge.resource_id, str)
    ]
    return _normalized_unique_strings(candidate_ids)


def _graph_document_hash(graph_document: KernelGraphDocumentResponse) -> str:
    payload = graph_document.model_dump(mode="json")
    encoded_payload = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded_payload).hexdigest()


def _mark_failed_run(
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    error_message: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> None:
    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="failed")
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="failed",
        message=error_message,
        progress_percent=0.0,
        completed_steps=0,
        total_steps=_TOTAL_PROGRESS_STEPS,
        metadata={"error": error_message},
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "failed", "error": error_message},
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="research_bootstrap_error",
        media_type="application/json",
        content={"error": error_message},
    )


async def execute_research_bootstrap_run(  # noqa: PLR0913, PLR0915
    *,
    space_id: UUID,
    title: str,
    objective: str | None,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_hypotheses: int,
    model_id: str | None,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    graph_api_gateway: GraphApiGateway,
    graph_connection_runner: HarnessGraphConnectionRunner,
    proposal_store: HarnessProposalStore,
    research_state_store: HarnessResearchStateStore,
    graph_snapshot_store: HarnessGraphSnapshotStore,
    schedule_store: HarnessScheduleStore,
    runtime: GraphHarnessKernelRuntime,
    existing_run: HarnessRunRecord | None = None,
) -> ResearchBootstrapExecutionResult:
    """Bootstrap one research space into a durable harness memory state."""
    run: HarnessRunRecord | None = None

    try:
        graph_health = graph_api_gateway.get_health()
        if existing_run is None:
            run = queue_research_bootstrap_run(
                space_id=space_id,
                title=title,
                objective=objective,
                seed_entity_ids=seed_entity_ids,
                source_type=source_type,
                relation_types=relation_types,
                max_depth=max_depth,
                max_hypotheses=max_hypotheses,
                model_id=model_id,
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
                run_registry=run_registry,
                artifact_store=artifact_store,
            )
            ensure_run_transparency_seed(
                run=run,
                artifact_store=artifact_store,
                runtime=runtime,
            )
        else:
            run = existing_run
            if artifact_store.get_workspace(space_id=space_id, run_id=run.id) is None:
                artifact_store.seed_for_run(run=run)
            ensure_run_transparency_seed(
                run=run,
                artifact_store=artifact_store,
                runtime=runtime,
            )
        run_registry.set_run_status(space_id=space_id, run_id=run.id, status="running")
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "running",
                "objective": objective,
                "seed_entity_ids": seed_entity_ids,
            },
        )
        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="graph_snapshot",
            message="Capturing graph context snapshot.",
            progress_percent=0.25,
            completed_steps=1,
            total_steps=_TOTAL_PROGRESS_STEPS,
        )
        graph_snapshot_payload = run_capture_graph_snapshot(
            runtime=runtime,
            run=run,
            space_id=str(space_id),
            seed_entity_ids=seed_entity_ids,
            depth=max_depth,
            top_k=max(25, max_hypotheses),
            step_key="bootstrap.graph_snapshot_capture",
        )
        graph_document = KernelGraphDocumentResponse.model_validate_json(
            json.dumps(
                graph_snapshot_payload,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
        )
        claim_list = run_list_graph_claims(
            runtime=runtime,
            run=run,
            space_id=str(space_id),
            claim_status=None,
            limit=max(50, max_hypotheses * 5),
            step_key="bootstrap.graph_claims",
        )
        hypothesis_list = run_list_graph_hypotheses(
            runtime=runtime,
            run=run,
            space_id=str(space_id),
            limit=max(25, max_hypotheses),
            step_key="bootstrap.graph_hypotheses",
        )
        current_hypotheses = [
            _serialize_hypothesis_text(hypothesis)
            for hypothesis in hypothesis_list.hypotheses[:10]
        ]
        graph_summary = _graph_summary_payload(
            objective=objective,
            seed_entity_ids=seed_entity_ids,
            graph_document=graph_document,
            claims=claim_list.claims,
            current_hypotheses=current_hypotheses,
        )
        graph_snapshot = graph_snapshot_store.create_snapshot(
            space_id=space_id,
            source_run_id=run.id,
            claim_ids=_snapshot_claim_ids(
                graph_document=graph_document,
                claims=claim_list.claims,
                current_hypotheses=hypothesis_list.hypotheses,
            ),
            relation_ids=_snapshot_relation_ids(graph_document),
            graph_document_hash=_graph_document_hash(graph_document),
            summary=graph_summary,
            metadata={
                "mode": graph_document.meta.mode,
                "seed_entity_ids": seed_entity_ids,
            },
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="graph_context_snapshot",
            media_type="application/json",
            content=_graph_snapshot_payload(
                snapshot=graph_snapshot,
                graph_summary=graph_summary,
            ),
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="graph_summary",
            media_type="application/json",
            content=graph_summary,
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="run.graph_snapshot_captured",
            message="Captured graph context snapshot.",
            payload={"snapshot_id": graph_snapshot.id},
            progress_percent=0.25,
        )

        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="candidate_claims",
            message="Generating initial candidate claims from bootstrap seeds.",
            progress_percent=0.55,
            completed_steps=2,
            total_steps=_TOTAL_PROGRESS_STEPS,
            metadata={"snapshot_id": graph_snapshot.id},
        )
        outcomes = [
            await graph_connection_runner.run(
                HarnessGraphConnectionRequest(
                    seed_entity_id=seed_entity_id,
                    research_space_id=str(space_id),
                    source_type=source_type,
                    source_id=None,
                    model_id=model_id,
                    relation_types=relation_types,
                    max_depth=max_depth,
                    shadow_mode=True,
                    pipeline_run_id=None,
                    research_space_settings={},
                ),
            )
            for seed_entity_id in seed_entity_ids
        ]
        candidate_claims, errors = _collect_candidate_claims(
            outcomes,
            max_candidates=max_hypotheses,
        )
        proposal_records = proposal_store.create_proposals(
            space_id=space_id,
            run_id=run.id,
            proposals=_build_candidate_claim_proposals(
                outcomes,
                max_candidates=max_hypotheses,
            ),
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="candidate_claim_pack",
            media_type="application/json",
            content=_proposal_artifact_payload(proposal_records),
        )
        source_inventory = _source_inventory_payload(
            claims=claim_list.claims,
            current_hypotheses=current_hypotheses,
            outcomes=outcomes,
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="source_inventory",
            media_type="application/json",
            content=source_inventory,
        )
        pending_questions = _build_pending_questions(
            objective=objective,
            proposals=proposal_records,
            max_questions=5,
        )
        research_brief = _research_brief_payload(
            objective=objective,
            graph_summary=graph_summary,
            proposals=proposal_records,
            pending_questions=pending_questions,
            source_inventory=source_inventory,
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="research_brief",
            media_type="application/json",
            content=research_brief,
        )
        active_schedules = [
            schedule.id
            for schedule in schedule_store.list_schedules(space_id=space_id)
            if schedule.status == "active"
        ]
        existing_state = research_state_store.get_state(space_id=space_id)
        explored_questions = _normalized_unique_strings(
            (
                list(existing_state.explored_questions)
                if existing_state is not None
                else []
            )
            + (
                [objective]
                if isinstance(objective, str) and objective.strip() != ""
                else []
            ),
        )
        research_state = research_state_store.upsert_state(
            space_id=space_id,
            objective=objective,
            current_hypotheses=current_hypotheses,
            explored_questions=explored_questions,
            pending_questions=pending_questions,
            last_graph_snapshot_id=graph_snapshot.id,
            last_learning_cycle_at=(
                existing_state.last_learning_cycle_at
                if existing_state is not None
                else None
            ),
            active_schedules=active_schedules,
            confidence_model={
                "proposal_ranking_model": "candidate_claim_v1",
                "graph_snapshot_model": "graph_document_v1",
                "bootstrap_runtime_model": "research_bootstrap_v1",
            },
            budget_policy=(
                existing_state.budget_policy if existing_state is not None else {}
            ),
            metadata={
                "last_bootstrap_run_id": run.id,
                "proposal_count": len(proposal_records),
                "candidate_claim_count": len(candidate_claims),
                "error_count": len(errors),
            },
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="run.research_state_updated",
            message="Updated structured research state.",
            payload={
                "last_graph_snapshot_id": graph_snapshot.id,
                "pending_question_count": len(pending_questions),
            },
            progress_percent=0.8,
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="run.proposals_staged",
            message=f"Staged {len(proposal_records)} bootstrap proposal(s).",
            payload={
                "proposal_count": len(proposal_records),
                "artifact_key": "candidate_claim_pack",
            },
            progress_percent=0.8,
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "completed",
                "last_graph_snapshot_id": graph_snapshot.id,
                "last_graph_context_snapshot_key": "graph_context_snapshot",
                "last_graph_summary_key": "graph_summary",
                "last_research_brief_key": "research_brief",
                "last_source_inventory_key": "source_inventory",
                "last_candidate_claim_pack_key": "candidate_claim_pack",
                "proposal_count": len(proposal_records),
                "proposal_counts": {
                    "pending_review": len(proposal_records),
                    "promoted": 0,
                    "rejected": 0,
                },
                "pending_question_count": len(pending_questions),
            },
        )
        updated_run = run_registry.set_run_status(
            space_id=space_id,
            run_id=run.id,
            status="completed",
        )
        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="completed",
            message="Research bootstrap completed.",
            progress_percent=1.0,
            completed_steps=_TOTAL_PROGRESS_STEPS,
            total_steps=_TOTAL_PROGRESS_STEPS,
            metadata={
                "snapshot_id": graph_snapshot.id,
                "proposal_count": len(proposal_records),
                "research_state_space_id": research_state.space_id,
            },
        )
        return ResearchBootstrapExecutionResult(
            run=run if updated_run is None else updated_run,
            graph_snapshot=graph_snapshot,
            research_state=research_state,
            research_brief=research_brief,
            graph_summary=graph_summary,
            source_inventory=source_inventory,
            proposal_records=proposal_records,
            pending_questions=pending_questions,
            errors=errors,
        )
    except GraphServiceClientError:
        if run is not None:
            _mark_failed_run(
                space_id=space_id,
                run=run,
                error_message="Graph API unavailable during research bootstrap.",
                run_registry=run_registry,
                artifact_store=artifact_store,
            )
        raise
    except Exception as exc:
        if run is not None:
            _mark_failed_run(
                space_id=space_id,
                run=run,
                error_message=str(exc),
                run_registry=run_registry,
                artifact_store=artifact_store,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Research bootstrap run failed: {exc}",
        ) from exc
    finally:
        graph_api_gateway.close()


__all__ = [
    "ResearchBootstrapExecutionResult",
    "build_research_bootstrap_run_input_payload",
    "execute_research_bootstrap_run",
    "normalize_bootstrap_seed_entity_ids",
    "queue_research_bootstrap_run",
]
