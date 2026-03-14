"""Chat session endpoints for the standalone harness service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal
from uuid import UUID  # noqa: TC003

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from services.graph_harness_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from services.graph_harness_api.auth import (
    get_current_harness_user,
    require_harness_read_access,
    require_harness_write_access,
)
from services.graph_harness_api.chat_graph_write_workflow import (
    ChatGraphWriteArtifactError,
    ChatGraphWriteCandidateError,
    ChatGraphWriteCandidateRequest,
    ChatGraphWriteVerificationError,
    chat_graph_write_source_key,
    load_graph_chat_artifacts,
    require_verified_graph_chat_result,
    stage_chat_graph_write_proposals,
)
from services.graph_harness_api.chat_sessions import (
    HarnessChatMessageRecord,  # noqa: TC001
    HarnessChatSessionRecord,  # noqa: TC001
    HarnessChatSessionStore,  # noqa: TC001
)
from services.graph_harness_api.chat_workflow import (
    DEFAULT_CHAT_SESSION_TITLE,
    GraphChatMessageExecution,
    load_chat_memory_context,
    memory_context_artifact,
    queue_graph_chat_message_run,
)
from services.graph_harness_api.dependencies import (
    get_artifact_store,
    get_chat_session_store,
    get_graph_api_gateway,
    get_graph_snapshot_store,
    get_harness_execution_services,
    get_proposal_store,
    get_research_state_store,
    get_run_registry,
)
from services.graph_harness_api.graph_chat_runtime import (
    GraphChatResult,
)
from services.graph_harness_api.graph_client import GraphApiGateway  # noqa: TC001
from services.graph_harness_api.graph_snapshot import (  # noqa: TC001
    HarnessGraphSnapshotStore,
)
from services.graph_harness_api.proposal_actions import (
    decide_proposal,
    promote_to_graph_claim,
)
from services.graph_harness_api.proposal_store import (
    HarnessProposalRecord,  # noqa: TC001
)
from services.graph_harness_api.research_state import (  # noqa: TC001
    HarnessResearchStateStore,
)
from services.graph_harness_api.routers.runs import HarnessRunResponse
from services.graph_harness_api.run_registry import HarnessRunRegistry  # noqa: TC001
from services.graph_harness_api.transparency import (
    append_manual_review_decision,
    ensure_run_transparency_seed,
)
from services.graph_harness_api.worker import execute_inline_worker_run
from src.domain.entities.user import User  # noqa: TC001
from src.infrastructure.graph_service.errors import GraphServiceClientError
from src.type_definitions.common import JSONObject  # noqa: TC001

if TYPE_CHECKING:
    from services.graph_harness_api.harness_runtime import HarnessExecutionServices
    from services.graph_harness_api.proposal_store import HarnessProposalStore

router = APIRouter(
    prefix="/v1/spaces",
    tags=["chat"],
    dependencies=[Depends(require_harness_read_access)],
)

_CHAT_SESSION_STORE_DEPENDENCY = Depends(get_chat_session_store)
_CURRENT_USER_DEPENDENCY = Depends(get_current_harness_user)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_GRAPH_SNAPSHOT_STORE_DEPENDENCY = Depends(get_graph_snapshot_store)
_PROPOSAL_STORE_DEPENDENCY = Depends(get_proposal_store)
_RESEARCH_STATE_STORE_DEPENDENCY = Depends(get_research_state_store)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)


class ChatSessionCreateRequest(BaseModel):
    """Create one chat session."""

    model_config = ConfigDict(strict=True)

    title: str | None = Field(default=None, min_length=1, max_length=256)


class ChatMessageCreateRequest(BaseModel):
    """Send one message to a graph chat session."""

    model_config = ConfigDict(strict=True)

    content: str = Field(..., min_length=1, max_length=4000)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    max_depth: int = Field(default=2, ge=1, le=4)
    top_k: int = Field(default=10, ge=1, le=25)
    include_evidence_chains: bool = True


class ChatMessageResponse(BaseModel):
    """Serialized chat message payload."""

    model_config = ConfigDict(strict=True)

    id: str
    session_id: str
    role: str
    content: str
    run_id: str | None
    metadata: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: HarnessChatMessageRecord) -> ChatMessageResponse:
        return cls(
            id=record.id,
            session_id=record.session_id,
            role=record.role,
            content=record.content,
            run_id=record.run_id,
            metadata=record.metadata,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class ChatGraphWriteProposalRequest(BaseModel):
    """Request payload for converting chat findings into proposals."""

    model_config = ConfigDict(strict=True)

    candidates: list[ChatGraphWriteCandidateRequest] | None = Field(
        default=None,
        max_length=25,
    )


class ChatGraphWriteCandidateDecisionRequest(BaseModel):
    """Promote or reject one inline chat graph-write candidate."""

    model_config = ConfigDict(strict=True)

    decision: Literal["promote", "reject"]
    reason: str | None = Field(default=None, min_length=1, max_length=2000)
    metadata: JSONObject = Field(default_factory=dict)


class ChatSessionResponse(BaseModel):
    """Serialized chat session payload."""

    model_config = ConfigDict(strict=True)

    id: str
    space_id: str
    title: str
    created_by: str
    last_run_id: str | None
    status: str
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: HarnessChatSessionRecord) -> ChatSessionResponse:
        return cls(
            id=record.id,
            space_id=record.space_id,
            title=record.title,
            created_by=record.created_by,
            last_run_id=record.last_run_id,
            status=record.status,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class ChatGraphWriteProposalRecordResponse(BaseModel):
    """Serialized proposal staged from chat findings."""

    model_config = ConfigDict(strict=True)

    id: str
    run_id: str
    proposal_type: str
    title: str
    summary: str
    status: str
    confidence: float
    ranking_score: float
    payload: JSONObject
    metadata: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_record(
        cls,
        record: HarnessProposalRecord,
    ) -> ChatGraphWriteProposalRecordResponse:
        return cls(
            id=record.id,
            run_id=record.run_id,
            proposal_type=record.proposal_type,
            title=record.title,
            summary=record.summary,
            status=record.status,
            confidence=record.confidence,
            ranking_score=record.ranking_score,
            payload=record.payload,
            metadata=record.metadata,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class ChatSessionListResponse(BaseModel):
    """List response for chat sessions."""

    model_config = ConfigDict(strict=True)

    sessions: list[ChatSessionResponse]
    total: int


class ChatSessionDetailResponse(BaseModel):
    """Chat session state including ordered message history."""

    model_config = ConfigDict(strict=True)

    session: ChatSessionResponse
    messages: list[ChatMessageResponse]


class ChatMessageRunResponse(BaseModel):
    """Combined graph-chat run result for one sent message."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    session: ChatSessionResponse
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse
    result: GraphChatResult


