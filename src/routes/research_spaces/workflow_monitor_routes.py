"""Source workflow monitor routes for research spaces."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.application.services.ports.run_progress_port import RunProgressPort
from src.application.services.source_workflow_monitor_service import (
    SourceWorkflowMonitorService,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.infrastructure.llm.state import ArtanaKernelRunProgressRepository
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    verify_space_membership,
)

from .router import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)
from .workflow_monitor_schemas import (
    SourcePipelineRunListResponse,
    SourceWorkflowEventListResponse,
    SourceWorkflowMonitorResponse,
)

logger = logging.getLogger(__name__)
_RUN_PROGRESS_RETRY_INTERVAL_SECONDS = 30.0
_RUN_PROGRESS_CACHE_LOCK = Lock()


@dataclass
class _RunProgressPortState:
    port: RunProgressPort | None = None
    last_failure_monotonic: float | None = None


_RUN_PROGRESS_STATE = _RunProgressPortState()


def _build_run_progress_port() -> RunProgressPort:
    return ArtanaKernelRunProgressRepository()


def _reset_run_progress_port_cache_for_tests() -> None:
    """Reset cached run-progress state for deterministic unit tests."""
    with _RUN_PROGRESS_CACHE_LOCK:
        _RUN_PROGRESS_STATE.port = None
        _RUN_PROGRESS_STATE.last_failure_monotonic = None


def get_run_progress_port() -> RunProgressPort | None:
    """Provide optional Artana run-progress adapter."""
    with _RUN_PROGRESS_CACHE_LOCK:
        if _RUN_PROGRESS_STATE.port is not None:
            return _RUN_PROGRESS_STATE.port

        now_monotonic = monotonic()
        if _RUN_PROGRESS_STATE.last_failure_monotonic is not None and (
            now_monotonic - _RUN_PROGRESS_STATE.last_failure_monotonic
            < _RUN_PROGRESS_RETRY_INTERVAL_SECONDS
        ):
            return None

        try:
            port = _build_run_progress_port()
        except Exception as exc:  # pragma: no cover - optional monitor enrichment
            _RUN_PROGRESS_STATE.last_failure_monotonic = now_monotonic
            logger.warning(
                "Artana run-progress monitor unavailable; continuing without stage progress. %s",
                exc,
            )
            return None

        _RUN_PROGRESS_STATE.port = port
        _RUN_PROGRESS_STATE.last_failure_monotonic = None
        return port


def get_source_workflow_monitor_service(
    session: Session = Depends(get_session),
    run_progress: RunProgressPort | None = Depends(get_run_progress_port),
) -> SourceWorkflowMonitorService:
    """Provide source workflow monitor service."""
    return SourceWorkflowMonitorService(
        session=session,
        run_progress=run_progress,
    )


class WorkflowMonitorQueryParams(BaseModel):
    run_id: str | None = Field(default=None)
    limit: int = Field(default=50)
    include_graph: bool = Field(default=True)


def get_workflow_monitor_query_params(
    run_id: str | None = Query(default=None, min_length=1, max_length=255),
    limit: int = Query(50, ge=1, le=200),
    include_graph: bool = Query(default=True),
) -> WorkflowMonitorQueryParams:
    return WorkflowMonitorQueryParams(
        run_id=run_id,
        limit=limit,
        include_graph=include_graph,
    )


class WorkflowEventsQueryParams(BaseModel):
    run_id: str | None = Field(default=None)
    limit: int = Field(default=200)
    since: str | None = Field(default=None)


def get_workflow_events_query_params(
    run_id: str | None = Query(default=None, min_length=1, max_length=255),
    limit: int = Query(200, ge=1, le=1000),
    since: str | None = Query(default=None, min_length=1, max_length=64),
) -> WorkflowEventsQueryParams:
    return WorkflowEventsQueryParams(
        run_id=run_id,
        limit=limit,
        since=since,
    )


@research_spaces_router.get(
    "/{space_id}/sources/{source_id}/pipeline-runs",
    response_model=SourcePipelineRunListResponse,
    summary="List pipeline run summaries for a source",
)
def list_source_pipeline_runs(
    space_id: UUID,
    source_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    monitor_service: SourceWorkflowMonitorService = Depends(
        get_source_workflow_monitor_service,
    ),
    session: Session = Depends(get_session),
) -> SourcePipelineRunListResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        runs = monitor_service.list_pipeline_runs(
            space_id=space_id,
            source_id=source_id,
            limit=limit,
        )
        return SourcePipelineRunListResponse(
            source_id=source_id,
            runs=runs,
            total=len(runs),
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load source pipeline runs: {exc!s}",
        ) from exc


@research_spaces_router.get(
    "/{space_id}/sources/{source_id}/workflow-monitor",
    response_model=SourceWorkflowMonitorResponse,
    summary="Get source workflow monitor snapshot",
)
def get_source_workflow_monitor(
    space_id: UUID,
    source_id: UUID,
    query: WorkflowMonitorQueryParams = Depends(get_workflow_monitor_query_params),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    monitor_service: SourceWorkflowMonitorService = Depends(
        get_source_workflow_monitor_service,
    ),
    session: Session = Depends(get_session),
) -> SourceWorkflowMonitorResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        payload = monitor_service.get_source_workflow_monitor(
            space_id=space_id,
            source_id=source_id,
            run_id=query.run_id,
            limit=query.limit,
            include_graph=query.include_graph,
        )
        return SourceWorkflowMonitorResponse.model_validate(payload)
    except LookupError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load source workflow monitor: {exc!s}",
        ) from exc


@research_spaces_router.get(
    "/{space_id}/sources/{source_id}/workflow-events",
    response_model=SourceWorkflowEventListResponse,
    summary="List detailed workflow timeline events for a source run",
)
def list_source_workflow_events(
    space_id: UUID,
    source_id: UUID,
    query: WorkflowEventsQueryParams = Depends(get_workflow_events_query_params),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    monitor_service: SourceWorkflowMonitorService = Depends(
        get_source_workflow_monitor_service,
    ),
    session: Session = Depends(get_session),
) -> SourceWorkflowEventListResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        payload = monitor_service.list_workflow_events(
            space_id=space_id,
            source_id=source_id,
            run_id=query.run_id,
            limit=query.limit,
            since=query.since,
        )
        return SourceWorkflowEventListResponse.model_validate(payload)
    except LookupError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load source workflow events: {exc!s}",
        ) from exc


__all__ = [
    "get_source_workflow_monitor",
    "list_source_pipeline_runs",
    "list_source_workflow_events",
]
