"""Harness-owned mechanism-discovery run endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from services.graph_harness_api.auth import require_harness_write_access
from services.graph_harness_api.dependencies import (
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_run_registry,
)
from services.graph_harness_api.mechanism_discovery_runtime import (
    MechanismCandidateRecord,
    MechanismDiscoveryRunExecutionResult,
    queue_mechanism_discovery_run,
)
from services.graph_harness_api.routers.runs import HarnessRunResponse
from services.graph_harness_api.transparency import ensure_run_transparency_seed
from services.graph_harness_api.worker import execute_inline_worker_run
from src.infrastructure.graph_service.errors import GraphServiceClientError

if TYPE_CHECKING:
    from services.graph_harness_api.artifact_store import HarnessArtifactStore
    from services.graph_harness_api.graph_client import GraphApiGateway
    from services.graph_harness_api.harness_runtime import HarnessExecutionServices
    from services.graph_harness_api.run_registry import HarnessRunRegistry

router = APIRouter(
    prefix="/v1/spaces",
    tags=["mechanism-discovery-runs"],
    dependencies=[Depends(require_harness_write_access)],
)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_BLANK_SEED_ENTITY_IDS_ERROR = "seed_entity_ids cannot contain blank values"
_INVALID_SEED_ENTITY_ID_ERROR = "seed_entity_ids must contain valid UUID values"


class MechanismDiscoveryRunRequest(BaseModel):
    """Request payload for one harness-owned mechanism-discovery run."""

    model_config = ConfigDict(strict=True)

    seed_entity_ids: list[str] = Field(..., min_length=1, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    max_candidates: int = Field(default=10, ge=1, le=50)
    max_reasoning_paths: int = Field(default=50, ge=1, le=200)
    max_path_depth: int = Field(default=4, ge=1, le=8)
    min_path_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class MechanismCandidateResponse(BaseModel):
    """One ranked mechanism candidate surfaced to the caller."""

    model_config = ConfigDict(strict=True)

    seed_entity_ids: list[str]
    end_entity_id: str
    relation_type: str
    source_label: str | None
    target_label: str | None
    source_type: str | None
    target_type: str | None
    path_count: int
    supporting_claim_count: int
    evidence_reference_count: int
    max_path_confidence: float
    average_path_confidence: float
    average_path_length: float
    ranking_score: float
    summary: str
    hypothesis_statement: str
    hypothesis_rationale: str

    @classmethod
    def from_record(
        cls,
        record: MechanismCandidateRecord,
    ) -> MechanismCandidateResponse:
        return cls(
            seed_entity_ids=list(record.seed_entity_ids),
            end_entity_id=record.end_entity_id,
            relation_type=record.relation_type,
            source_label=record.source_label,
            target_label=record.target_label,
            source_type=record.source_type,
            target_type=record.target_type,
            path_count=len(record.path_ids),
            supporting_claim_count=len(record.supporting_claim_ids),
            evidence_reference_count=record.evidence_reference_count,
            max_path_confidence=record.max_path_confidence,
            average_path_confidence=record.average_path_confidence,
            average_path_length=record.average_path_length,
            ranking_score=record.ranking_score,
            summary=record.summary,
            hypothesis_statement=record.hypothesis_statement,
            hypothesis_rationale=record.hypothesis_rationale,
        )


class MechanismDiscoveryRunResponse(BaseModel):
    """Combined run summary and ranked mechanism candidates."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    candidates: list[MechanismCandidateResponse]
    candidate_count: int
    proposal_count: int
    scanned_path_count: int


def _normalize_seed_entity_ids(seed_entity_ids: list[str]) -> tuple[str, ...]:
    normalized_ids: list[str] = []
    seen_ids: set[str] = set()
    for value in seed_entity_ids:
        normalized = value.strip()
        if normalized == "":
            raise ValueError(_BLANK_SEED_ENTITY_IDS_ERROR)
        try:
            UUID(normalized)
        except ValueError as exc:
            raise ValueError(_INVALID_SEED_ENTITY_ID_ERROR) from exc
        if normalized in seen_ids:
            continue
        normalized_ids.append(normalized)
        seen_ids.add(normalized)
    return tuple(normalized_ids)


def build_mechanism_discovery_run_response(
    result: MechanismDiscoveryRunExecutionResult,
) -> MechanismDiscoveryRunResponse:
    """Serialize one completed mechanism-discovery execution."""
    return MechanismDiscoveryRunResponse(
        run=HarnessRunResponse.from_record(result.run),
        candidates=[
            MechanismCandidateResponse.from_record(candidate)
            for candidate in result.candidates
        ],
        candidate_count=len(result.candidates),
        proposal_count=len(result.proposal_records),
        scanned_path_count=result.scanned_path_count,
    )


@router.post(
    "/{space_id}/agents/mechanism-discovery/runs",
    response_model=MechanismDiscoveryRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start one harness-owned mechanism-discovery run",
)
async def create_mechanism_discovery_run(  # noqa: PLR0913
    space_id: UUID,
    request: MechanismDiscoveryRunRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphApiGateway = _GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> MechanismDiscoveryRunResponse:
    """Read reasoning paths, rank converging mechanisms, and stage hypotheses."""
    try:
        seed_entity_ids = _normalize_seed_entity_ids(request.seed_entity_ids)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    resolved_title = (
        request.title.strip() if isinstance(request.title, str) else ""
    ) or "Mechanism Discovery Run"
    try:
        graph_health = graph_api_gateway.get_health()
        queued_run = queue_mechanism_discovery_run(
            space_id=space_id,
            title=resolved_title,
            seed_entity_ids=seed_entity_ids,
            max_candidates=request.max_candidates,
            max_reasoning_paths=request.max_reasoning_paths,
            max_path_depth=request.max_path_depth,
            min_path_confidence=request.min_path_confidence,
            graph_service_status=graph_health.status,
            graph_service_version=graph_health.version,
            run_registry=run_registry,
            artifact_store=artifact_store,
        )
        ensure_run_transparency_seed(
            run=queued_run,
            artifact_store=artifact_store,
            runtime=execution_services.runtime,
        )
        result = await execute_inline_worker_run(
            run=queued_run,
            services=execution_services,
            worker_id="inline-mechanism-discovery",
        )
    except GraphServiceClientError as exc:
        detail = exc.detail or str(exc)
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        ) from exc
    finally:
        graph_api_gateway.close()
    if not isinstance(result, MechanismDiscoveryRunExecutionResult):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Mechanism-discovery worker returned an unexpected result.",
        )
    return build_mechanism_discovery_run_response(result)


__all__ = [
    "MechanismCandidateResponse",
    "MechanismDiscoveryRunRequest",
    "MechanismDiscoveryRunResponse",
    "build_mechanism_discovery_run_response",
    "create_mechanism_discovery_run",
    "router",
]
