"""Unit tests for research space management service defaults."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.application.services.research_space_management_service import (
    CreateSpaceRequest,
    ResearchSpaceManagementService,
    UpdateSpaceRequest,
)
from src.domain.entities.user import User, UserRole, UserStatus

if TYPE_CHECKING:
    from src.domain.entities.research_space import ResearchSpace, SpaceStatus


class StubResearchSpaceRepository:
    """Minimal repository stub for create-space tests."""

    def __init__(self) -> None:
        self.saved_spaces: list[ResearchSpace] = []

    def slug_exists(self, slug: str) -> bool:
        return any(space.slug == slug for space in self.saved_spaces)

    def save(self, space: ResearchSpace) -> ResearchSpace:
        self.saved_spaces.append(space)
        return space

    def find_by_id(self, space_id: UUID) -> ResearchSpace | None:
        for space in self.saved_spaces:
            if space.id == space_id:
                return space
        return None

    def find_by_slug(self, slug: str) -> ResearchSpace | None:
        for space in self.saved_spaces:
            if space.slug == slug:
                return space
        return None

    def find_by_owner(
        self,
        owner_id: UUID,
        skip: int,
        limit: int,
    ) -> list[ResearchSpace]:
        _ = owner_id
        _ = skip
        _ = limit
        return []

    def find_by_status(
        self,
        status: SpaceStatus,
        skip: int,
        limit: int,
    ) -> list[ResearchSpace]:
        _ = status
        _ = skip
        _ = limit
        return []

    def find_active_spaces(self, skip: int, limit: int) -> list[ResearchSpace]:
        _ = skip
        _ = limit
        return []

    def search_by_name(self, query: str, skip: int, limit: int) -> list[ResearchSpace]:
        _ = query
        _ = skip
        _ = limit
        return []

    def count_by_owner(self, owner_id: UUID) -> int:
        _ = owner_id
        return 0

    def delete(self, space_id: UUID) -> bool:
        for index, space in enumerate(self.saved_spaces):
            if space.id == space_id:
                self.saved_spaces.pop(index)
                return True
        return False


class RecordingSpaceLifecycleSync:
    def __init__(self) -> None:
        self.spaces: list[ResearchSpace] = []

    def sync_space(self, space: ResearchSpace) -> None:
        self.spaces.append(space)


def test_create_space_defaults_relation_auto_promotion_disabled() -> None:
    repository = StubResearchSpaceRepository()
    service = ResearchSpaceManagementService(repository)

    created = service.create_space(
        CreateSpaceRequest(
            owner_id=uuid4(),
            name="Claim First Space",
            slug="claim-first-space",
            settings={},
            tags=[],
        ),
    )

    assert created.settings["relation_auto_promotion"]["enabled"] is False


def test_create_space_preserves_explicit_relation_auto_promotion_setting() -> None:
    repository = StubResearchSpaceRepository()
    service = ResearchSpaceManagementService(repository)

    created = service.create_space(
        CreateSpaceRequest(
            owner_id=uuid4(),
            name="Claim First Space Explicit",
            slug="claim-first-space-explicit",
            settings={"relation_auto_promotion": {"enabled": True}},
            tags=[],
        ),
    )

    assert created.settings["relation_auto_promotion"]["enabled"] is True


def test_create_space_syncs_graph_tenant_snapshot() -> None:
    repository = StubResearchSpaceRepository()
    sync = RecordingSpaceLifecycleSync()
    service = ResearchSpaceManagementService(
        repository,
        space_lifecycle_sync=sync,
    )

    created = service.create_space(
        CreateSpaceRequest(
            owner_id=uuid4(),
            name="Graph Sync",
            slug="graph-sync",
            settings={},
            tags=[],
        ),
    )

    assert sync.spaces == [created]


def test_update_space_syncs_saved_snapshot() -> None:
    repository = StubResearchSpaceRepository()
    sync = RecordingSpaceLifecycleSync()
    service = ResearchSpaceManagementService(
        repository,
        space_lifecycle_sync=sync,
    )
    created = service.create_space(
        CreateSpaceRequest(
            owner_id=uuid4(),
            name="Original",
            slug="graph-sync",
            settings={},
            tags=[],
        ),
    )
    sync.spaces.clear()

    updated = service.update_space(
        created.id,
        UpdateSpaceRequest(name="Updated"),
        User(
            id=created.owner_id,
            email="owner@example.com",
            username="owner",
            full_name="Owner",
            hashed_password="hashed",
            role=UserRole.RESEARCHER,
            status=UserStatus.ACTIVE,
        ),
    )

    assert updated is not None
    assert updated.name == "Updated"
    assert sync.spaces == [updated]


def test_delete_space_syncs_archived_snapshot() -> None:
    repository = StubResearchSpaceRepository()
    sync = RecordingSpaceLifecycleSync()
    service = ResearchSpaceManagementService(
        repository,
        space_lifecycle_sync=sync,
    )
    created = service.create_space(
        CreateSpaceRequest(
            owner_id=uuid4(),
            name="Delete Me",
            slug="delete-me",
            settings={},
            tags=[],
        ),
    )
    sync.spaces.clear()

    deleted = service.delete_space(created.id, created.owner_id)

    assert deleted is True
    assert len(sync.spaces) == 1
    assert sync.spaces[0].id == created.id
    assert sync.spaces[0].status.value == "archived"
