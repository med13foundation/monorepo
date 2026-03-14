"""Artifact and workspace endpoints for the standalone harness service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from services.graph_harness_api.auth import require_harness_read_access
from services.graph_harness_api.dependencies import get_artifact_store, get_run_registry
from src.type_definitions.common import JSONObject  # noqa: TC001

if TYPE_CHECKING:
    from services.graph_harness_api.artifact_store import (
        HarnessArtifactRecord,
        HarnessArtifactStore,
        HarnessWorkspaceRecord,
    )
    from services.graph_harness_api.run_registry import HarnessRunRegistry

_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)

router = APIRouter(
    prefix="/v1/spaces",
    tags=["artifacts"],
    dependencies=[Depends(require_harness_read_access)],
)


class HarnessArtifactResponse(BaseModel):
    """Serialized artifact payload."""

    model_config = ConfigDict(strict=True)

    key: str
    media_type: str
    content: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: HarnessArtifactRecord) -> HarnessArtifactResponse:
        """Serialize one artifact record."""
        return cls(
            key=record.key,
            media_type=record.media_type,
            content=record.content,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class HarnessArtifactListResponse(BaseModel):
    """List response for run artifacts."""

    model_config = ConfigDict(strict=True)

    artifacts: list[HarnessArtifactResponse]
    total: int


class HarnessWorkspaceResponse(BaseModel):
    """Serialized workspace snapshot payload."""

    model_config = ConfigDict(strict=True)

    snapshot: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: HarnessWorkspaceRecord) -> HarnessWorkspaceResponse:
        """Serialize one workspace snapshot record."""
        return cls(
            snapshot=record.snapshot,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


def _require_run(
    *,
    space_id: UUID,
    run_id: UUID,
    run_registry: HarnessRunRegistry,
) -> None:
    run = run_registry.get_run(space_id=space_id, run_id=run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found in space '{space_id}'",
        )


@router.get(
    "/{space_id}/runs/{run_id}/artifacts",
    response_model=HarnessArtifactListResponse,
    summary="List artifacts for one harness run",
)
def list_artifacts(
    space_id: UUID,
    run_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> HarnessArtifactListResponse:
    """Return artifacts stored for one harness run."""
    _require_run(space_id=space_id, run_id=run_id, run_registry=run_registry)
    artifacts = artifact_store.list_artifacts(space_id=space_id, run_id=run_id)
    return HarnessArtifactListResponse(
        artifacts=[
            HarnessArtifactResponse.from_record(artifact) for artifact in artifacts
        ],
        total=len(artifacts),
    )


@router.get(
    "/{space_id}/runs/{run_id}/artifacts/{artifact_key}",
    response_model=HarnessArtifactResponse,
    summary="Get one artifact for one harness run",
)
def get_artifact(
    space_id: UUID,
    run_id: UUID,
    artifact_key: str,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> HarnessArtifactResponse:
    """Return one artifact stored for one harness run."""
    _require_run(space_id=space_id, run_id=run_id, run_registry=run_registry)
    artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=artifact_key,
    )
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Artifact '{artifact_key}' not found for run '{run_id}' "
                f"in space '{space_id}'"
            ),
        )
    return HarnessArtifactResponse.from_record(artifact)


@router.get(
    "/{space_id}/runs/{run_id}/workspace",
    response_model=HarnessWorkspaceResponse,
    summary="Get workspace snapshot for one harness run",
)
def get_workspace(
    space_id: UUID,
    run_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> HarnessWorkspaceResponse:
    """Return the workspace snapshot stored for one harness run."""
    _require_run(space_id=space_id, run_id=run_id, run_registry=run_registry)
    workspace = artifact_store.get_workspace(space_id=space_id, run_id=run_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace for run '{run_id}' not found in space '{space_id}'",
        )
    return HarnessWorkspaceResponse.from_record(workspace)


__all__ = [
    "HarnessArtifactListResponse",
    "HarnessArtifactResponse",
    "HarnessWorkspaceResponse",
    "get_artifact",
    "get_workspace",
    "list_artifacts",
    "router",
]
