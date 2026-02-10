"""
Kernel entity repository interface.

Defines the abstract contract for generic entity CRUD operations,
replacing Gene/Variant/Phenotype/etc repository interfaces.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.database.kernel.entities import EntityIdentifierModel, EntityModel


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
        study_id: str,
        entity_type: str,
        display_label: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> EntityModel:
        """Create a new entity in the given study."""

    @abstractmethod
    def get_by_id(self, entity_id: str) -> EntityModel | None:
        """Retrieve a single entity by primary key."""

    @abstractmethod
    def find_by_type(
        self,
        study_id: str,
        entity_type: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[EntityModel]:
        """List entities of a specific type within a study."""

    @abstractmethod
    def search(
        self,
        study_id: str,
        query: str,
        *,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[EntityModel]:
        """Full-text search on display_label within a study."""

    @abstractmethod
    def count_by_type(self, study_id: str) -> dict[str, int]:
        """Return ``{entity_type: count}`` for all types in a study."""

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
    ) -> EntityIdentifierModel:
        """Attach an external identifier (HGNC, DOI, MRN, etc.) to an entity."""

    @abstractmethod
    def find_by_identifier(
        self,
        *,
        namespace: str,
        identifier_value: str,
        study_id: str | None = None,
    ) -> EntityModel | None:
        """Look up an entity by a specific namespace + value pair."""

    # ── Resolution ────────────────────────────────────────────────────

    @abstractmethod
    def resolve(
        self,
        *,
        study_id: str,
        entity_type: str,
        identifiers: dict[str, str],
    ) -> EntityModel | None:
        """
        Attempt to find an existing entity matching the given identifiers.

        Uses the entity resolution policy for ``entity_type`` to determine
        the matching strategy (STRICT_MATCH, LOOKUP, FUZZY, NONE).

        Returns the matched entity or ``None`` if no match is found.
        """


__all__ = ["KernelEntityRepository"]
