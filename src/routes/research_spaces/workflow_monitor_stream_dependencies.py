"""Shared dependencies and async offload helpers for workflow SSE routes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.application.services.source_workflow_monitor_service import (
    SourceWorkflowMonitorService,
)
from src.database.session import get_session
from src.domain.entities.user import UserRole
from src.type_definitions.common import JSONObject

from . import dependencies as space_dependencies
from . import workflow_monitor_stream_utils as stream_utils


@dataclass
class MembershipContext:
    membership_service: MembershipManagementService
    session: Session


def get_membership_context(
    membership_service: MembershipManagementService = Depends(
        space_dependencies.get_membership_service,
    ),
    session: Session = Depends(get_session),
) -> MembershipContext:
    return MembershipContext(
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


async def verify_stream_membership(
    *,
    space_id: UUID,
    current_user_id: UUID,
    current_user_role: UserRole | None,
    membership_context: MembershipContext,
) -> None:
    await asyncio.to_thread(
        space_dependencies.verify_space_membership,
        space_id,
        current_user_id,
        membership_context.membership_service,
        membership_context.session,
        current_user_role,
    )


async def load_monitor_payload(
    *,
    monitor_service: SourceWorkflowMonitorService,
    space_id: UUID,
    source_id: UUID,
    run_id: str | None,
    limit: int,
    include_graph: bool,
) -> JSONObject:
    return await asyncio.to_thread(
        monitor_service.get_source_workflow_monitor,
        space_id=space_id,
        source_id=source_id,
        run_id=run_id,
        limit=limit,
        include_graph=include_graph,
    )


async def load_events_payload(
    *,
    monitor_service: SourceWorkflowMonitorService,
    space_id: UUID,
    source_id: UUID,
    run_id: str | None,
    limit: int,
    since: str | None,
) -> JSONObject:
    return await asyncio.to_thread(
        monitor_service.list_workflow_events,
        space_id=space_id,
        source_id=source_id,
        run_id=run_id,
        limit=limit,
        since=since,
    )


async def resolve_stream_source_ids(
    *,
    session: Session,
    space_id: UUID,
    include_inactive: bool,
    requested_source_ids: list[str],
) -> list[str]:
    return await asyncio.to_thread(
        stream_utils.resolve_space_source_ids,
        session=session,
        space_id=space_id,
        include_inactive=include_inactive,
        requested_source_ids=requested_source_ids,
    )


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
