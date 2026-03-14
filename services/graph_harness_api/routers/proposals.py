"""Proposal endpoints for the standalone harness service."""

from __future__ import annotations

from uuid import UUID  # noqa: TC003

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from services.graph_harness_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from services.graph_harness_api.auth import (
    require_harness_read_access,
    require_harness_write_access,
)
from services.graph_harness_api.dependencies import (
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_proposal_store,
    get_run_registry,
)
from services.graph_harness_api.graph_client import GraphApiGateway  # noqa: TC001
from services.graph_harness_api.proposal_actions import (
    decide_proposal,
    promote_to_graph_claim,
    promote_to_graph_hypothesis,
    require_proposal,
)
from services.graph_harness_api.proposal_store import (  # noqa: TC001
    HarnessProposalRecord,
    HarnessProposalStore,
)
from services.graph_harness_api.run_registry import HarnessRunRegistry  # noqa: TC001
from services.graph_harness_api.transparency import append_manual_review_decision
from src.type_definitions.common import JSONObject  # noqa: TC001

router = APIRouter(
    prefix="/v1/spaces",
    tags=["proposals"],
    dependencies=[Depends(require_harness_read_access)],
)
_PROPOSAL_STORE_DEPENDENCY = Depends(get_proposal_store)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_STATUS_QUERY = Query(default=None, alias="status", min_length=1, max_length=32)
_PROPOSAL_TYPE_QUERY = Query(default=None, min_length=1, max_length=64)
_RUN_ID_QUERY = Query(default=None)


class HarnessProposalResponse(BaseModel):
    """Serialized proposal record."""

    model_config = ConfigDict(strict=True)

    id: str
    space_id: str
    run_id: str
    proposal_type: str
    source_kind: str
    source_key: str
    title: str
    summary: str
    status: str
    confidence: float
    ranking_score: float
    reasoning_path: JSONObject
    evidence_bundle: list[JSONObject]
    payload: JSONObject
    metadata: JSONObject
    decision_reason: str | None
    decided_at: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: HarnessProposalRecord) -> HarnessProposalResponse:
        """Serialize one stored proposal."""
        return cls(
            id=record.id,
            space_id=record.space_id,
            run_id=record.run_id,
            proposal_type=record.proposal_type,
            source_kind=record.source_kind,
            source_key=record.source_key,
            title=record.title,
            summary=record.summary,
            status=record.status,
            confidence=record.confidence,
            ranking_score=record.ranking_score,
            reasoning_path=record.reasoning_path,
            evidence_bundle=record.evidence_bundle,
            payload=record.payload,
            metadata=record.metadata,
            decision_reason=record.decision_reason,
            decided_at=(
                record.decided_at.isoformat() if record.decided_at is not None else None
            ),
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class HarnessProposalListResponse(BaseModel):
    """List response for proposals."""

    model_config = ConfigDict(strict=True)

    proposals: list[HarnessProposalResponse]
    total: int


class HarnessProposalDecisionRequest(BaseModel):
    """Promote or reject one proposal."""

    model_config = ConfigDict(strict=True)

    reason: str | None = Field(default=None, min_length=1, max_length=2000)
    metadata: JSONObject = Field(default_factory=dict)


@router.get(
    "/{space_id}/proposals",
    response_model=HarnessProposalListResponse,
    summary="List staged proposals",
)
def list_proposals(
    space_id: UUID,
    status_filter: str | None = _STATUS_QUERY,
    proposal_type: str | None = _PROPOSAL_TYPE_QUERY,
    run_id: UUID | None = _RUN_ID_QUERY,
    *,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
) -> HarnessProposalListResponse:
    """Return proposals for one research space."""
    proposals = proposal_store.list_proposals(
        space_id=space_id,
        status=status_filter,
        proposal_type=proposal_type,
        run_id=run_id,
    )
    return HarnessProposalListResponse(
        proposals=[
            HarnessProposalResponse.from_record(proposal) for proposal in proposals
        ],
        total=len(proposals),
    )


@router.get(
    "/{space_id}/proposals/{proposal_id}",
    response_model=HarnessProposalResponse,
    summary="Get one staged proposal",
)
def get_proposal(
    space_id: UUID,
    proposal_id: UUID,
    *,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
) -> HarnessProposalResponse:
    """Return one proposal with evidence and ranking."""
    proposal = require_proposal(
        space_id=space_id,
        proposal_id=proposal_id,
        proposal_store=proposal_store,
    )
    return HarnessProposalResponse.from_record(proposal)


@router.post(
    "/{space_id}/proposals/{proposal_id}/promote",
    response_model=HarnessProposalResponse,
    summary="Promote one reviewed proposal",
    dependencies=[Depends(require_harness_write_access)],
)
def promote_proposal(  # noqa: PLR0913
    space_id: UUID,
    proposal_id: UUID,
    request: HarnessProposalDecisionRequest,
    *,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphApiGateway = _GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services=_HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> HarnessProposalResponse:
    """Promote one proposal into the reviewed state."""
    proposal = require_proposal(
        space_id=space_id,
        proposal_id=proposal_id,
        proposal_store=proposal_store,
    )
    if proposal.status != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Proposal '{proposal.id}' is already decided with status "
                f"'{proposal.status}'"
            ),
        )
    try:
        if proposal.proposal_type == "candidate_claim":
            promotion_metadata = promote_to_graph_claim(
                space_id=space_id,
                proposal=proposal,
                request_metadata=request.metadata,
                graph_api_gateway=graph_api_gateway,
            )
            workspace_patch = {
                "last_promoted_graph_claim_id": promotion_metadata["graph_claim_id"],
            }
        elif proposal.proposal_type == "mechanism_candidate":
            promotion_metadata = promote_to_graph_hypothesis(
                space_id=space_id,
                proposal=proposal,
                graph_api_gateway=graph_api_gateway,
            )
            workspace_patch = {
                "last_promoted_hypothesis_claim_id": promotion_metadata[
                    "graph_hypothesis_claim_id"
                ],
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Proposal type '{proposal.proposal_type}' is not supported for "
                    "promotion"
                ),
            )
    finally:
        graph_api_gateway.close()
    updated = decide_proposal(
        space_id=space_id,
        proposal_id=proposal_id,
        decision_status="promoted",
        decision_reason=request.reason,
        request_metadata=request.metadata,
        proposal_store=proposal_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
        decision_metadata=promotion_metadata,
        event_payload=promotion_metadata,
        workspace_patch=workspace_patch,
    )
    append_manual_review_decision(
        space_id=space_id,
        run_id=proposal.run_id,
        tool_name=(
            "create_manual_hypothesis"
            if proposal.proposal_type == "mechanism_candidate"
            else "create_graph_claim"
        ),
        decision="promote",
        reason=request.reason,
        artifact_key=(
            "candidate_hypothesis_pack"
            if proposal.proposal_type == "mechanism_candidate"
            else "candidate_claim_pack"
        ),
        metadata={
            "proposal_id": updated.id,
            "proposal_type": proposal.proposal_type,
            **promotion_metadata,
        },
        artifact_store=artifact_store,
        run_registry=run_registry,
        runtime=execution_services.runtime,
    )
    return HarnessProposalResponse.from_record(updated)


