"""Route-level mapping tests for graph tenant sync failures."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.domain.entities.user import User, UserRole, UserStatus
from src.infrastructure.graph_service.errors import GraphServiceClientError
from src.routes.research_spaces import membership_routes, space_routes
from src.routes.research_spaces.schemas import (
    CreateSpaceRequestModel,
    InviteMemberRequestModel,
)


def _build_user() -> User:
    return User(
        id=uuid4(),
        email="graph-sync@example.com",
        username="graph-sync",
        full_name="Graph Sync",
        hashed_password="hashed-password",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )


class _FailingSpaceServiceStub:
    def create_space(self, request: object) -> object:  # noqa: ARG002
        raise GraphServiceClientError(
            "graph sync failed",
            detail="graph sync failed",
        )


class _FailingMembershipServiceStub:
    def invite_member(self, request: object) -> object:  # noqa: ARG002
        raise GraphServiceClientError(
            "graph sync failed",
            detail="graph sync failed",
        )


def test_create_space_route_maps_graph_sync_failure_to_500() -> None:
    current_user = _build_user()

    with pytest.raises(HTTPException) as exc_info:
        space_routes.create_space(
            CreateSpaceRequestModel(
                name="Graph Sync Space",
                slug="graph-sync-space",
                description="Graph sync route test",
                settings={"review_threshold": 0.7},
                tags=[],
            ),
            current_user=current_user,
            service=_FailingSpaceServiceStub(),
        )

    assert exc_info.value.status_code == 500
    assert "graph-space sync failed" in str(exc_info.value.detail)


def test_invite_member_route_maps_graph_sync_failure_to_500() -> None:
    current_user = _build_user()

    with pytest.raises(HTTPException) as exc_info:
        membership_routes.invite_member(
            uuid4(),
            InviteMemberRequestModel(
                user_id=uuid4(),
                role="researcher",
            ),
            current_user=current_user,
            service=_FailingMembershipServiceStub(),
            session=object(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 500
    assert "graph-space sync failed" in str(exc_info.value.detail)