class ChatGraphWriteProposalResponse(BaseModel):
    """Proposals created from the latest graph-chat findings."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    session: ChatSessionResponse
    proposals: list[ChatGraphWriteProposalRecordResponse]
    proposal_count: int


class ChatGraphWriteCandidateDecisionResponse(BaseModel):
    """Decision result for one inline chat graph-write candidate."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    session: ChatSessionResponse
    candidate_index: int
    candidate: ChatGraphWriteCandidateRequest
    proposal: ChatGraphWriteProposalRecordResponse


def build_chat_message_run_response(
    execution: GraphChatMessageExecution,
) -> ChatMessageRunResponse:
    """Serialize one graph-chat execution into the public route response."""
    return ChatMessageRunResponse(
        run=HarnessRunResponse.from_record(execution.run),
        session=ChatSessionResponse.from_record(execution.session),
        user_message=ChatMessageResponse.from_record(execution.user_message),
        assistant_message=ChatMessageResponse.from_record(execution.assistant_message),
        result=execution.result,
    )


def _require_session(
    *,
    space_id: UUID,
    session_id: UUID,
    chat_session_store: HarnessChatSessionStore,
) -> HarnessChatSessionRecord:
    session = chat_session_store.get_session(space_id=space_id, session_id=session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session '{session_id}' not found in space '{space_id}'",
        )
    return session


