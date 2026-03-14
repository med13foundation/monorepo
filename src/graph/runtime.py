"""Shared runtime helpers for active graph-pack derived configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.graph.pack_registry import resolve_graph_domain_pack

if TYPE_CHECKING:
    from src.graph.core.domain_context_policy import GraphDomainContextPolicy
    from src.graph.core.domain_pack import GraphDomainPack
    from src.graph.core.relation_autopromotion_defaults import (
        RelationAutopromotionDefaults,
    )


def create_graph_domain_pack() -> GraphDomainPack:
    """Return the active graph domain pack for runtime composition."""
    return resolve_graph_domain_pack()


def create_graph_domain_context_policy() -> GraphDomainContextPolicy:
    """Return the active-pack domain-context policy for runtime callers."""
    return create_graph_domain_pack().domain_context_policy


def create_relation_autopromotion_defaults() -> RelationAutopromotionDefaults:
    """Return the active-pack relation auto-promotion defaults."""
    return create_graph_domain_pack().relation_autopromotion_defaults
