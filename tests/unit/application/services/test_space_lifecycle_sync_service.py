"""Unit coverage for platform-to-graph space reconciliation service."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.application.services.space_lifecycle_sync_service import (
    SpaceLifecycleSyncService,
)
from src.domain.entities.research_space import ResearchSpace, SpaceStatus


def _build_space(*, status: SpaceStatus = SpaceStatus.ACTIVE) -> ResearchSpace:
    return ResearchSpace(
        id=uuid4(),
        slug=f"space-{uuid4().hex[:8]}",
        name="Graph Sync Space",
        description="Graph tenant reconciliation test",
        owner_id=uuid4(),
        status=status,
        settings={},
        tags=[],
    )


class StubResearchSpaceRepository:
    def __init__(self, spaces: list[ResearchSpace]) -> None:
        self._spaces = list(spaces)
        self.find_by_status_calls: list[tuple[SpaceStatus, int, int]] = []

    def save(self, space: ResearchSpace) -> ResearchSpace:
        self._spaces.append(space)
        return space

    def find_by_id(self, space_id: UUID) -> ResearchSpace | None:
        for space in self._spaces:
            if space.id == space_id:
                return space
        return None

    def find_by_slug(self, slug: str) -> ResearchSpace | None:
        for space in self._spaces:
            if space.slug == slug:
                return space
        return None

    def find_by_owner(
        self,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        del owner_id, skip, limit
        return []

    def find_by_status(
        self,
        status: SpaceStatus,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        self.find_by_status_calls.append((status, skip, limit))
        matches = [space for space in self._spaces if space.status == status]
        return matches[skip : skip + limit]

    def find_active_spaces(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        return self.find_by_status(SpaceStatus.ACTIVE, skip=skip, limit=limit)

    def search_by_name(
        self,
        query: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        del query, skip, limit
        return []

    def slug_exists(self, slug: str) -> bool:
        return any(space.slug == slug for space in self._spaces)

    def delete(self, space_id: UUID) -> bool:
        del space_id
        return False

    def exists(self, space_id: UUID) -> bool:
        return self.find_by_id(space_id) is not None

    def count_by_owner(self, owner_id: UUID) -> int:
        return sum(1 for space in self._spaces if space.owner_id == owner_id)


class RecordingSpaceLifecycleSync:
    def __init__(self) -> None:
        self.synced_spaces: list[ResearchSpace] = []

    def sync_space(self, space: ResearchSpace) -> None:
        self.synced_spaces.append(space)


def test_sync_space_syncs_requested_space() -> None:
    space = _build_space(status=SpaceStatus.ACTIVE)
    repository = StubResearchSpaceRepository([space])
    sync = RecordingSpaceLifecycleSync()
    service = SpaceLifecycleSyncService(repository, sync)

    synced = service.sync_space(space.id)

    assert synced == space
    assert sync.synced_spaces == [space]


def test_sync_space_raises_for_unknown_space() -> None:
    service = SpaceLifecycleSyncService(
        StubResearchSpaceRepository([]),
        RecordingSpaceLifecycleSync(),
    )

    with pytest.raises(ValueError, match="not found"):
        service.sync_space(uuid4())


def test_sync_spaces_pages_through_requested_statuses() -> None:
    active_one = _build_space(status=SpaceStatus.ACTIVE)
    active_two = _build_space(status=SpaceStatus.ACTIVE)
    archived = _build_space(status=SpaceStatus.ARCHIVED)
    repository = StubResearchSpaceRepository([active_one, active_two, archived])
    sync = RecordingSpaceLifecycleSync()
    service = SpaceLifecycleSyncService(repository, sync)

    summary = service.sync_spaces(
        statuses=(SpaceStatus.ACTIVE, SpaceStatus.ARCHIVED),
        batch_size=1,
    )

    assert summary.total_spaces == 3
    assert summary.synced_space_ids == (
        active_one.id,
        active_two.id,
        archived.id,
    )
    assert summary.statuses == ("active", "archived")
    assert sync.synced_spaces == [active_one, active_two, archived]
    assert repository.find_by_status_calls == [
        (SpaceStatus.ACTIVE, 0, 1),
        (SpaceStatus.ACTIVE, 1, 1),
        (SpaceStatus.ACTIVE, 2, 1),
        (SpaceStatus.ARCHIVED, 0, 1),
        (SpaceStatus.ARCHIVED, 1, 1),
    ]