def _require_latest_chat_run(
    *,
    space_id: UUID,
    session: HarnessChatSessionRecord,
    run_registry: HarnessRunRegistry,
) -> HarnessRunResponse:
    if session.last_run_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chat session has no graph-chat run to convert into proposals",
        )
    run = run_registry.get_run(space_id=space_id, run_id=session.last_run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Latest chat run '{session.last_run_id}' not found in space "
                f"'{space_id}'"
            ),
        )
    return HarnessRunResponse.from_record(run)


def _require_graph_chat_artifacts(
    *,
    space_id: UUID,
    run_id: str,
    artifact_store: HarnessArtifactStore,
) -> tuple[GraphChatResult, JSONObject]:
    graph_chat_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="graph_chat_result",
    )
    if graph_chat_artifact is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Latest chat run does not have a graph_chat_result artifact",
        )
    chat_summary_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="chat_summary",
    )
    if chat_summary_artifact is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Latest chat run does not have a chat_summary artifact",
        )
    try:
        graph_chat_result = GraphChatResult.model_validate(graph_chat_artifact.content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stored graph_chat_result artifact is invalid: {exc}",
        ) from exc
    return graph_chat_result, chat_summary_artifact.content


def _resolve_chat_graph_write_candidates(
    *,
    request: ChatGraphWriteProposalRequest,
    space_id: UUID,
    run_id: str,
    artifact_store: HarnessArtifactStore,
) -> list[ChatGraphWriteCandidateRequest]:
    if request.candidates is not None:
        return request.candidates
    graph_chat_result, _ = load_graph_chat_artifacts(
        space_id=space_id,
        run_id=run_id,
        artifact_store=artifact_store,
    )
    return list(graph_chat_result.graph_write_candidates)


def _require_reviewable_chat_graph_write_candidate(
    *,
    space_id: UUID,
    run_id: str,
    candidate_index: int,
    artifact_store: HarnessArtifactStore,
) -> ChatGraphWriteCandidateRequest:
    graph_chat_result, _ = load_graph_chat_artifacts(
        space_id=space_id,
        run_id=run_id,
        artifact_store=artifact_store,
    )
    require_verified_graph_chat_result(graph_chat_result)
    candidates = graph_chat_result.graph_write_candidates
    if candidate_index < 0 or candidate_index >= len(candidates):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Graph-write candidate index '{candidate_index}' not found for "
                f"chat run '{run_id}'"
            ),
        )
    return candidates[candidate_index]


def _find_existing_chat_graph_write_proposal(
    *,
    space_id: UUID,
    run_id: str,
    session_id: UUID,
    candidate: ChatGraphWriteCandidateRequest,
    proposal_store: HarnessProposalStore,
) -> HarnessProposalRecord | None:
    candidate_source_key = chat_graph_write_source_key(
        session_id=session_id,
        candidate=candidate,
    )
    proposals = proposal_store.list_proposals(space_id=space_id, run_id=run_id)
    for proposal in proposals:
        if (
            proposal.source_kind == "chat_graph_write"
            and proposal.source_key == candidate_source_key
        ):
            return proposal
    return None


