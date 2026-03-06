"""Unit tests for research-space discovery access rules."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.domain.entities.research_space import ResearchSpace, SpaceStatus
from src.domain.entities.user import User, UserRole, UserStatus
from src.routes import research_space_discovery as routes


def _build_context(space_id: object | None = None) -> routes.SpaceDiscoveryContext:
    resolved_space_id = uuid4() if space_id is None else space_id
    service = SimpleNamespace(space_id=resolved_space_id)
    return routes.SpaceDiscoveryContext(db_session=object(), service=service)


def test_require_space_access_allows_space_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    space_id = uuid4()
    user = User(
        id=user_id,
        email="owner@example.com",
        username="owner",
        full_name="Owner Example",
        hashed_password="hashed",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )
    context = _build_context(space_id=space_id)
    owned_space = ResearchSpace(
        id=space_id,
        slug="owned-space",
        name="Owned Space",
        description="Owner-created space",
        owner_id=user_id,
        status=SpaceStatus.ACTIVE,
        settings={},
        tags=[],
    )

    monkeypatch.setattr(
        routes,
        "SqlAlchemyResearchSpaceRepository",
        lambda session: SimpleNamespace(find_by_id=lambda _: owned_space),
    )
    monkeypatch.setattr(
        routes,
        "SqlAlchemyResearchSpaceMembershipRepository",
        lambda session: SimpleNamespace(find_by_space_and_user=lambda *_: None),
    )

    routes.require_space_access(context, user)


def test_require_space_access_rejects_non_member_non_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(
        id=uuid4(),
        email="viewer@example.com",
        username="viewer",
        full_name="Viewer Example",
        hashed_password="hashed",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )
    context = _build_context()

    monkeypatch.setattr(
        routes,
        "SqlAlchemyResearchSpaceRepository",
        lambda session: SimpleNamespace(find_by_id=lambda _: None),
    )
    monkeypatch.setattr(
        routes,
        "SqlAlchemyResearchSpaceMembershipRepository",
        lambda session: SimpleNamespace(find_by_space_and_user=lambda *_: None),
    )

    with pytest.raises(
        HTTPException,
        match="You do not have access to this research space",
    ):
        routes.require_space_access(context, user)
