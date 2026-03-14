"""Domain-neutral graph view configuration types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

GraphDomainViewType = str


class GraphViewExtension(Protocol):
    """Extension contract for pack-owned graph view semantics."""

    @property
    def entity_view_types(self) -> dict[GraphDomainViewType, str]:
        """Return the pack-owned entity view type mapping."""

    @property
    def document_view_types(self) -> frozenset[GraphDomainViewType]:
        """Return the pack-owned document view types."""

    @property
    def claim_view_types(self) -> frozenset[GraphDomainViewType]:
        """Return the pack-owned claim view types."""

    @property
    def mechanism_relation_types(self) -> frozenset[str]:
        """Return relation types used for mechanism-oriented graph views."""

    @property
    def supported_view_types(self) -> frozenset[GraphDomainViewType]:
        """Return all supported view types for the extension."""

    def normalize_view_type(self, value: str) -> GraphDomainViewType:
        """Normalize one raw route value into a supported graph view type."""

    def is_entity_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets an entity resource."""

    def is_claim_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets a claim resource."""

    def is_document_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets a document resource."""


@dataclass(frozen=True)
class GraphViewConfig:
    """Configurable graph view semantics supplied by a domain pack."""

    entity_view_types: dict[GraphDomainViewType, str]
    document_view_types: frozenset[GraphDomainViewType]
    claim_view_types: frozenset[GraphDomainViewType]
    mechanism_relation_types: frozenset[str]

    @property
    def supported_view_types(self) -> frozenset[GraphDomainViewType]:
        """Return all supported view types for the configured domain pack."""
        return (
            frozenset(self.entity_view_types)
            | self.document_view_types
            | self.claim_view_types
        )

    def normalize_view_type(self, value: str) -> GraphDomainViewType:
        """Normalize one raw route value into a supported graph view type."""
        normalized = value.strip().lower()
        if normalized in self.supported_view_types:
            return normalized
        msg = f"Unsupported graph view type '{value}'"
        raise ValueError(msg)

    def is_entity_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets an entity resource."""
        return view_type in self.entity_view_types

    def is_claim_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets a claim resource."""
        return view_type in self.claim_view_types

    def is_document_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets a document resource."""
        return view_type in self.document_view_types
