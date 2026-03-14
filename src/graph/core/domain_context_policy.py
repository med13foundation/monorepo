"""Contracts for pack-owned graph domain-context policies."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceTypeDomainContextDefault:
    """Default domain context for one source type."""

    source_type: str
    domain_context: str


@dataclass(frozen=True)
class GraphDomainContextPolicy:
    """Pack-owned policy for resolving source-type domain defaults."""

    source_type_defaults: tuple[SourceTypeDomainContextDefault, ...]
