"""Graph-local port for resolving space settings."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.type_definitions.common import ResearchSpaceSettings


class SpaceSettingsPort(ABC):
    """Resolve graph-space settings without depending on platform space models."""

    @abstractmethod
    def get_settings(
        self,
        space_id: UUID,
    ) -> ResearchSpaceSettings | None:
        """Return settings for one graph space, if present."""


__all__ = ["SpaceSettingsPort"]
