"""Pack-registration contracts for graph platform startup."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

    from src.graph.core.domain_pack import GraphDomainPack


class GraphDomainPackRegistry(Protocol):
    """Registry interface for graph domain-pack startup and resolution."""

    def register(self, pack: GraphDomainPack) -> None:
        """Register one graph domain pack."""

    def registered_packs(self) -> Mapping[str, GraphDomainPack]:
        """Return registered graph domain packs keyed by normalized name."""

    def resolve(self, pack_name: str) -> GraphDomainPack | None:
        """Resolve one registered graph domain pack by name."""


@dataclass
class InMemoryGraphDomainPackRegistry:
    """In-memory registry used by the current graph runtime."""

    _packs: dict[str, GraphDomainPack] = field(default_factory=dict)

    def register(self, pack: GraphDomainPack) -> None:
        self._packs[pack.name.strip().lower()] = pack

    def registered_packs(self) -> Mapping[str, GraphDomainPack]:
        return dict(self._packs)

    def resolve(self, pack_name: str) -> GraphDomainPack | None:
        return self._packs.get(pack_name.strip().lower())
