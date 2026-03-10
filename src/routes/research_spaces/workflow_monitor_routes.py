"""Source workflow monitor snapshot routes for research spaces."""

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
from src.application.services.pipeline_run_trace_service import (
    PipelineRunTraceService,
)
from src.application.services.ports.run_progress_port import RunProgressPort
from src.application.services.source_workflow_monitor_service import (
    SourceWorkflowMonitorService,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.infrastructure.llm.state import ArtanaKernelRunProgressRepository
from src.infrastructure.repositories import SqlAlchemyPipelineRunEventRepository
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
    PipelineRunComparisonResponse,
    PipelineRunCostReportResponse,
    PipelineRunCostSummaryResponse,
    PipelineRunSummaryEnvelopeResponse,
    PipelineRunTimingSummaryResponse,
    SourcePipelineRunListResponse,
    SourceWorkflowDocumentTraceResponse,
    SourceWorkflowEventListResponse,
    SourceWorkflowMonitorResponse,
    SourceWorkflowQueryTraceResponse,
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
        pipeline_trace=PipelineRunTraceService(
            session,
            event_repository=SqlAlchemyPipelineRunEventRepository(session),
        ),
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
    stage: str | None = Field(default=None)
    level: str | None = Field(default=None)
    scope_kind: str | None = Field(default=None)
    scope_id: str | None = Field(default=None)
    agent_kind: str | None = Field(default=None)


class WorkflowEventsFilterQueryParams(BaseModel):
    stage: str | None = Field(default=None)
    level: str | None = Field(default=None)
    scope_kind: str | None = Field(default=None)
    scope_id: str | None = Field(default=None)
    agent_kind: str | None = Field(default=None)


def get_workflow_events_filter_query_params(
    stage: str | None = Query(default=None, min_length=1, max_length=64),
    level: str | None = Query(default=None, min_length=1, max_length=16),
    scope_kind: str | None = Query(default=None, min_length=1, max_length=32),
    scope_id: str | None = Query(default=None, min_length=1, max_length=255),
    agent_kind: str | None = Query(default=None, min_length=1, max_length=64),
) -> WorkflowEventsFilterQueryParams:
    return WorkflowEventsFilterQueryParams(
        stage=stage,
        level=level,
        scope_kind=scope_kind,
        scope_id=scope_id,
        agent_kind=agent_kind,
    )


def get_workflow_events_query_params(
    run_id: str | None = Query(default=None, min_length=1, max_length=255),
    limit: int = Query(200, ge=1, le=1000),
    since: str | None = Query(default=None, min_length=1, max_length=64),
    filters: WorkflowEventsFilterQueryParams = Depends(
        get_workflow_events_filter_query_params,
    ),
) -> WorkflowEventsQueryParams:
    return WorkflowEventsQueryParams(
        run_id=run_id,
        limit=limit,
        since=since,
        stage=filters.stage,
        level=filters.level,
        scope_kind=filters.scope_kind,
        scope_id=filters.scope_id,
        agent_kind=filters.agent_kind,
    )


class CostReportQueryParams(BaseModel):
    source_type: str | None = None
    user_id: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    limit: int = Field(default=200)


@dataclass(frozen=True)
class WorkflowMonitorRouteContext:
    current_user: User
    membership_service: MembershipManagementService
    monitor_service: SourceWorkflowMonitorService
    session: Session


def get_workflow_monitor_route_context(
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    monitor_service: SourceWorkflowMonitorService = Depends(
        get_source_workflow_monitor_service,
    ),
    session: Session = Depends(get_session),
) -> WorkflowMonitorRouteContext:
    return WorkflowMonitorRouteContext(
        current_user=current_user,
        membership_service=membership_service,
        monitor_service=monitor_service,
        session=session,
    )


def get_shared_cost_report_query_params(
    source_type: str | None = Query(default=None, min_length=1, max_length=64),
    date_from: str | None = Query(default=None, min_length=1, max_length=64),
    date_to: str | None = Query(default=None, min_length=1, max_length=64),
    limit: int = Query(200, ge=1, le=1000),
) -> CostReportQueryParams:
    return CostReportQueryParams(
        source_type=source_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


def get_cost_report_query_params(
    shared_query: CostReportQueryParams = Depends(get_shared_cost_report_query_params),
    user_id: str | None = Query(default=None, min_length=1, max_length=255),
) -> CostReportQueryParams:
    return shared_query.model_copy(update={"user_id": user_id})


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
            stage=query.stage,
            level=query.level,
            scope_kind=query.scope_kind,
            scope_id=query.scope_id,
            agent_kind=query.agent_kind,
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


@research_spaces_router.get(
    "/{space_id}/sources/{source_id}/pipeline-runs/{run_id}/summary",
    response_model=PipelineRunSummaryEnvelopeResponse,
    summary="Get one source pipeline run summary",
)
def get_source_pipeline_run_summary(
    space_id: UUID,
    source_id: UUID,
    run_id: str,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    monitor_service: SourceWorkflowMonitorService = Depends(
        get_source_workflow_monitor_service,
    ),
    session: Session = Depends(get_session),
) -> PipelineRunSummaryEnvelopeResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        payload = monitor_service.get_pipeline_run_summary(
            space_id=space_id,
            source_id=source_id,
            run_id=run_id,
        )
        return PipelineRunSummaryEnvelopeResponse.model_validate(payload)
    except LookupError as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load pipeline run summary: {exc!s}",
        ) from exc


@research_spaces_router.get(
    "/{space_id}/sources/{source_id}/pipeline-runs/{run_id}/documents/{document_id}/trace",
    response_model=SourceWorkflowDocumentTraceResponse,
    summary="Get document-level trace for a pipeline run",
)
def get_source_document_trace(
    space_id: UUID,
    source_id: UUID,
    run_id: str,
    document_id: UUID,
    route_context: WorkflowMonitorRouteContext = Depends(
        get_workflow_monitor_route_context,
    ),
) -> SourceWorkflowDocumentTraceResponse:
    verify_space_membership(
        space_id,
        route_context.current_user.id,
        route_context.membership_service,
        route_context.session,
        route_context.current_user.role,
    )
    try:
        payload = route_context.monitor_service.get_document_trace(
            space_id=space_id,
            source_id=source_id,
            run_id=run_id,
            document_id=document_id,
        )
        return SourceWorkflowDocumentTraceResponse.model_validate(payload)
    except LookupError as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load document trace: {exc!s}",
        ) from exc


