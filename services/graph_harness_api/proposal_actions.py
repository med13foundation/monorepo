"""Shared proposal promotion and rejection helpers for harness workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status

from services.graph_harness_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from services.graph_harness_api.graph_client import GraphApiGateway  # noqa: TC001
from services.graph_harness_api.run_registry import HarnessRunRegistry  # noqa: TC001
from src.infrastructure.graph_service.errors import GraphServiceClientError
from src.type_definitions.common import JSONObject  # noqa: TC001
from src.type_definitions.graph_service_contracts import (
    CreateManualHypothesisRequest,
    KernelRelationClaimCreateRequest,
)

if TYPE_CHECKING:
    from services.graph_harness_api.proposal_store import (
        HarnessProposalRecord,
        HarnessProposalStore,
    )


def require_proposal(
    *,
    space_id: UUID,
    proposal_id: UUID | str,
    proposal_store: HarnessProposalStore,
) -> HarnessProposalRecord:
    """Return one proposal from the store or raise a typed 404."""
    proposal = proposal_store.get_proposal(space_id=space_id, proposal_id=proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal '{proposal_id}' not found in space '{space_id}'",
        )
    return proposal


def status_counts(
    proposals: list[HarnessProposalRecord],
) -> dict[str, int]:
    """Count proposal decisions for one run snapshot."""
    counts = {
        "pending_review": 0,
        "promoted": 0,
        "rejected": 0,
    }
    for proposal in proposals:
        counts[proposal.status] = counts.get(proposal.status, 0) + 1
    return counts


def _require_payload_string(
    payload: JSONObject,
    *,
    field_name: str,
) -> str:
    value = payload.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Proposal payload is missing required '{field_name}' for graph promotion"
        ),
    )


def _require_payload_string_list(
    payload: JSONObject,
    *,
    field_name: str,
) -> list[str]:
    value = payload.get(field_name)
    if not isinstance(value, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Proposal payload is missing required '{field_name}' list",
        )
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        trimmed = item.strip()
        if trimmed == "":
            continue
        normalized.append(trimmed)
    if normalized:
        return normalized
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Proposal payload is missing required '{field_name}' list",
    )


def _require_payload_uuid(
    payload: JSONObject,
    *,
    field_name: str,
) -> UUID:
    value = _require_payload_string(payload, field_name=field_name)
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Proposal payload field '{field_name}' must be a UUID",
        ) from exc


def build_graph_claim_request(
    *,
    proposal: HarnessProposalRecord,
    request_metadata: JSONObject,
) -> KernelRelationClaimCreateRequest:
    """Build one graph-claim creation request from a harness proposal."""
    if proposal.proposal_type != "candidate_claim":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Proposal type '{proposal.proposal_type}' is not supported for "
                "graph claim promotion"
            ),
        )
    reasoning = proposal.reasoning_path.get("reasoning")
    agent_run_id = proposal.metadata.get("agent_run_id")
    return KernelRelationClaimCreateRequest(
        source_entity_id=_require_payload_uuid(
            proposal.payload,
            field_name="proposed_subject",
        ),
        target_entity_id=_require_payload_uuid(
            proposal.payload,
            field_name="proposed_object",
        ),
        relation_type=_require_payload_string(
            proposal.payload,
            field_name="proposed_claim_type",
        ),
        confidence=proposal.confidence,
        claim_text=(
            reasoning
            if isinstance(reasoning, str) and reasoning.strip() != ""
            else proposal.summary
        ),
        evidence_summary=proposal.summary,
        source_document_ref=f"harness_proposal:{proposal.id}",
        agent_run_id=agent_run_id if isinstance(agent_run_id, str) else None,
        metadata={
            **proposal.metadata,
            **request_metadata,
            "proposal_id": proposal.id,
            "harness_run_id": proposal.run_id,
            "proposal_type": proposal.proposal_type,
            "source_kind": proposal.source_kind,
            "source_key": proposal.source_key,
            "reasoning_path": proposal.reasoning_path,
            "evidence_bundle": proposal.evidence_bundle,
        },
    )


def build_manual_hypothesis_request(
    *,
    proposal: HarnessProposalRecord,
) -> CreateManualHypothesisRequest:
    """Build one manual-hypothesis creation request from a mechanism proposal."""
    if proposal.proposal_type != "mechanism_candidate":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Proposal type '{proposal.proposal_type}' is not supported for "
                "manual hypothesis promotion"
            ),
        )
    return CreateManualHypothesisRequest(
        statement=_require_payload_string(
            proposal.payload,
            field_name="hypothesis_statement",
        ),
        rationale=_require_payload_string(
            proposal.payload,
            field_name="hypothesis_rationale",
        ),
        seed_entity_ids=_require_payload_string_list(
            proposal.payload,
            field_name="seed_entity_ids",
        ),
        source_type=_require_payload_string(
            proposal.payload,
            field_name="source_type",
        ),
    )


def promote_to_graph_claim(
    *,
    space_id: UUID,
    proposal: HarnessProposalRecord,
    request_metadata: JSONObject,
    graph_api_gateway: GraphApiGateway,
) -> JSONObject:
    """Create one unresolved graph claim from a staged harness proposal."""
    try:
        graph_claim = graph_api_gateway.create_claim(
            space_id=str(space_id),
            request=build_graph_claim_request(
                proposal=proposal,
                request_metadata=request_metadata,
            ),
        )
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.detail or str(exc),
        ) from exc
    return {
        "graph_claim_id": str(graph_claim.id),
        "graph_claim_status": graph_claim.claim_status,
        "graph_claim_validation_state": graph_claim.validation_state,
        "graph_claim_persistability": graph_claim.persistability,
        "graph_claim_polarity": graph_claim.polarity,
    }


def promote_to_graph_hypothesis(
    *,
    space_id: UUID,
    proposal: HarnessProposalRecord,
    graph_api_gateway: GraphApiGateway,
) -> JSONObject:
    """Create one manual graph hypothesis from a staged mechanism proposal."""
    try:
        hypothesis = graph_api_gateway.create_manual_hypothesis(
            space_id=space_id,
            request=build_manual_hypothesis_request(proposal=proposal),
        )
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.detail or str(exc),
        ) from exc
    return {
        "graph_hypothesis_claim_id": str(hypothesis.claim_id),
        "graph_hypothesis_origin": hypothesis.origin,
        "graph_hypothesis_claim_status": hypothesis.claim_status,
        "graph_hypothesis_validation_state": hypothesis.validation_state,
        "graph_hypothesis_persistability": hypothesis.persistability,
    }


def decide_proposal(  # noqa: PLR0913
    *,
    space_id: UUID,
    proposal_id: UUID | str,
    decision_status: str,
    decision_reason: str | None,
    request_metadata: JSONObject,
    proposal_store: HarnessProposalStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    decision_metadata: JSONObject | None = None,
    event_payload: JSONObject | None = None,
    workspace_patch: JSONObject | None = None,
) -> HarnessProposalRecord:
    """Persist one proposal decision and update its originating run state."""
    proposal = require_proposal(
        space_id=space_id,
        proposal_id=proposal_id,
        proposal_store=proposal_store,
    )
    merged_metadata = {
        **request_metadata,
        **(decision_metadata or {}),
    }
    try:
        updated = proposal_store.decide_proposal(
            space_id=space_id,
            proposal_id=proposal_id,
            status=decision_status,
            decision_reason=decision_reason,
            metadata=merged_metadata,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
                if "already decided" in str(exc)
                else status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        ) from exc
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal '{proposal_id}' not found in space '{space_id}'",
        )

    run = run_registry.get_run(space_id=space_id, run_id=proposal.run_id)
    if run is not None:
        proposals_for_run = proposal_store.list_proposals(
            space_id=space_id,
            run_id=proposal.run_id,
        )
        proposal_counts = status_counts(proposals_for_run)
        run_registry.record_event(
            space_id=space_id,
            run_id=proposal.run_id,
            event_type=f"proposal.{decision_status}",
            message=f"Proposal '{proposal.id}' marked {decision_status}.",
            payload={
                "proposal_id": proposal.id,
                "proposal_type": proposal.proposal_type,
                "status_counts": proposal_counts,
                "reason": decision_reason,
                "metadata": merged_metadata,
                **(event_payload or {}),
            },
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=proposal.run_id,
            patch={
                "proposal_counts": proposal_counts,
                "last_proposal_id": proposal.id,
                "last_proposal_status": decision_status,
                (
                    "last_promoted_proposal_id"
                    if decision_status == "promoted"
                    else "last_rejected_proposal_id"
                ): proposal.id,
                **(workspace_patch or {}),
            },
        )
    return updated


__all__ = [
    "build_manual_hypothesis_request",
    "build_graph_claim_request",
    "decide_proposal",
    "promote_to_graph_claim",
    "promote_to_graph_hypothesis",
    "require_proposal",
    "status_counts",
]