def _ensure_pending_chat_graph_write_proposal(  # noqa: PLR0913
    *,
    space_id: UUID,
    run_id: str,
    session_id: UUID,
    candidate: ChatGraphWriteCandidateRequest,
    artifact_store: HarnessArtifactStore,
    proposal_store: HarnessProposalStore,
    run_registry: HarnessRunRegistry,
) -> HarnessProposalRecord:
    existing = _find_existing_chat_graph_write_proposal(
        space_id=space_id,
        run_id=run_id,
        session_id=session_id,
        candidate=candidate,
        proposal_store=proposal_store,
    )
    if existing is not None:
        if existing.status != "pending_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Chat graph-write candidate is already decided with status "
                    f"'{existing.status}'"
                ),
            )
        return existing
    execution = stage_chat_graph_write_proposals(
        space_id=space_id,
        session_id=session_id,
        run_id=run_id,
        candidates=[candidate],
        artifact_store=artifact_store,
        proposal_store=proposal_store,
        run_registry=run_registry,
    )
    if not execution.proposals:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stage chat graph-write proposal for direct review",
        )
    return execution.proposals[0]


@router.get(
    "/{space_id}/chat-sessions",
    response_model=ChatSessionListResponse,
    summary="List chat sessions",
)
def list_chat_sessions(
    space_id: UUID,
    *,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
) -> ChatSessionListResponse:
    sessions = chat_session_store.list_sessions(space_id=space_id)
    return ChatSessionListResponse(
        sessions=[ChatSessionResponse.from_record(record) for record in sessions],
        total=len(sessions),
    )


@router.post(
    "/{space_id}/chat-sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create chat session",
    dependencies=[Depends(require_harness_write_access)],
)
def create_chat_session(
    space_id: UUID,
    request: ChatSessionCreateRequest,
    *,
    current_user: User = _CURRENT_USER_DEPENDENCY,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
) -> ChatSessionResponse:
    resolved_title = (
        request.title.strip() if isinstance(request.title, str) else ""
    ) or DEFAULT_CHAT_SESSION_TITLE
    session = chat_session_store.create_session(
        space_id=space_id,
        title=resolved_title,
        created_by=current_user.id,
    )
    return ChatSessionResponse.from_record(session)


@router.get(
    "/{space_id}/chat-sessions/{session_id}",
    response_model=ChatSessionDetailResponse,
    summary="Get chat session state",
)
def get_chat_session(
    space_id: UUID,
    session_id: UUID,
    *,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
) -> ChatSessionDetailResponse:
    session = _require_session(
        space_id=space_id,
        session_id=session_id,
        chat_session_store=chat_session_store,
    )
    messages = chat_session_store.list_messages(
        space_id=space_id,
        session_id=session_id,
    )
    return ChatSessionDetailResponse(
        session=ChatSessionResponse.from_record(session),
        messages=[ChatMessageResponse.from_record(record) for record in messages],
    )


@router.post(
    "/{space_id}/chat-sessions/{session_id}/messages",
    response_model=ChatMessageRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send message and run graph chat",
    dependencies=[Depends(require_harness_write_access)],
)
async def send_chat_message(  # noqa: C901, PLR0912, PLR0913, PLR0915
    space_id: UUID,
    session_id: UUID,
    request: ChatMessageCreateRequest,
    *,
    current_user: User = _CURRENT_USER_DEPENDENCY,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphApiGateway = _GRAPH_API_GATEWAY_DEPENDENCY,
    research_state_store: HarnessResearchStateStore = _RESEARCH_STATE_STORE_DEPENDENCY,
    graph_snapshot_store: HarnessGraphSnapshotStore = _GRAPH_SNAPSHOT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> ChatMessageRunResponse:
    session = _require_session(
        space_id=space_id,
        session_id=session_id,
        chat_session_store=chat_session_store,
    )
    try:
        research_state, graph_snapshot = load_chat_memory_context(
            space_id=space_id,
            research_state_store=research_state_store,
            graph_snapshot_store=graph_snapshot_store,
        )
        memory_context = memory_context_artifact(
            research_state=research_state,
            graph_snapshot=graph_snapshot,
        )
        graph_health = graph_api_gateway.get_health()
        queued_run = queue_graph_chat_message_run(
            space_id=space_id,
            session=session,
            title=session.title,
            content=request.content,
            current_user_id=current_user.id,
            model_id=request.model_id,
            max_depth=request.max_depth,
            top_k=request.top_k,
            include_evidence_chains=request.include_evidence_chains,
            memory_context=memory_context,
            graph_service_status=graph_health.status,
            graph_service_version=graph_health.version,
            chat_session_store=chat_session_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
        )
        ensure_run_transparency_seed(
            run=queued_run,
            artifact_store=artifact_store,
            runtime=execution_services.runtime,
        )
        execution = await execute_inline_worker_run(
            run=queued_run,
            services=execution_services,
            worker_id="inline-graph-chat",
        )
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    finally:
        graph_api_gateway.close()
    if not isinstance(execution, GraphChatMessageExecution):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Graph-chat worker returned an unexpected result.",
        )
    return build_chat_message_run_response(execution)