@router.post(
    "/{space_id}/proposals/{proposal_id}/reject",
    response_model=HarnessProposalResponse,
    summary="Reject one staged proposal",
    dependencies=[Depends(require_harness_write_access)],
)
def reject_proposal(  # noqa: PLR0913
    space_id: UUID,
    proposal_id: UUID,
    request: HarnessProposalDecisionRequest,
    *,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services=_HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> HarnessProposalResponse:
    """Reject one proposal without touching the graph ledger."""
    updated = decide_proposal(
        space_id=space_id,
        proposal_id=proposal_id,
        decision_status="rejected",
        decision_reason=request.reason,
        request_metadata=request.metadata,
        proposal_store=proposal_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    append_manual_review_decision(
        space_id=space_id,
        run_id=updated.run_id,
        tool_name="proposal_review",
        decision="reject",
        reason=request.reason,
        artifact_key=(
            "candidate_hypothesis_pack"
            if updated.proposal_type == "mechanism_candidate"
            else "candidate_claim_pack"
        ),
        metadata={
            "proposal_id": updated.id,
            "proposal_type": updated.proposal_type,
            "status": updated.status,
        },
        artifact_store=artifact_store,
        run_registry=run_registry,
        runtime=execution_services.runtime,
    )
    return HarnessProposalResponse.from_record(updated)


__all__ = [
    "HarnessProposalDecisionRequest",
    "HarnessProposalListResponse",
    "HarnessProposalResponse",
    "get_proposal",
    "list_proposals",
    "promote_proposal",
    "reject_proposal",
    "router",
]
