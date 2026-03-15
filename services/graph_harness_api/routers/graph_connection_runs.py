"""Harness-owned graph-connection AI run endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from services.graph_harness_api.auth import require_harness_write_access
from services.graph_harness_api.dependencies import (
    get_artifact_store,
    get_graph_api_gateway,
    get_graph_connection_runner,
    get_harness_execution_services,
    get_run_registry,
)
from services.graph_harness_api.graph_connection_runtime import (
    HarnessGraphConnectionRequest,
    HarnessGraphConnectionRunner,
)
from services.graph_harness_api.routers.runs import HarnessRunResponse
from services.graph_harness_api.transparency import (
    append_skill_activity,
    ensure_run_transparency_seed,
)
from src.domain.agents.contracts.graph_connection import (  # noqa: TC001
    GraphConnectionContract,
)
from src.infrastructure.graph_service.errors import GraphServiceClientError

if TYPE_CHECKING:
    from services.graph_harness_api.artifact_store import HarnessArtifactStore
    from services.graph_harness_api.graph_client import GraphApiGateway
    from services.graph_harness_api.harness_runtime import HarnessExecutionServices
    from services.graph_harness_api.run_registry import HarnessRunRegistry
    from src.type_definitions.common import JSONObject

router = APIRouter(
    prefix="/v1/spaces",
    tags=["graph-connection-runs"],
    dependencies=[Depends(require_harness_write_access)],
)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_GRAPH_CONNECTION_RUNNER_DEPENDENCY = Depends(get_graph_connection_runner)

_BLANK_SEED_ENTITY_IDS_ERROR = "seed_entity_ids cannot contain blank values"


class GraphConnectionRunRequest(BaseModel):
    """Request payload for one harness-owned graph-connection run."""

    model_config = ConfigDict(strict=True)

    seed_entity_ids: list[str] = Field(..., min_length=1, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    source_type: str | None = Field(default=None, min_length=1, max_length=64)
    source_id: str | None = Field(default=None, min_length=1, max_length=64)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    relation_types: list[str] | None = None
    max_depth: int = Field(default=2, ge=1, le=4)
    shadow_mode: bool = True
    pipeline_run_id: str | None = Field(default=None, min_length=1, max_length=128)


class GraphConnectionRunResponse(BaseModel):
    """Combined run and graph-connection result payload."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    outcomes: list[GraphConnectionContract]


def _normalize_seed_entity_ids(seed_entity_ids: list[str]) -> list[str]:
    normalized_ids: list[str] = []
    for value in seed_entity_ids:
        normalized = value.strip()
        if not normalized:
            raise ValueError(_BLANK_SEED_ENTITY_IDS_ERROR)
        normalized_ids.append(normalized)
    return normalized_ids


@router.post(
    "/{space_id}/agents/graph-connections/runs",
    response_model=GraphConnectionRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start one harness-owned graph-connection AI run",
)
async def create_graph_connection_run(  # noqa: PLR0913
    space_id: UUID,
    request: GraphConnectionRunRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
    graph_api_gateway: GraphApiGateway = _GRAPH_API_GATEWAY_DEPENDENCY,
    graph_connection_runner: HarnessGraphConnectionRunner = _GRAPH_CONNECTION_RUNNER_DEPENDENCY,
) -> GraphConnectionRunResponse:
    """Execute one AI-backed graph-connection run from the harness service."""
    try:
        seed_entity_ids = _normalize_seed_entity_ids(request.seed_entity_ids)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    resolved_title = (
        request.title.strip() if isinstance(request.title, str) else ""
    ) or "Graph Connection Agent Run"
    try:
        graph_health = graph_api_gateway.get_health()
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    finally:
        graph_api_gateway.close()

    run_input_payload: JSONObject = {
        "seed_entity_ids": seed_entity_ids,
        "source_type": request.source_type,
        "source_id": request.source_id,
        "model_id": request.model_id,
        "relation_types": request.relation_types or [],
        "max_depth": request.max_depth,
        "shadow_mode": request.shadow_mode,
        "pipeline_run_id": request.pipeline_run_id,
    }
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="graph-connections",
        title=resolved_title,
        input_payload=run_input_payload,
        graph_service_status=graph_health.status,
        graph_service_version=graph_health.version,
    )
    artifact_store.seed_for_run(run=run)
    ensure_run_transparency_seed(
        run=run,
        artifact_store=artifact_store,
        runtime=execution_services.runtime,
    )
    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="running")
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "running"},
    )

    outcomes: list[GraphConnectionContract] = []
    try:
        for seed_entity_id in seed_entity_ids:
            outcome_result = await graph_connection_runner.run(
                HarnessGraphConnectionRequest(
                    harness_id="graph-connections",
                    seed_entity_id=seed_entity_id,
                    research_space_id=str(space_id),
                    source_type=request.source_type,
                    source_id=request.source_id,
                    model_id=request.model_id,
                    relation_types=request.relation_types,
                    max_depth=request.max_depth,
                    shadow_mode=request.shadow_mode,
                    pipeline_run_id=request.pipeline_run_id,
                    research_space_settings={},
                ),
            )
            append_skill_activity(
                space_id=space_id,
                run_id=run.id,
                skill_names=outcome_result.active_skill_names,
                source_run_id=outcome_result.agent_run_id,
                source_kind="graph_connection",
                artifact_store=artifact_store,
                run_registry=run_registry,
                runtime=execution_services.runtime,
            )
            outcomes.append(outcome_result.contract)
    except Exception as exc:
        run_registry.set_run_status(space_id=space_id, run_id=run.id, status="failed")
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={"status": "failed", "error": str(exc)},
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="graph_connection_error",
            media_type="application/json",
            content={"error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph-connection run failed: {exc}",
        ) from exc

    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="graph_connection_result",
        media_type="application/json",
        content={
            "outcomes": [outcome.model_dump(mode="json") for outcome in outcomes],
        },
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "completed",
            "last_graph_connection_result_key": "graph_connection_result",
            "graph_connection_count": len(outcomes),
        },
    )
    updated_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
    )
    if updated_run is None:
        updated_run = run
    return GraphConnectionRunResponse(
        run=HarnessRunResponse.from_record(updated_run),
        outcomes=outcomes,
    )


__all__ = [
    "GraphConnectionRunRequest",
    "GraphConnectionRunResponse",
    "create_graph_connection_run",
    "router",
]
