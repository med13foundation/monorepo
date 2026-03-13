"""SQLAlchemy adapter for graph-local space settings."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.domain.ports.space_registry_port import SpaceRegistryPort
from src.domain.ports.space_settings_port import SpaceSettingsPort
from src.infrastructure.repositories.kernel.kernel_space_registry_repository import (
    SqlAlchemyKernelSpaceRegistryRepository,
)
from src.type_definitions.common import ResearchSpaceSettings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class SqlAlchemyKernelSpaceSettingsRepository(SpaceSettingsPort):
    """Resolve graph-space settings from the graph-owned registry."""

    def __init__(
        self,
        session: Session,
        *,
        space_registry: SpaceRegistryPort | None = None,
    ) -> None:
        self._session = session
        self._space_registry = space_registry

    def get_settings(
        self,
        space_id: UUID,
    ) -> ResearchSpaceSettings | None:
        registry = self._space_registry or SqlAlchemyKernelSpaceRegistryRepository(
            self._session,
        )
        space = registry.get_by_id(space_id)
        if space is None:
            return None
        return space.settings


__all__ = ["SqlAlchemyKernelSpaceSettingsRepository"]
