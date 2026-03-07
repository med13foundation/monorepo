"""Source workflow SSE stream routes for research spaces."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

try:
    from fastapi.sse import EventSourceResponse
except ImportError:  # pragma: no cover - depends on installed FastAPI extras
    from sse_starlette import EventSourceResponse

from src.application.services.source_workflow_monitor_service import (
    SourceWorkflowMonitorService,
)
from src.database.session import get_session
from src.routes.auth import get_current_active_user

from . import dependencies as space_dependencies
from . import workflow_monitor_routes as monitor_routes
from . import workflow_monitor_stream_utils as stream_utils
from .router import HTTP_404_NOT_FOUND, research_spaces_router

logger = logging.getLogger(__name__)


@dataclass
class _MembershipContext:
    membership_service: object
    session: Session


def get_membership_context(
    membership_service: object = Depends(
        space_dependencies.get_membership_service,
    ),
    session: Session = Depends(get_session),
) -> _MembershipContext:
    return _MembershipContext(
        membership_service=membership_service,
        session=session,
    )


class WorkflowSpaceStreamQueryParams(BaseModel):
    source_ids: list[str] = Field(default_factory=list)
    include_inactive: bool = False
    events_limit: int = Field(default=3, ge=1, le=10)


def get_workflow_space_stream_query_params(
    source_ids: str | None = Query(default=None, min_length=1, max_length=4000),
    include_inactive: bool = Query(default=False),
    events_limit: int = Query(3, ge=1, le=10),
) -> WorkflowSpaceStreamQueryParams:
    return WorkflowSpaceStreamQueryParams(
        source_ids=stream_utils.parse_requested_source_ids(source_ids),
        include_inactive=include_inactive,
        events_limit=events_limit,
    )


@research_spaces_router.get(
    "/{space_id}/sources/{source_id}/workflow-stream",
    summary="Stream live workflow monitor updates for one source",
)
async def stream_source_workflow_monitor(  # noqa: PLR0913, PLR0915
    request: Request,
    space_id: UUID,
    source_id: UUID,
    query: monitor_routes.WorkflowMonitorQueryParams = Depends(
        monitor_routes.get_workflow_monitor_query_params,
    ),
    current_user: object = Depends(get_current_active_user),
    membership_context: _MembershipContext = Depends(get_membership_context),
    monitor_service: SourceWorkflowMonitorService = Depends(
        monitor_routes.get_source_workflow_monitor_service,
    ),
) -> EventSourceResponse:
    if not stream_utils.is_workflow_sse_enabled():
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Workflow SSE is disabled",
        )

    current_user_id = current_user.id  # type: ignore[attr-defined]
    current_user_role = current_user.role  # type: ignore[attr-defined]
    space_dependencies.verify_space_membership(
        space_id,
        current_user_id,
        membership_context.membership_service,  # type: ignore[arg-type]
        membership_context.session,
        current_user_role,
    )

    async def _event_generator() -> AsyncIterator[str]:
        sequence = 0
        since_cursor: str | None = None
        last_snapshot_hash: str | None = None
        last_heartbeat_mono = 0.0

        bootstrap_monitor = monitor_service.get_source_workflow_monitor(
            space_id=space_id,
            source_id=source_id,
            run_id=query.run_id,
            limit=stream_utils.STREAM_SOURCE_MONITOR_LIMIT,
            include_graph=query.include_graph,
        )
        bootstrap_events_payload = monitor_service.list_workflow_events(
            space_id=space_id,
            source_id=source_id,
            run_id=query.run_id,
            limit=stream_utils.STREAM_EVENTS_LIMIT,
            since=None,
        )
        bootstrap_events_raw = bootstrap_events_payload.get("events")
        bootstrap_events = (
            bootstrap_events_raw if isinstance(bootstrap_events_raw, list) else []
        )
        since_cursor = stream_utils.extract_latest_occurred_at(bootstrap_events)
        last_snapshot_hash = stream_utils.hash_payload(bootstrap_monitor)
        last_heartbeat_mono = asyncio.get_running_loop().time()

        sequence += 1
        yield stream_utils.sse_event_payload(
            event="bootstrap",
            sequence=sequence,
            data={
                "monitor": bootstrap_monitor,
                "events": bootstrap_events,
                "generated_at": stream_utils.now_iso(),
                "run_id": query.run_id,
            },
        )

        while True:
            if await request.is_disconnected():
                break

            emitted_event = False
            try:
                monitor_payload = monitor_service.get_source_workflow_monitor(
                    space_id=space_id,
                    source_id=source_id,
                    run_id=query.run_id,
                    limit=stream_utils.STREAM_SOURCE_MONITOR_LIMIT,
                    include_graph=query.include_graph,
                )
                snapshot_hash = stream_utils.hash_payload(monitor_payload)
                if snapshot_hash != last_snapshot_hash:
                    last_snapshot_hash = snapshot_hash
                    sequence += 1
                    emitted_event = True
                    yield stream_utils.sse_event_payload(
                        event="snapshot",
                        sequence=sequence,
                        data={
                            "monitor": monitor_payload,
                            "generated_at": stream_utils.now_iso(),
                            "run_id": query.run_id,
                        },
                    )

                events_payload = monitor_service.list_workflow_events(
                    space_id=space_id,
                    source_id=source_id,
                    run_id=query.run_id,
                    limit=stream_utils.STREAM_EVENTS_LIMIT,
                    since=since_cursor,
                )
                events_raw = events_payload.get("events")
                events = events_raw if isinstance(events_raw, list) else []
                latest_since = stream_utils.extract_latest_occurred_at(events)
                if latest_since is not None:
                    since_cursor = latest_since
                if events:
                    sequence += 1
                    emitted_event = True
                    yield stream_utils.sse_event_payload(
                        event="workflow_events",
                        sequence=sequence,
                        data={
                            "events": events,
                            "generated_at": stream_utils.now_iso(),
                            "run_id": query.run_id,
                        },
                    )
            except Exception as exc:  # pragma: no cover - defensive stream guard
                logger.warning(
                    "Workflow SSE source stream iteration failed for source_id=%s: %s",
                    source_id,
                    exc,
                )
                sequence += 1
                emitted_event = True
                yield stream_utils.sse_event_payload(
                    event="error",
                    sequence=sequence,
                    data={
                        "message": "Workflow stream iteration failed; retrying.",
                        "generated_at": stream_utils.now_iso(),
                    },
                )

            now_mono = asyncio.get_running_loop().time()
            if (
                not emitted_event
                and now_mono - last_heartbeat_mono
                >= stream_utils.STREAM_HEARTBEAT_SECONDS
            ):
                sequence += 1
                yield stream_utils.sse_event_payload(
                    event="heartbeat",
                    sequence=sequence,
                    data={"generated_at": stream_utils.now_iso()},
                )
                last_heartbeat_mono = now_mono
            elif emitted_event:
                last_heartbeat_mono = now_mono

            await asyncio.sleep(stream_utils.STREAM_TICK_SECONDS)

    return EventSourceResponse(_event_generator())


@research_spaces_router.get(
    "/{space_id}/workflow-stream",
    summary="Stream live workflow card updates for sources in one research space",
)
async def stream_space_workflow_cards(  # noqa: PLR0913, PLR0915
    request: Request,
    space_id: UUID,
    query: WorkflowSpaceStreamQueryParams = Depends(
        get_workflow_space_stream_query_params,
    ),
    current_user: object = Depends(get_current_active_user),
    membership_context: _MembershipContext = Depends(get_membership_context),
    monitor_service: SourceWorkflowMonitorService = Depends(
        monitor_routes.get_source_workflow_monitor_service,
    ),
) -> EventSourceResponse:
    if not stream_utils.is_workflow_sse_enabled():
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Workflow SSE is disabled",
        )

    current_user_id = current_user.id  # type: ignore[attr-defined]
    current_user_role = current_user.role  # type: ignore[attr-defined]
    space_dependencies.verify_space_membership(
        space_id,
        current_user_id,
        membership_context.membership_service,  # type: ignore[arg-type]
        membership_context.session,
        current_user_role,
    )

    async def _event_generator() -> AsyncIterator[str]:  # noqa: PLR0912, PLR0915
        sequence = 0
        last_heartbeat_mono = asyncio.get_running_loop().time()
        last_hash_by_source: dict[str, str] = {}
        since_by_source: dict[str, str | None] = {}

        source_ids = stream_utils.resolve_space_source_ids(
            session=membership_context.session,
            space_id=space_id,
            include_inactive=query.include_inactive,
            requested_source_ids=query.source_ids,
        )
        bootstrap_rows: list[dict[str, object]] = []
        for source_id_str in source_ids:
            try:
                source_uuid = UUID(source_id_str)
                monitor_payload = monitor_service.get_source_workflow_monitor(
                    space_id=space_id,
                    source_id=source_uuid,
                    run_id=None,
                    limit=stream_utils.STREAM_MONITOR_LIMIT,
                    include_graph=False,
                )
                events_payload = monitor_service.list_workflow_events(
                    space_id=space_id,
                    source_id=source_uuid,
                    run_id=None,
                    limit=query.events_limit,
                    since=None,
                )
                events_raw = events_payload.get("events")
                events = events_raw if isinstance(events_raw, list) else []
                since_by_source[source_id_str] = (
                    stream_utils.extract_latest_occurred_at(
                        events,
                    )
                )
                row: dict[str, object] = {
                    "source_id": source_id_str,
                    "workflow_status": stream_utils.build_workflow_card_status(
                        monitor_payload,
                    ),
                    "events": events,
                    "generated_at": stream_utils.now_iso(),
                }
                last_hash_by_source[source_id_str] = stream_utils.hash_payload(row)
                bootstrap_rows.append(row)
            except Exception as exc:  # pragma: no cover - defensive stream guard
                logger.warning(
                    "Workflow SSE bootstrap failed for source_id=%s: %s",
                    source_id_str,
                    exc,
                )
        sequence += 1
        yield stream_utils.sse_event_payload(
            event="bootstrap",
            sequence=sequence,
            data={
                "sources": bootstrap_rows,
                "generated_at": stream_utils.now_iso(),
            },
        )

        while True:
            if await request.is_disconnected():
                break

            emitted_event = False
            try:
                source_ids = stream_utils.resolve_space_source_ids(
                    session=membership_context.session,
                    space_id=space_id,
                    include_inactive=query.include_inactive,
                    requested_source_ids=query.source_ids,
                )
                active_source_set = set(source_ids)
                for stale_source_id in list(last_hash_by_source.keys()):
                    if stale_source_id not in active_source_set:
                        last_hash_by_source.pop(stale_source_id, None)
                        since_by_source.pop(stale_source_id, None)

                for source_id_str in source_ids:
                    try:
                        source_uuid = UUID(source_id_str)
                        monitor_payload = monitor_service.get_source_workflow_monitor(
                            space_id=space_id,
                            source_id=source_uuid,
                            run_id=None,
                            limit=stream_utils.STREAM_MONITOR_LIMIT,
                            include_graph=False,
                        )
                        events_payload = monitor_service.list_workflow_events(
                            space_id=space_id,
                            source_id=source_uuid,
                            run_id=None,
                            limit=query.events_limit,
                            since=since_by_source.get(source_id_str),
                        )
                        events_raw = events_payload.get("events")
                        events = events_raw if isinstance(events_raw, list) else []
                        latest_since = stream_utils.extract_latest_occurred_at(events)
                        if latest_since is not None:
                            since_by_source[source_id_str] = latest_since

                        event_payload: dict[str, object] = {
                            "source_id": source_id_str,
                            "workflow_status": stream_utils.build_workflow_card_status(
                                monitor_payload,
                            ),
                            "events": events,
                            "generated_at": stream_utils.now_iso(),
                        }
                        payload_hash = stream_utils.hash_payload(event_payload)
                        if payload_hash == last_hash_by_source.get(source_id_str):
                            continue
                        last_hash_by_source[source_id_str] = payload_hash
                        sequence += 1
                        emitted_event = True
                        yield stream_utils.sse_event_payload(
                            event="source_card_status",
                            sequence=sequence,
                            data=event_payload,
                        )
                    except Exception as source_exc:  # pragma: no cover - defensive
                        logger.warning(
                            "Workflow SSE source iteration failed for source_id=%s: %s",
                            source_id_str,
                            source_exc,
                        )
            except Exception as exc:  # pragma: no cover - defensive stream guard
                logger.warning(
                    "Workflow SSE space stream iteration failed for space_id=%s: %s",
                    space_id,
                    exc,
                )
                sequence += 1
                emitted_event = True
                yield stream_utils.sse_event_payload(
                    event="error",
                    sequence=sequence,
                    data={
                        "message": "Workflow stream iteration failed; retrying.",
                        "generated_at": stream_utils.now_iso(),
                    },
                )

            now_mono = asyncio.get_running_loop().time()
            if (
                not emitted_event
                and now_mono - last_heartbeat_mono
                >= stream_utils.STREAM_HEARTBEAT_SECONDS
            ):
                sequence += 1
                yield stream_utils.sse_event_payload(
                    event="heartbeat",
                    sequence=sequence,
                    data={"generated_at": stream_utils.now_iso()},
                )
                last_heartbeat_mono = now_mono
            elif emitted_event:
                last_heartbeat_mono = now_mono

            await asyncio.sleep(stream_utils.STREAM_TICK_SECONDS)

    return EventSourceResponse(_event_generator())


__all__ = [
    "WorkflowSpaceStreamQueryParams",
    "get_workflow_space_stream_query_params",
    "stream_source_workflow_monitor",
    "stream_space_workflow_cards",
]
