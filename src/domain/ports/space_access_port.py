"""Graph-local port for space access resolution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.research_space_membership import MembershipRole


class SpaceAccessPort(ABC):
    """Resolve one caller's effective role within one graph space."""

    @abstractmethod
    def get_effective_role(
        self,
        space_id: UUID,
        user_id: UUID,
    ) -> MembershipRole | None:
        """Return the effective role for one user in one space."""


__all__ = ["SpaceAccessPort"]