@research_spaces_router.get(
    "/{space_id}/sources/{source_id}/pipeline-runs/{run_id}/query-trace",
    response_model=SourceWorkflowQueryTraceResponse,
    summary="Get query-generation trace for a pipeline run",
)
def get_source_query_trace(
    space_id: UUID,
    source_id: UUID,
    run_id: str,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    monitor_service: SourceWorkflowMonitorService = Depends(
        get_source_workflow_monitor_service,
    ),
    session: Session = Depends(get_session),
) -> SourceWorkflowQueryTraceResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        payload = monitor_service.get_query_generation_trace(
            space_id=space_id,
            source_id=source_id,
            run_id=run_id,
        )
        return SourceWorkflowQueryTraceResponse.model_validate(payload)
    except LookupError as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load query trace: {exc!s}",
        ) from exc


@research_spaces_router.get(
    "/{space_id}/sources/{source_id}/pipeline-runs/{run_id}/timing",
    response_model=PipelineRunTimingSummaryResponse,
    summary="Get timing summary for a pipeline run",
)
def get_source_pipeline_run_timing(
    space_id: UUID,
    source_id: UUID,
    run_id: str,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    monitor_service: SourceWorkflowMonitorService = Depends(
        get_source_workflow_monitor_service,
    ),
    session: Session = Depends(get_session),
) -> PipelineRunTimingSummaryResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        payload = monitor_service.get_run_timing_summary(
            space_id=space_id,
            source_id=source_id,
            run_id=run_id,
        )
        return PipelineRunTimingSummaryResponse.model_validate(payload)
    except LookupError as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load timing summary: {exc!s}",
        ) from exc