@router.post(
    "/{space_id}/chat-sessions/{session_id}/proposals/graph-write",
    response_model=ChatGraphWriteProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Convert chat findings into graph proposals",
    dependencies=[Depends(require_harness_write_access)],
)
def create_chat_graph_write_proposals(  # noqa: PLR0913
    space_id: UUID,
    session_id: UUID,
    request: ChatGraphWriteProposalRequest,
    *,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
) -> ChatGraphWriteProposalResponse:
    session = _require_session(
        space_id=space_id,
        session_id=session_id,
        chat_session_store=chat_session_store,
    )
    run = _require_latest_chat_run(
        space_id=space_id,
        session=session,
        run_registry=run_registry,
    )
    try:
        resolved_candidates = _resolve_chat_graph_write_candidates(
            request=request,
            space_id=space_id,
            run_id=run.id,
            artifact_store=artifact_store,
        )
        execution = stage_chat_graph_write_proposals(
            space_id=space_id,
            session_id=session_id,
            run_id=run.id,
            candidates=resolved_candidates,
            artifact_store=artifact_store,
            proposal_store=proposal_store,
            run_registry=run_registry,
        )
    except ChatGraphWriteCandidateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (ChatGraphWriteArtifactError, ChatGraphWriteVerificationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    refreshed_session = chat_session_store.get_session(
        space_id=space_id,
        session_id=session_id,
    )
    return ChatGraphWriteProposalResponse(
        run=run,
        session=ChatSessionResponse.from_record(refreshed_session or session),
        proposals=[
            ChatGraphWriteProposalRecordResponse.from_record(record)
            for record in execution.proposals
        ],
        proposal_count=len(execution.proposals),
    )


@router.post(
    "/{space_id}/chat-sessions/{session_id}/graph-write-candidates/{candidate_index}/review",
    response_model=ChatGraphWriteCandidateDecisionResponse,
    summary="Promote or reject one inline graph-write candidate",
    dependencies=[Depends(require_harness_write_access)],
)
def review_chat_graph_write_candidate(  # noqa: PLR0913
    space_id: UUID,
    session_id: UUID,
    candidate_index: int,
    request: ChatGraphWriteCandidateDecisionRequest,
    *,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    graph_api_gateway: GraphApiGateway = _GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> ChatGraphWriteCandidateDecisionResponse:
    session = _require_session(
        space_id=space_id,
        session_id=session_id,
        chat_session_store=chat_session_store,
    )
    run = _require_latest_chat_run(
        space_id=space_id,
        session=session,
        run_registry=run_registry,
    )
    try:
        candidate = _require_reviewable_chat_graph_write_candidate(
            space_id=space_id,
            run_id=run.id,
            candidate_index=candidate_index,
            artifact_store=artifact_store,
        )
        proposal = _ensure_pending_chat_graph_write_proposal(
            space_id=space_id,
            run_id=run.id,
            session_id=session_id,
            candidate=candidate,
            artifact_store=artifact_store,
            proposal_store=proposal_store,
            run_registry=run_registry,
        )
        request_metadata: JSONObject = {
            **request.metadata,
            "chat_candidate_index": candidate_index,
            "chat_session_id": str(session_id),
        }
        workspace_patch: JSONObject = {
            "last_chat_graph_write_candidate_index": candidate_index,
            "last_chat_graph_write_candidate_source_key": proposal.source_key,
            "last_chat_graph_write_candidate_decision": request.decision,
        }
        if request.decision == "promote":
            promotion_metadata = promote_to_graph_claim(
                space_id=space_id,
                proposal=proposal,
                request_metadata=request_metadata,
                graph_api_gateway=graph_api_gateway,
            )
            updated_proposal = decide_proposal(
                space_id=space_id,
                proposal_id=proposal.id,
                decision_status="promoted",
                decision_reason=request.reason,
                request_metadata=request_metadata,
                proposal_store=proposal_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                decision_metadata=promotion_metadata,
                event_payload={
                    "candidate_index": candidate_index,
                    "source_key": proposal.source_key,
                    **promotion_metadata,
                },
                workspace_patch={
                    **workspace_patch,
                    "last_promoted_graph_claim_id": promotion_metadata[
                        "graph_claim_id"
                    ],
                },
            )
            append_manual_review_decision(
                space_id=space_id,
                run_id=run.id,
                tool_name="create_graph_claim",
                decision="promote",
                reason=request.reason,
                artifact_key="graph_write_candidate_suggestions",
                metadata={
                    "candidate_index": candidate_index,
                    "proposal_id": updated_proposal.id,
                    "chat_session_id": str(session_id),
                    "source_key": proposal.source_key,
                    "graph_claim_id": promotion_metadata["graph_claim_id"],
                },
                artifact_store=artifact_store,
                run_registry=run_registry,
                runtime=execution_services.runtime,
            )
        else:
            updated_proposal = decide_proposal(
                space_id=space_id,
                proposal_id=proposal.id,
                decision_status="rejected",
                decision_reason=request.reason,
                request_metadata=request_metadata,
                proposal_store=proposal_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                event_payload={
                    "candidate_index": candidate_index,
                    "source_key": proposal.source_key,
                },
                workspace_patch=workspace_patch,
            )
            append_manual_review_decision(
                space_id=space_id,
                run_id=run.id,
                tool_name="chat_graph_write_review",
                decision="reject",
                reason=request.reason,
                artifact_key="graph_write_candidate_suggestions",
                metadata={
                    "candidate_index": candidate_index,
                    "proposal_id": updated_proposal.id,
                    "chat_session_id": str(session_id),
                    "source_key": proposal.source_key,
                },
                artifact_store=artifact_store,
                run_registry=run_registry,
                runtime=execution_services.runtime,
            )
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    except (ChatGraphWriteArtifactError, ChatGraphWriteVerificationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    finally:
        graph_api_gateway.close()
    refreshed_session = chat_session_store.get_session(
        space_id=space_id,
        session_id=session_id,
    )
    return ChatGraphWriteCandidateDecisionResponse(
        run=run,
        session=ChatSessionResponse.from_record(refreshed_session or session),
        candidate_index=candidate_index,
        candidate=candidate,
        proposal=ChatGraphWriteProposalRecordResponse.from_record(updated_proposal),
    )


__all__ = [
    "ChatGraphWriteCandidateDecisionRequest",
    "ChatGraphWriteCandidateDecisionResponse",
    "ChatGraphWriteCandidateRequest",
    "ChatGraphWriteProposalRecordResponse",
    "ChatGraphWriteProposalRequest",
    "ChatGraphWriteProposalResponse",
    "ChatMessageCreateRequest",
    "ChatMessageResponse",
    "ChatMessageRunResponse",
    "ChatSessionCreateRequest",
    "ChatSessionDetailResponse",
    "ChatSessionListResponse",
    "ChatSessionResponse",
    "build_chat_message_run_response",
    "create_chat_graph_write_proposals",
    "create_chat_session",
    "get_chat_session",
    "list_chat_sessions",
    "review_chat_graph_write_candidate",
    "router",
    "send_chat_message",
]
