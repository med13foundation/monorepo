"""Domain-neutral runtime identity defaults for graph domain packs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphRuntimeIdentity:
    """Default runtime identity values supplied by a graph domain pack."""

    service_name: str
    jwt_issuer: str