@research_spaces_router.get(
    "/{space_id}/sources/{source_id}/pipeline-runs/{run_id}/cost",
    response_model=PipelineRunCostSummaryResponse,
    summary="Get direct AI/tool cost summary for a pipeline run",
)
def get_source_pipeline_run_cost(
    space_id: UUID,
    source_id: UUID,
    run_id: str,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    monitor_service: SourceWorkflowMonitorService = Depends(
        get_source_workflow_monitor_service,
    ),
    session: Session = Depends(get_session),
) -> PipelineRunCostSummaryResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        payload = monitor_service.get_run_cost_summary(
            space_id=space_id,
            source_id=source_id,
            run_id=run_id,
        )
        return PipelineRunCostSummaryResponse.model_validate(payload)
    except LookupError as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load run cost summary: {exc!s}",
        ) from exc


@research_spaces_router.get(
    "/{space_id}/pipeline-run-costs",
    response_model=PipelineRunCostReportResponse,
    summary="List pipeline run cost summaries in a research space",
)
def list_space_pipeline_run_costs(
    space_id: UUID,
    query: CostReportQueryParams = Depends(get_cost_report_query_params),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    monitor_service: SourceWorkflowMonitorService = Depends(
        get_source_workflow_monitor_service,
    ),
    session: Session = Depends(get_session),
) -> PipelineRunCostReportResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        payload = monitor_service.list_run_costs(
            space_id=space_id,
            source_id=None,
            source_type=query.source_type,
            user_id=query.user_id,
            date_from=query.date_from,
            date_to=query.date_to,
            limit=query.limit,
        )
        return PipelineRunCostReportResponse.model_validate(payload)
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load pipeline run costs: {exc!s}",
        ) from exc


@research_spaces_router.get(
    "/{space_id}/users/{user_id}/pipeline-run-costs",
    response_model=PipelineRunCostReportResponse,
    summary="List pipeline run cost summaries for one user",
)
def list_user_pipeline_run_costs(
    space_id: UUID,
    user_id: str,
    query: CostReportQueryParams = Depends(get_shared_cost_report_query_params),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    monitor_service: SourceWorkflowMonitorService = Depends(
        get_source_workflow_monitor_service,
    ),
    session: Session = Depends(get_session),
) -> PipelineRunCostReportResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        payload = monitor_service.list_run_costs(
            space_id=space_id,
            source_id=None,
            source_type=query.source_type,
            user_id=user_id,
            date_from=query.date_from,
            date_to=query.date_to,
            limit=query.limit,
        )
        return PipelineRunCostReportResponse.model_validate(payload)
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load user pipeline run costs: {exc!s}",
        ) from exc


@research_spaces_router.get(
    "/{space_id}/sources/{source_id}/pipeline-runs/compare",
    response_model=PipelineRunComparisonResponse,
    summary="Compare two pipeline runs for a source",
)
def compare_source_pipeline_runs(
    space_id: UUID,
    source_id: UUID,
    run_a: str = Query(..., min_length=1, max_length=255),
    run_b: str = Query(..., min_length=1, max_length=255),
    route_context: WorkflowMonitorRouteContext = Depends(
        get_workflow_monitor_route_context,
    ),
) -> PipelineRunComparisonResponse:
    verify_space_membership(
        space_id,
        route_context.current_user.id,
        route_context.membership_service,
        route_context.session,
        route_context.current_user.role,
    )
    try:
        payload = route_context.monitor_service.compare_source_runs(
            space_id=space_id,
            source_id=source_id,
            run_a_id=run_a,
            run_b_id=run_b,
        )
        return PipelineRunComparisonResponse.model_validate(payload)
    except LookupError as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compare pipeline runs: {exc!s}",
        ) from exc


__all__ = [
    "_reset_run_progress_port_cache_for_tests",
    "compare_source_pipeline_runs",
    "get_cost_report_query_params",
    "get_run_progress_port",
    "get_source_document_trace",
    "get_source_workflow_monitor",
    "get_source_workflow_monitor_service",
    "get_source_pipeline_run_cost",
    "get_source_pipeline_run_summary",
    "get_source_pipeline_run_timing",
    "get_source_query_trace",
    "get_workflow_events_filter_query_params",
    "get_workflow_monitor_route_context",
    "get_workflow_monitor_query_params",
    "list_source_pipeline_runs",
    "list_source_workflow_events",
    "list_space_pipeline_run_costs",
    "list_user_pipeline_run_costs",
]
