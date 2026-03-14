"""
Kernel entity repository interface.

Defines the abstract contract for generic entity CRUD operations,
replacing Gene/Variant/Phenotype/etc repository interfaces.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.kernel.entities import (
        KernelEntity,
        KernelEntityAlias,
        KernelEntityIdentifier,
    )
    from src.type_definitions.common import JSONObject


class KernelEntityRepository(ABC):
    """
    Generic entity repository — replaces all entity-specific repos.

    All entities (GENE, VARIANT, PHENOTYPE, PATIENT, DRUG, etc.) are stored
    in the same ``entities`` table, differentiated by ``entity_type``.
    """

    # ── CRUD ──────────────────────────────────────────────────────────

    @abstractmethod
    def create(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        display_label: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelEntity:
        """Create a new entity in the given research space."""

    @abstractmethod
    def get_by_id(self, entity_id: str) -> KernelEntity | None:
        """Retrieve a single entity by primary key."""

    @abstractmethod
    def update(
        self,
        entity_id: str,
        *,
        display_label: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelEntity | None:
        """
        Update an entity's display label and/or metadata.

        Args:
            entity_id: Entity primary key.
            display_label: New display label (None means no change).
            metadata: Metadata patch to merge into existing metadata (None means no change).

        Returns:
            Updated entity, or None if the entity does not exist.
        """

    @abstractmethod
    def find_by_type(
        self,
        research_space_id: str,
        entity_type: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelEntity]:
        """List entities of a specific type within a research space."""

    @abstractmethod
    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        entity_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelEntity]:
        """List entities within a research space, optionally filtered by entity type."""

    @abstractmethod
    def search(
        self,
        research_space_id: str,
        query: str,
        *,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[KernelEntity]:
        """Search canonical labels and aliases within a research space."""

    @abstractmethod
    def count_by_type(self, research_space_id: str) -> dict[str, int]:
        """Return ``{entity_type: count}`` for all types in a research space."""

    @abstractmethod
    def count_global_by_type(self) -> dict[str, int]:
        """Return ``{entity_type: count}`` across all research spaces."""

    @abstractmethod
    def delete(self, entity_id: str) -> bool:
        """Delete an entity and cascade to identifiers/observations/relations."""

    # ── Identifiers ───────────────────────────────────────────────────

    @abstractmethod
    def add_identifier(
        self,
        *,
        entity_id: str,
        namespace: str,
        identifier_value: str,
        sensitivity: str = "INTERNAL",
    ) -> KernelEntityIdentifier:
        """Attach an external identifier (HGNC, DOI, MRN, etc.) to an entity."""

    @abstractmethod
    def find_by_identifier(
        self,
        *,
        namespace: str,
        identifier_value: str,
        research_space_id: str | None = None,
    ) -> KernelEntity | None:
        """Look up one entity by a specific namespace + value pair."""

    @abstractmethod
    def find_identifier_candidates(
        self,
        *,
        namespace: str,
        identifier_value: str,
        research_space_id: str | None = None,
        entity_type: str | None = None,
    ) -> list[KernelEntity]:
        """Return all exact identifier matches within the optional scope."""

    @abstractmethod
    def find_by_display_label(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        display_label: str,
    ) -> KernelEntity | None:
        """Look up one entity by exact normalized canonical display label."""

    @abstractmethod
    def find_display_label_candidates(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        display_label: str,
    ) -> list[KernelEntity]:
        """Return all exact canonical-label matches within one space + type."""

    @abstractmethod
    def add_alias(
        self,
        *,
        entity_id: str,
        alias_label: str,
        source: str | None = None,
        review_status: str = "ACTIVE",
    ) -> KernelEntityAlias:
        """Attach one normalized alias to an entity."""

    @abstractmethod
    def list_aliases(
        self,
        *,
        entity_id: str,
        include_inactive: bool = False,
    ) -> list[KernelEntityAlias]:
        """List aliases attached to one entity."""

    @abstractmethod
    def find_by_alias(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        alias_label: str,
    ) -> KernelEntity | None:
        """Look up one entity by exact normalized active alias."""

    @abstractmethod
    def find_alias_candidates(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        alias_label: str,
    ) -> list[KernelEntity]:
        """Return all exact active-alias matches within one space + type."""

    # ── Resolution ────────────────────────────────────────────────────

    @abstractmethod
    def resolve_candidates(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        identifiers: dict[str, str],
    ) -> list[KernelEntity]:
        """
        Return the deduplicated exact-match candidate set across all anchors.

        Implementations must not silently pick the first anchor match. The
        application layer decides whether multiple exact candidates are
        acceptable or should fail with a conflict.
        """

    @abstractmethod
    def resolve(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        identifiers: dict[str, str],
    ) -> KernelEntity | None:
        """
        Attempt to find an existing entity matching the given identifiers.

        Uses the entity resolution policy for ``entity_type`` to determine
        the matching strategy (STRICT_MATCH, LOOKUP, FUZZY, NONE). When more
        than one exact candidate exists across the provided anchors, the
        implementation should raise a conflict instead of silently choosing one.

        Returns the matched entity or ``None`` if no match is found.
        """


__all__ = ["KernelEntityRepository"]
