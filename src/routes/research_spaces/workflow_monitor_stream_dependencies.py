"""Shared dependencies and async offload helpers for workflow SSE routes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, Field

from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.application.services.source_workflow_monitor_service import (
    SourceWorkflowMonitorService,
)
from src.database.session import SessionLocal, set_session_rls_context
from src.domain.entities.user import UserRole
from src.infrastructure.repositories import SqlAlchemyResearchSpaceRepository
from src.infrastructure.repositories.research_space_membership_repository import (
    SqlAlchemyResearchSpaceMembershipRepository,
)
from src.type_definitions.common import JSONObject

from . import dependencies as space_dependencies
from . import workflow_monitor_routes as monitor_routes
from . import workflow_monitor_stream_utils as stream_utils

if TYPE_CHECKING:
    from typing import Protocol

    from sqlalchemy.orm import Session

    class WorkflowMonitorReader(Protocol):
        def get_source_workflow_monitor(
            self,
            *,
            space_id: UUID,
            source_id: UUID,
            run_id: str | None,
            limit: int,
            include_graph: bool,
        ) -> JSONObject: ...

        def list_workflow_events(
            self,
            *,
            space_id: UUID,
            source_id: UUID,
            run_id: str | None,
            limit: int,
            since: str | None,
        ) -> JSONObject: ...


@dataclass
class MembershipContext:
    membership_service: object | None = None
    session: object | None = None


def get_membership_context() -> MembershipContext:
    return MembershipContext()


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


async def verify_stream_membership(
    *,
    space_id: UUID,
    current_user_id: UUID,
    current_user_role: UserRole | None,
    membership_context: MembershipContext | None = None,
) -> None:
    await asyncio.to_thread(
        _verify_stream_membership_sync,
        space_id=space_id,
        current_user_id=current_user_id,
        current_user_role=current_user_role,
    )


async def load_monitor_payload(
    *,
    monitor_service: WorkflowMonitorReader,
    space_id: UUID,
    source_id: UUID,
    run_id: str | None,
    limit: int,
    include_graph: bool,
    current_user_id: UUID,
    current_user_role: UserRole | None,
) -> JSONObject:
    if not isinstance(monitor_service, SourceWorkflowMonitorService):
        return await asyncio.to_thread(
            monitor_service.get_source_workflow_monitor,
            space_id=space_id,
            source_id=source_id,
            run_id=run_id,
            limit=limit,
            include_graph=include_graph,
        )

    return await asyncio.to_thread(
        _load_monitor_payload_sync,
        current_user_id=current_user_id,
        current_user_role=current_user_role,
        space_id=space_id,
        source_id=source_id,
        run_id=run_id,
        limit=limit,
        include_graph=include_graph,
    )


async def load_events_payload(
    *,
    monitor_service: WorkflowMonitorReader,
    space_id: UUID,
    source_id: UUID,
    run_id: str | None,
    limit: int,
    since: str | None,
    current_user_id: UUID,
    current_user_role: UserRole | None,
) -> JSONObject:
    if not isinstance(monitor_service, SourceWorkflowMonitorService):
        return await asyncio.to_thread(
            monitor_service.list_workflow_events,
            space_id=space_id,
            source_id=source_id,
            run_id=run_id,
            limit=limit,
            since=since,
        )

    return await asyncio.to_thread(
        _load_events_payload_sync,
        current_user_id=current_user_id,
        current_user_role=current_user_role,
        space_id=space_id,
        source_id=source_id,
        run_id=run_id,
        limit=limit,
        since=since,
    )


async def resolve_stream_source_ids(
    *,
    space_id: UUID,
    include_inactive: bool,
    requested_source_ids: list[str],
    current_user_id: UUID,
    current_user_role: UserRole | None,
) -> list[str]:
    return await asyncio.to_thread(
        _resolve_stream_source_ids_sync,
        current_user_id=current_user_id,
        current_user_role=current_user_role,
        space_id=space_id,
        include_inactive=include_inactive,
        requested_source_ids=requested_source_ids,
    )


def _is_admin_user(current_user_role: UserRole | None) -> bool:
    return current_user_role == UserRole.ADMIN


def _open_stream_session(
    *,
    current_user_id: UUID,
    current_user_role: UserRole | None,
) -> Session:
    session = SessionLocal()
    is_admin_user = _is_admin_user(current_user_role)
    set_session_rls_context(
        session,
        current_user_id=current_user_id,
        has_phi_access=is_admin_user,
        is_admin=is_admin_user,
        bypass_rls=False,
    )
    return session


def _build_membership_service(session: Session) -> MembershipManagementService:
    membership_repository = SqlAlchemyResearchSpaceMembershipRepository(session=session)
    space_repository = SqlAlchemyResearchSpaceRepository(session=session)
    return MembershipManagementService(
        membership_repository=membership_repository,
        research_space_repository=space_repository,
    )


def _build_monitor_service(session: Session) -> SourceWorkflowMonitorService:
    return SourceWorkflowMonitorService(
        session=session,
        run_progress=monitor_routes.get_run_progress_port(),
    )


def _verify_stream_membership_sync(
    *,
    space_id: UUID,
    current_user_id: UUID,
    current_user_role: UserRole | None,
) -> None:
    session = _open_stream_session(
        current_user_id=current_user_id,
        current_user_role=current_user_role,
    )
    try:
        membership_service = _build_membership_service(session)
        space_dependencies.verify_space_membership(
            space_id,
            current_user_id,
            membership_service,
            session,
            current_user_role,
        )
    finally:
        session.close()


def _load_monitor_payload_sync(
    *,
    current_user_id: UUID,
    current_user_role: UserRole | None,
    space_id: UUID,
    source_id: UUID,
    run_id: str | None,
    limit: int,
    include_graph: bool,
) -> JSONObject:
    session = _open_stream_session(
        current_user_id=current_user_id,
        current_user_role=current_user_role,
    )
    try:
        monitor_service = _build_monitor_service(session)
        return monitor_service.get_source_workflow_monitor(
            space_id=space_id,
            source_id=source_id,
            run_id=run_id,
            limit=limit,
            include_graph=include_graph,
        )
    finally:
        session.close()


def _load_events_payload_sync(
    *,
    current_user_id: UUID,
    current_user_role: UserRole | None,
    space_id: UUID,
    source_id: UUID,
    run_id: str | None,
    limit: int,
    since: str | None,
) -> JSONObject:
    session = _open_stream_session(
        current_user_id=current_user_id,
        current_user_role=current_user_role,
    )
    try:
        monitor_service = _build_monitor_service(session)
        return monitor_service.list_workflow_events(
            space_id=space_id,
            source_id=source_id,
            run_id=run_id,
            limit=limit,
            since=since,
        )
    finally:
        session.close()


def _resolve_stream_source_ids_sync(
    *,
    current_user_id: UUID,
    current_user_role: UserRole | None,
    space_id: UUID,
    include_inactive: bool,
    requested_source_ids: list[str],
) -> list[str]:
    session = _open_stream_session(
        current_user_id=current_user_id,
        current_user_role=current_user_role,
    )
    try:
        return stream_utils.resolve_space_source_ids(
            session=session,
            space_id=space_id,
            include_inactive=include_inactive,
            requested_source_ids=requested_source_ids,
        )
    finally:
        session.close()


__all__ = [
    "MembershipContext",
    "WorkflowSpaceStreamQueryParams",
    "get_membership_context",
    "get_workflow_space_stream_query_params",
    "load_events_payload",
    "load_monitor_payload",
    "resolve_stream_source_ids",
    "verify_stream_membership",
]
