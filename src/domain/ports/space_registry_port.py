"""Graph-local port for tenant space registry lookup."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.kernel.spaces import KernelSpaceRegistryEntry


class SpaceRegistryPort(ABC):
    """Resolve graph-local space registry metadata."""

    @abstractmethod
    def get_by_id(
        self,
        space_id: UUID,
    ) -> KernelSpaceRegistryEntry | None:
        """Fetch one graph space registry entry."""

    @abstractmethod
    def list_space_ids(self) -> list[UUID]:
        """List all graph space ids known to the registry."""

    @abstractmethod
    def list_entries(self) -> list[KernelSpaceRegistryEntry]:
        """List all graph space registry entries."""

    @abstractmethod
    def save(
        self,
        entry: KernelSpaceRegistryEntry,
    ) -> KernelSpaceRegistryEntry:
        """Create or update one graph space registry entry."""


__all__ = ["SpaceRegistryPort"]
