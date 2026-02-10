"""
Kernel entity repository interface.

Defines the abstract contract for generic entity CRUD operations,
replacing Gene/Variant/Phenotype/etc repository interfaces.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.kernel.entities import KernelEntity, KernelEntityIdentifier
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
        """Full-text search on display_label within a research space."""

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
        """Look up an entity by a specific namespace + value pair."""

    # ── Resolution ────────────────────────────────────────────────────

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
        the matching strategy (STRICT_MATCH, LOOKUP, FUZZY, NONE).

        Returns the matched entity or ``None`` if no match is found.
        """


__all__ = ["KernelEntityRepository"]
