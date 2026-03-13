"""Graph-owned space registry routes for the standalone graph service."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from services.graph_api.auth import (
    get_current_active_user,
    is_graph_service_admin,
)
from services.graph_api.database import get_session, set_session_rls_context
from services.graph_api.dependencies import (
    get_space_membership_repository,
    get_space_registry_port,
)
from src.domain.entities.kernel.spaces import KernelSpaceRegistryEntry
from src.domain.entities.research_space_membership import (
    MembershipRole,
    ResearchSpaceMembership,
)
from src.domain.entities.user import User
from src.domain.ports.space_registry_port import SpaceRegistryPort
from src.infrastructure.repositories.kernel.kernel_space_membership_repository import (
    SqlAlchemyKernelSpaceMembershipRepository,
)
from src.type_definitions.common import ResearchSpaceSettings

router = APIRouter(prefix="/v1/admin/spaces", tags=["spaces"])

GraphSpaceStatus = Literal["active", "inactive", "archived", "suspended"]


def _empty_space_settings() -> ResearchSpaceSettings:
    return {}


class GraphSpaceRegistryResponse(BaseModel):
    """Serialized graph-space registry entry."""

    model_config = ConfigDict(strict=True)

    id: UUID
    slug: str
    name: str
    description: str | None
    owner_id: UUID
    status: GraphSpaceStatus
    settings: ResearchSpaceSettings
    sync_source: str | None = None
    sync_fingerprint: str | None = None
    source_updated_at: datetime | None = None
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class GraphSpaceRegistryListResponse(BaseModel):
    """Collection response for graph-space registry entries."""

    model_config = ConfigDict(strict=True)

    spaces: list[GraphSpaceRegistryResponse]
    total: int


class GraphSpaceRegistryUpsertRequest(BaseModel):
    """Create or update one graph-space registry entry."""

    model_config = ConfigDict(strict=False)

    slug: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=4000)
    owner_id: UUID
    status: GraphSpaceStatus = "active"
    settings: ResearchSpaceSettings = Field(default_factory=_empty_space_settings)


class GraphSpaceMembershipResponse(BaseModel):
    """Serialized graph-space membership entry."""

    model_config = ConfigDict(strict=True)

    id: UUID
    space_id: UUID
    user_id: UUID
    role: Literal["owner", "admin", "curator", "researcher", "viewer"]
    invited_by: UUID | None
    invited_at: datetime | None
    joined_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class GraphSpaceMembershipListResponse(BaseModel):
    """Collection response for graph-space memberships."""

    model_config = ConfigDict(strict=True)

    memberships: list[GraphSpaceMembershipResponse]
    total: int


class GraphSpaceMembershipUpsertRequest(BaseModel):
    """Create or update one graph-space membership."""

    model_config = ConfigDict(strict=False)

    role: Literal["admin", "curator", "researcher", "viewer"]
    invited_by: UUID | None = None
    invited_at: datetime | None = None
    joined_at: datetime | None = None
    is_active: bool = True


class GraphSpaceSyncMembershipRequest(BaseModel):
    """Desired synced membership state for one graph space."""

    model_config = ConfigDict(strict=False)

    user_id: UUID
    role: Literal["admin", "curator", "researcher", "viewer"]
    invited_by: UUID | None = None
    invited_at: datetime | None = None
    joined_at: datetime | None = None
    is_active: bool = True


class GraphSpaceSyncRequest(BaseModel):
    """Atomic graph-space tenant sync payload."""

    model_config = ConfigDict(strict=False)

    slug: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=4000)
    owner_id: UUID
    status: GraphSpaceStatus = "active"
    settings: ResearchSpaceSettings = Field(default_factory=_empty_space_settings)
    sync_source: str | None = Field(default="platform_control_plane", max_length=64)
    sync_fingerprint: str | None = Field(default=None, max_length=64)
    source_updated_at: datetime | None = None
    memberships: list[GraphSpaceSyncMembershipRequest] = Field(default_factory=list)


class GraphSpaceSyncResponse(BaseModel):
    """Atomic graph-space tenant sync result."""

    model_config = ConfigDict(strict=True)

    applied: bool
    space: GraphSpaceRegistryResponse
    memberships: list[GraphSpaceMembershipResponse]
    total_memberships: int


def _require_graph_admin(*, current_user: User, session: Session) -> None:
    if not is_graph_service_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Graph service admin access is required for this operation",
        )
    set_session_rls_context(
        session,
        current_user_id=current_user.id,
        has_phi_access=True,
        is_admin=True,
        bypass_rls=True,
    )


def _response_from_entry(
    entry: KernelSpaceRegistryEntry,
) -> GraphSpaceRegistryResponse:
    return GraphSpaceRegistryResponse(
        id=entry.id,
        slug=entry.slug,
        name=entry.name,
        description=entry.description,
        owner_id=entry.owner_id,
        status=cast(GraphSpaceStatus, entry.status),
        settings=entry.settings,
        sync_source=entry.sync_source,
        sync_fingerprint=entry.sync_fingerprint,
        source_updated_at=entry.source_updated_at,
        last_synced_at=entry.last_synced_at,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _membership_response(
    membership: ResearchSpaceMembership,
) -> GraphSpaceMembershipResponse:
    return GraphSpaceMembershipResponse(
        id=membership.id,
        space_id=membership.space_id,
        user_id=membership.user_id,
        role=membership.role.value,
        invited_by=membership.invited_by,
        invited_at=membership.invited_at,
        joined_at=membership.joined_at,
        is_active=membership.is_active,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


def _sync_fingerprint(
    *,
    request: GraphSpaceSyncRequest,
) -> str:
    normalized_memberships = sorted(
        [
            {
                "user_id": str(membership.user_id),
                "role": membership.role,
                "invited_by": (
                    str(membership.invited_by)
                    if membership.invited_by is not None
                    else None
                ),
                "invited_at": (
                    membership.invited_at.astimezone(UTC).isoformat()
                    if membership.invited_at is not None
                    else None
                ),
                "joined_at": (
                    membership.joined_at.astimezone(UTC).isoformat()
                    if membership.joined_at is not None
                    else None
                ),
                "is_active": membership.is_active,
            }
            for membership in request.memberships
        ],
        key=lambda membership: (membership["user_id"], membership["role"]),
    )
    payload = {
        "slug": request.slug,
        "name": request.name,
        "description": request.description,
        "owner_id": str(request.owner_id),
        "status": request.status,
        "settings": request.settings,
        "source_updated_at": (
            request.source_updated_at.astimezone(UTC).isoformat()
            if request.source_updated_at is not None
            else None
        ),
        "memberships": normalized_memberships,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    ).hexdigest()


@router.get(
    "",
    response_model=GraphSpaceRegistryListResponse,
    summary="List graph-space registry entries",
)
def list_graph_spaces(
    *,
    current_user: User = Depends(get_current_active_user),
    space_registry: SpaceRegistryPort = Depends(get_space_registry_port),
    session: Session = Depends(get_session),
) -> GraphSpaceRegistryListResponse:
    _require_graph_admin(current_user=current_user, session=session)
    entries = space_registry.list_entries()
    return GraphSpaceRegistryListResponse(
        spaces=[_response_from_entry(entry) for entry in entries],
        total=len(entries),
    )


@router.get(
    "/{space_id}",
    response_model=GraphSpaceRegistryResponse,
    summary="Fetch one graph-space registry entry",
)
def get_graph_space(
    space_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_registry: SpaceRegistryPort = Depends(get_space_registry_port),
    session: Session = Depends(get_session),
) -> GraphSpaceRegistryResponse:
    _require_graph_admin(current_user=current_user, session=session)
    entry = space_registry.get_by_id(space_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Graph space not found",
        )
    return _response_from_entry(entry)


@router.put(
    "/{space_id}",
    response_model=GraphSpaceRegistryResponse,
    summary="Create or update one graph-space registry entry",
)
def upsert_graph_space(
    space_id: UUID,
    request: GraphSpaceRegistryUpsertRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_registry: SpaceRegistryPort = Depends(get_space_registry_port),
    session: Session = Depends(get_session),
) -> GraphSpaceRegistryResponse:
    _require_graph_admin(current_user=current_user, session=session)
    existing_entry = space_registry.get_by_id(space_id)
    entry = KernelSpaceRegistryEntry(
        id=space_id,
        slug=request.slug,
        name=request.name,
        description=request.description,
        owner_id=request.owner_id,
        status=request.status,
        settings=request.settings,
        created_at=(
            existing_entry.created_at
            if existing_entry is not None
            else datetime.now(UTC)
        ),
        updated_at=(
            existing_entry.updated_at
            if existing_entry is not None
            else datetime.now(UTC)
        ),
    )
    saved_entry = space_registry.save(entry)
    session.commit()
    return _response_from_entry(saved_entry)


@router.get(
    "/{space_id}/memberships",
    response_model=GraphSpaceMembershipListResponse,
    summary="List graph-space memberships",
)
def list_graph_space_memberships(
    space_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_registry: SpaceRegistryPort = Depends(get_space_registry_port),
    membership_repository: SqlAlchemyKernelSpaceMembershipRepository = Depends(
        get_space_membership_repository,
    ),
    session: Session = Depends(get_session),
) -> GraphSpaceMembershipListResponse:
    _require_graph_admin(current_user=current_user, session=session)
    if space_registry.get_by_id(space_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Graph space not found",
        )
    memberships = membership_repository.list_for_space(space_id)
    return GraphSpaceMembershipListResponse(
        memberships=[_membership_response(membership) for membership in memberships],
        total=len(memberships),
    )


@router.put(
    "/{space_id}/memberships/{user_id}",
    response_model=GraphSpaceMembershipResponse,
    summary="Create or update one graph-space membership",
)
def upsert_graph_space_membership(
    space_id: UUID,
    user_id: UUID,
    request: GraphSpaceMembershipUpsertRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_registry: SpaceRegistryPort = Depends(get_space_registry_port),
    membership_repository: SqlAlchemyKernelSpaceMembershipRepository = Depends(
        get_space_membership_repository,
    ),
    session: Session = Depends(get_session),
) -> GraphSpaceMembershipResponse:
    _require_graph_admin(current_user=current_user, session=session)
    if space_registry.get_by_id(space_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Graph space not found",
        )
    existing_membership = membership_repository.get_for_space_user(
        space_id=space_id,
        user_id=user_id,
    )
    now = datetime.now(UTC)
    membership = ResearchSpaceMembership(
        id=existing_membership.id if existing_membership is not None else uuid4(),
        space_id=space_id,
        user_id=user_id,
        role=MembershipRole(request.role),
        invited_by=request.invited_by,
        invited_at=request.invited_at,
        joined_at=request.joined_at,
        is_active=request.is_active,
        created_at=(
            existing_membership.created_at if existing_membership is not None else now
        ),
        updated_at=now,
    )
    saved_membership = membership_repository.save(membership)
    session.commit()
    return _membership_response(saved_membership)


@router.post(
    "/{space_id}/sync",
    response_model=GraphSpaceSyncResponse,
    summary="Atomically sync graph-space registry and memberships",
)
def sync_graph_space(
    space_id: UUID,
    request: GraphSpaceSyncRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_registry: SpaceRegistryPort = Depends(get_space_registry_port),
    membership_repository: SqlAlchemyKernelSpaceMembershipRepository = Depends(
        get_space_membership_repository,
    ),
    session: Session = Depends(get_session),
) -> GraphSpaceSyncResponse:
    _require_graph_admin(current_user=current_user, session=session)
    existing_entry = space_registry.get_by_id(space_id)
    now = datetime.now(UTC)
    effective_sync_fingerprint = request.sync_fingerprint or _sync_fingerprint(
        request=request,
    )
    existing_memberships = membership_repository.list_for_space(
        space_id=space_id,
    )
    if (
        existing_entry is not None
        and existing_entry.sync_fingerprint == effective_sync_fingerprint
    ):
        return GraphSpaceSyncResponse(
            applied=False,
            space=_response_from_entry(existing_entry),
            memberships=[
                _membership_response(membership) for membership in existing_memberships
            ],
            total_memberships=len(existing_memberships),
        )
    saved_entry = space_registry.save(
        KernelSpaceRegistryEntry(
            id=space_id,
            slug=request.slug,
            name=request.name,
            description=request.description,
            owner_id=request.owner_id,
            status=request.status,
            settings=request.settings,
            sync_source=request.sync_source,
            sync_fingerprint=effective_sync_fingerprint,
            source_updated_at=request.source_updated_at,
            last_synced_at=now,
            created_at=(
                existing_entry.created_at if existing_entry is not None else now
            ),
            updated_at=now,
        ),
    )
    synced_memberships = membership_repository.replace_for_space(
        space_id=space_id,
        memberships=[
            ResearchSpaceMembership(
                id=(
                    existing_membership.id
                    if (
                        existing_membership := membership_repository.get_for_space_user(
                            space_id=space_id,
                            user_id=membership.user_id,
                        )
                    )
                    is not None
                    else uuid4()
                ),
                space_id=space_id,
                user_id=membership.user_id,
                role=MembershipRole(membership.role),
                invited_by=membership.invited_by,
                invited_at=membership.invited_at,
                joined_at=membership.joined_at,
                is_active=membership.is_active,
                created_at=(
                    existing_membership.created_at
                    if existing_membership is not None
                    else now
                ),
                updated_at=now,
            )
            for membership in request.memberships
        ],
    )
    session.commit()
    return GraphSpaceSyncResponse(
        applied=True,
        space=_response_from_entry(saved_entry),
        memberships=[
            _membership_response(membership) for membership in synced_memberships
        ],
        total_memberships=len(synced_memberships),
    )


__all__ = [
    "GraphSpaceRegistryListResponse",
    "GraphSpaceRegistryResponse",
    "GraphSpaceRegistryUpsertRequest",
    "GraphSpaceMembershipListResponse",
    "GraphSpaceMembershipResponse",
    "GraphSpaceMembershipUpsertRequest",
    "GraphSpaceSyncRequest",
    "GraphSpaceSyncResponse",
    "router",
]
