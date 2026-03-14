"""Pack-aware graph domain-context resolution helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.services.domain_context_resolver import DomainContextResolver

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from src.graph.core.domain_context_policy import GraphDomainContextPolicy


def default_graph_domain_context_for_source_type(
    source_type: str | None,
    *,
    domain_context_policy: GraphDomainContextPolicy,
    fallback: str | None = DomainContextResolver.GENERAL_DEFAULT_DOMAIN,
) -> str | None:
    """Return the provided-pack default domain context for one source type."""
    normalized_source_type = DomainContextResolver.normalize(source_type)
    if normalized_source_type is not None:
        for definition in domain_context_policy.source_type_defaults:
            if definition.source_type == normalized_source_type:
                return definition.domain_context
    return DomainContextResolver.normalize(fallback)


def resolve_graph_domain_context(  # noqa: PLR0913
    *,
    domain_context_policy: GraphDomainContextPolicy,
    explicit_domain_context: str | None = None,
    metadata: Mapping[str, object] | None = None,
    source_type: str | None = None,
    ai_inference: Callable[[], str | None] | None = None,
    fallback: str | None = None,
) -> str | None:
    """Resolve graph domain context using the provided-pack source defaults."""
    explicit = DomainContextResolver.normalize(explicit_domain_context)
    if explicit is not None:
        return explicit

    from_metadata = DomainContextResolver.from_metadata(metadata)
    if from_metadata is not None:
        return from_metadata

    from_source_type = default_graph_domain_context_for_source_type(
        source_type,
        domain_context_policy=domain_context_policy,
        fallback=None,
    )
    if from_source_type is not None:
        return from_source_type

    if ai_inference is not None:
        ai_inferred = DomainContextResolver.normalize(ai_inference())
        if ai_inferred is not None:
            return ai_inferred

    return DomainContextResolver.normalize(fallback)
