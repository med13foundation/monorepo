"""Unit tests for research space management service defaults."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.application.services.research_space_management_service import (
    CreateSpaceRequest,
    ResearchSpaceManagementService,
)

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
        _ = space_id
        return False


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
