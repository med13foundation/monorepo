"""Harness-owned graph-search AI run endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from services.graph_harness_api.auth import require_harness_write_access
from services.graph_harness_api.dependencies import (
    get_artifact_store,
    get_graph_api_gateway,
    get_graph_search_runner,
    get_harness_execution_services,
    get_run_registry,
)
from services.graph_harness_api.graph_search_runtime import (
    HarnessGraphSearchRequest,
    HarnessGraphSearchRunner,
)
from services.graph_harness_api.routers.runs import HarnessRunResponse
from services.graph_harness_api.transparency import (
    append_skill_activity,
    ensure_run_transparency_seed,
)
from src.domain.agents.contracts.graph_search import GraphSearchContract  # noqa: TC001
from src.infrastructure.graph_service.errors import GraphServiceClientError

if TYPE_CHECKING:
    from services.graph_harness_api.artifact_store import HarnessArtifactStore
    from services.graph_harness_api.graph_client import GraphApiGateway
    from services.graph_harness_api.harness_runtime import HarnessExecutionServices
    from services.graph_harness_api.run_registry import HarnessRunRegistry
    from src.type_definitions.common import JSONObject

router = APIRouter(
    prefix="/v1/spaces",
    tags=["graph-search-runs"],
    dependencies=[Depends(require_harness_write_access)],
)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_GRAPH_SEARCH_RUNNER_DEPENDENCY = Depends(get_graph_search_runner)


class GraphSearchRunRequest(BaseModel):
    """Request payload for one harness-owned graph-search run."""

    model_config = ConfigDict(strict=True)

    question: str = Field(..., min_length=1, max_length=2000)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    max_depth: int = Field(default=2, ge=1, le=4)
    top_k: int = Field(default=25, ge=1, le=100)
    curation_statuses: list[str] | None = None
    include_evidence_chains: bool = True


class GraphSearchRunResponse(BaseModel):
    """Combined run and graph-search result payload."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    result: GraphSearchContract


@router.post(
    "/{space_id}/agents/graph-search/runs",
    response_model=GraphSearchRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start one harness-owned graph-search AI run",
)
async def create_graph_search_run(  # noqa: PLR0913
    space_id: UUID,
    request: GraphSearchRunRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
    graph_api_gateway: GraphApiGateway = _GRAPH_API_GATEWAY_DEPENDENCY,
    graph_search_runner: HarnessGraphSearchRunner = _GRAPH_SEARCH_RUNNER_DEPENDENCY,
) -> GraphSearchRunResponse:
    """Execute one AI-backed graph-search run from the harness service."""
    resolved_title = (
        request.title.strip() if isinstance(request.title, str) else ""
    ) or "Graph Search Agent Run"
    try:
        graph_health = graph_api_gateway.get_health()
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    finally:
        graph_api_gateway.close()

    run = run_registry.create_run(
        space_id=space_id,
        harness_id="graph-search",
        title=resolved_title,
        input_payload={
            "question": request.question,
            "model_id": request.model_id,
            "max_depth": request.max_depth,
            "top_k": request.top_k,
            "curation_statuses": request.curation_statuses or [],
            "include_evidence_chains": request.include_evidence_chains,
        },
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

    try:
        search_result = await graph_search_runner.run(
            HarnessGraphSearchRequest(
                harness_id="graph-search",
                question=request.question,
                research_space_id=str(space_id),
                max_depth=request.max_depth,
                top_k=request.top_k,
                curation_statuses=request.curation_statuses,
                include_evidence_chains=request.include_evidence_chains,
                model_id=request.model_id,
            ),
        )
    except Exception as exc:
        run_registry.set_run_status(space_id=space_id, run_id=run.id, status="failed")
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "failed",
                "error": str(exc),
            },
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="graph_search_error",
            media_type="application/json",
            content={"error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph-search run failed: {exc}",
        ) from exc
    append_skill_activity(
        space_id=space_id,
        run_id=run.id,
        skill_names=search_result.active_skill_names,
        source_run_id=search_result.agent_run_id,
        source_kind="graph_search",
        artifact_store=artifact_store,
        run_registry=run_registry,
        runtime=execution_services.runtime,
    )

    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="graph_search_result",
        media_type="application/json",
        content=search_result.contract.model_dump(mode="json"),
    )
    workspace_patch: JSONObject = {
        "status": "completed",
        "last_graph_search_result_key": "graph_search_result",
        "graph_search_decision": search_result.contract.decision,
    }
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch=workspace_patch,
    )
    updated_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
    )
    if updated_run is None:
        updated_run = run
    return GraphSearchRunResponse(
        run=HarnessRunResponse.from_record(updated_run),
        result=search_result.contract,
    )


__all__ = [
    "GraphSearchRunRequest",
    "GraphSearchRunResponse",
    "create_graph_search_run",
    "router",
]
