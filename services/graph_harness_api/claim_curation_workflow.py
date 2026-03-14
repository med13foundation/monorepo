"""Reusable claim-curation workflow helpers for composed harness runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from services.graph_harness_api.claim_curation_runtime import (
    build_approval_actions,
    build_approval_intent_artifact,
    build_curation_packet,
    build_review_plan,
    review_curatable_proposals,
)
from services.graph_harness_api.transparency import (
    append_skill_activity,
    ensure_run_transparency_seed,
)

if TYPE_CHECKING:
    from uuid import UUID

    from services.graph_harness_api.approval_store import HarnessApprovalStore
    from services.graph_harness_api.artifact_store import HarnessArtifactStore
    from services.graph_harness_api.claim_curation_runtime import (
        ClaimCurationProposalReview,
    )
    from services.graph_harness_api.composition import GraphHarnessKernelRuntime
    from services.graph_harness_api.graph_client import GraphApiGateway
    from services.graph_harness_api.proposal_store import (
        HarnessProposalRecord,
        HarnessProposalStore,
    )
    from services.graph_harness_api.run_registry import (
        HarnessRunRecord,
        HarnessRunRegistry,
    )
    from src.type_definitions.common import JSONObject


class ClaimCurationNoEligibleProposalsError(RuntimeError):
    """Raised when no selected proposals remain eligible for governed review."""


@dataclass(frozen=True, slots=True)
class ClaimCurationRunExecution:
    """One created claim-curation run paused at the approval gate."""

    run: HarnessRunRecord
    curation_packet: JSONObject
    review_plan: JSONObject
    approval_intent: JSONObject
    proposal_count: int
    blocked_proposal_count: int
    pending_approval_count: int


def build_claim_curation_run_input_payload(
    *,
    reviews: list[ClaimCurationProposalReview] | None = None,
    proposal_ids: list[str] | None = None,
    blocked_proposal_ids: list[str] | None = None,
) -> JSONObject:
    if reviews is not None:
        selected_proposal_ids = [
            review.proposal.id
            for review in reviews
            if getattr(review, "eligible_for_approval", False)
        ]
        blocked_ids = [
            review.proposal.id
            for review in reviews
            if not getattr(review, "eligible_for_approval", False)
        ]
    else:
        selected_proposal_ids = list(proposal_ids or [])
        blocked_ids = list(blocked_proposal_ids or [])
    return {
        "workflow": "claim_curation",
        "proposal_ids": selected_proposal_ids,
        "blocked_proposal_ids": blocked_ids,
    }


def queue_claim_curation_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    title: str,
    proposal_ids: list[str],
    graph_service_status: str,
    graph_service_version: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessRunRecord:
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="claim-curation",
        title=title,
        input_payload=build_claim_curation_run_input_payload(proposal_ids=proposal_ids),
        graph_service_status=graph_service_status,
        graph_service_version=graph_service_version,
    )
    artifact_store.seed_for_run(run=run)
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "queued",
            "claim_curation_proposal_count": len(proposal_ids),
            "blocked_claim_curation_proposal_count": 0,
        },
    )
    return run


def _json_int(payload: JSONObject, key: str) -> int:
    value = payload.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _json_list_length(payload: JSONObject, key: str) -> int:
    value = payload.get(key)
    if isinstance(value, list):
        return len(value)
    return 0


def execute_claim_curation_run_for_proposals(  # noqa: PLR0913
    *,
    space_id: UUID,
    proposals: list[HarnessProposalRecord],
    title: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    proposal_store: HarnessProposalStore,
    approval_store: HarnessApprovalStore,
    graph_api_gateway: GraphApiGateway,
    runtime: GraphHarnessKernelRuntime,
    existing_run: HarnessRunRecord | None = None,
) -> ClaimCurationRunExecution:
    """Create one approval-gated claim-curation run from selected proposals."""
    try:
        graph_health = graph_api_gateway.get_health()
        if existing_run is None:
            run = queue_claim_curation_run(
                space_id=space_id,
                title=title,
                proposal_ids=[proposal.id for proposal in proposals],
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
        reviews = review_curatable_proposals(
            runtime=runtime,
            run=run,
            space_id=space_id,
            proposals=proposals,
            proposal_store=proposal_store,
        )
    finally:
        graph_api_gateway.close()

    append_skill_activity(
        space_id=space_id,
        run_id=run.id,
        skill_names=("graph_harness.claim_validation",),
        source_run_id=run.id,
        source_kind="claim_curation",
        artifact_store=artifact_store,
        run_registry=run_registry,
        runtime=runtime,
    )

    if not any(review.eligible_for_approval for review in reviews):
        error_message = (
            "No eligible proposals remain for claim curation after duplicate, "
            "conflict, and invariant checks."
        )
        raise ClaimCurationNoEligibleProposalsError(error_message)

    curation_packet = build_curation_packet(reviews=reviews)
    review_plan = build_review_plan(reviews=reviews)
    approval_actions = build_approval_actions(reviews=reviews)
    approval_summary = f"Review {len(approval_actions)} eligible proposal(s) for graph claim promotion."

    updated_run = run_registry.replace_run_input_payload(
        space_id=space_id,
        run_id=run.id,
        input_payload=build_claim_curation_run_input_payload(reviews=reviews),
    )
    if updated_run is not None:
        run = updated_run
    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="running")
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="review",
        message="Built claim-curation review plan.",
        progress_percent=0.35,
        completed_steps=1,
        total_steps=2,
        metadata={"proposal_count": len(proposals)},
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "running",
            "claim_curation_proposal_count": len(proposals),
            "blocked_claim_curation_proposal_count": _json_int(
                curation_packet,
                "blocked_proposal_count",
            ),
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="curation_packet",
        media_type="application/json",
        content=curation_packet,
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="review_plan",
        media_type="application/json",
        content=review_plan,
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="claim_curation.review_built",
        message=f"Built review plan for {len(proposals)} proposal(s).",
        payload={
            "proposal_ids": [proposal.id for proposal in proposals],
            "warning_count": _json_list_length(review_plan, "warnings"),
            "blocked_proposal_count": _json_int(
                review_plan,
                "blocked_proposal_count",
            ),
        },
        progress_percent=0.35,
    )

    approval_store.upsert_intent(
        space_id=space_id,
        run_id=run.id,
        summary=approval_summary,
        proposed_actions=approval_actions,
        metadata={
            "intent_kind": "claim_curation",
            "proposal_ids": [
                review.proposal.id for review in reviews if review.eligible_for_approval
            ],
            "blocked_proposal_ids": [
                review.proposal.id
                for review in reviews
                if not review.eligible_for_approval
            ],
        },
    )
    approvals = approval_store.list_approvals(space_id=space_id, run_id=run.id)
    approval_intent = build_approval_intent_artifact(
        run_id=run.id,
        summary=approval_summary,
        actions=approval_actions,
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="approval_intent",
        media_type="application/json",
        content=approval_intent,
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="run.intent_recorded",
        message="Run intent plan recorded.",
        payload={
            "summary": approval_summary,
            "approval_count": len(approvals),
        },
        progress_percent=0.5,
    )
    paused_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="paused",
    )
    paused_progress = run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="approval",
        message="Run paused pending curator approval.",
        progress_percent=0.5,
        completed_steps=1,
        total_steps=2,
        resume_point="approval_gate",
        metadata={"pending_approvals": len(approvals)},
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="run.paused",
        message="Run paused at approval gate.",
        payload={"pending_approvals": len(approvals)},
        progress_percent=(
            paused_progress.progress_percent if paused_progress is not None else 0.5
        ),
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "paused",
            "resume_point": "approval_gate",
            "pending_approvals": len(approvals),
            "blocked_proposal_count": _json_int(
                review_plan,
                "blocked_proposal_count",
            ),
            "last_curation_packet_key": "curation_packet",
            "last_review_plan_key": "review_plan",
            "last_approval_intent_key": "approval_intent",
        },
    )
    return ClaimCurationRunExecution(
        run=paused_run or run,
        curation_packet=curation_packet,
        review_plan=review_plan,
        approval_intent=approval_intent,
        proposal_count=len(proposals),
        blocked_proposal_count=_json_int(review_plan, "blocked_proposal_count"),
        pending_approval_count=len(approvals),
    )


__all__ = [
    "ClaimCurationNoEligibleProposalsError",
    "ClaimCurationRunExecution",
    "build_claim_curation_run_input_payload",
    "execute_claim_curation_run_for_proposals",
    "queue_claim_curation_run",
]
