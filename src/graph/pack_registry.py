"""Graph domain-pack registration and active-pack resolution."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from src.graph.core.pack_registration import (
    GraphDomainPackRegistry,
    InMemoryGraphDomainPackRegistry,
)
from src.graph.domain_biomedical.pack import get_biomedical_graph_domain_pack
from src.graph.domain_sports.pack import get_sports_graph_domain_pack

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src.graph.core.domain_pack import GraphDomainPack

_DEFAULT_GRAPH_DOMAIN_PACK = "biomedical"
_GRAPH_DOMAIN_PACK_REGISTRY = InMemoryGraphDomainPackRegistry()


def get_graph_domain_pack_registry() -> GraphDomainPackRegistry:
    """Return the process-local graph domain-pack registry."""
    return _GRAPH_DOMAIN_PACK_REGISTRY


def register_graph_domain_pack(
    pack: GraphDomainPack,
    *,
    registry: GraphDomainPackRegistry | None = None,
) -> None:
    """Register one graph domain pack with the chosen registry."""
    active_registry = registry or get_graph_domain_pack_registry()
    active_registry.register(pack)


def register_graph_domain_packs(
    packs: Iterable[GraphDomainPack],
    *,
    registry: GraphDomainPackRegistry | None = None,
) -> None:
    """Register multiple graph domain packs with the chosen registry."""
    active_registry = registry or get_graph_domain_pack_registry()
    for pack in packs:
        active_registry.register(pack)


def bootstrap_default_graph_domain_packs(
    *,
    registry: GraphDomainPackRegistry | None = None,
) -> None:
    """Register the built-in graph domain packs for the current runtime."""
    register_graph_domain_packs(
        (
            get_biomedical_graph_domain_pack(),
            get_sports_graph_domain_pack(),
        ),
        registry=registry,
    )


def get_registered_graph_domain_packs() -> dict[str, GraphDomainPack]:
    """Return registered graph domain packs keyed by pack name."""
    bootstrap_default_graph_domain_packs()
    return dict(get_graph_domain_pack_registry().registered_packs())


def resolve_graph_domain_pack() -> GraphDomainPack:
    """Resolve the active graph domain pack from runtime config."""
    registered_packs = get_registered_graph_domain_packs()
    configured_name = os.getenv("GRAPH_DOMAIN_PACK", _DEFAULT_GRAPH_DOMAIN_PACK)
    normalized_name = configured_name.strip().lower()
    pack = registered_packs.get(normalized_name)
    if pack is not None:
        return pack

    supported_names = ", ".join(sorted(registered_packs))
    message = (
        f"Unsupported GRAPH_DOMAIN_PACK '{configured_name}'. "
        f"Supported packs: {supported_names}"
    )
    raise RuntimeError(message)
