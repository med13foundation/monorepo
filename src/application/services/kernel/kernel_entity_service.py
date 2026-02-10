"""
Kernel entity application service.

Orchestrates entity creation with resolution-policy enforcement,
identifier management, and study-scoped search.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )
    from src.domain.repositories.kernel.entity_repository import (
        KernelEntityRepository,
    )
    from src.models.database.kernel.entities import (
        EntityIdentifierModel,
        EntityModel,
    )

logger = logging.getLogger(__name__)


class KernelEntityService:
    """
    Application service for kernel entities.

    Combines entity CRUD with resolution-policy enforcement.
    """

    def __init__(
        self,
        entity_repo: KernelEntityRepository,
        dictionary_repo: DictionaryRepository,
    ) -> None:
        self._entities = entity_repo
        self._dictionary = dictionary_repo

    # ── Create with resolution ────────────────────────────────────────

    def create_or_resolve(
        self,
        *,
        study_id: str,
        entity_type: str,
        identifiers: dict[str, str] | None = None,
        display_label: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> tuple[EntityModel, bool]:
        """
        Create an entity or return existing match.

        Uses the entity resolution policy to determine dedup strategy.
        Returns (entity, created) — ``created`` is False if resolved to existing.
        """
        # 1. Check resolution policy
        policy = self._dictionary.get_resolution_policy(entity_type)

        if policy and identifiers and policy.policy_strategy != "NONE":
            existing = self._entities.resolve(
                study_id=study_id,
                entity_type=entity_type,
                identifiers=identifiers,
            )
            if existing is not None:
                logger.info(
                    "Resolved %s to existing entity %s",
                    entity_type,
                    existing.id,
                )
                return existing, False

        # 2. Create new entity
        entity = self._entities.create(
            study_id=study_id,
            entity_type=entity_type,
            display_label=display_label,
            metadata=metadata,
        )

        # 3. Attach identifiers
        if identifiers:
            for namespace, value in identifiers.items():
                self._entities.add_identifier(
                    entity_id=entity.id,
                    namespace=namespace,
                    identifier_value=value,
                )

        logger.info("Created new %s entity %s", entity_type, entity.id)
        return entity, True

    # ── Identifier management ─────────────────────────────────────────

    def add_identifier(
        self,
        *,
        entity_id: str,
        namespace: str,
        identifier_value: str,
        sensitivity: str = "INTERNAL",
    ) -> EntityIdentifierModel:
        """Add an external identifier to an entity."""
        return self._entities.add_identifier(
            entity_id=entity_id,
            namespace=namespace,
            identifier_value=identifier_value,
            sensitivity=sensitivity,
        )

    # ── Read operations ───────────────────────────────────────────────

    def get_entity(self, entity_id: str) -> EntityModel | None:
        """Retrieve a single entity."""
        return self._entities.get_by_id(entity_id)

    def list_by_type(
        self,
        study_id: str,
        entity_type: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[EntityModel]:
        """List entities of a specific type in a study."""
        return self._entities.find_by_type(
            study_id,
            entity_type,
            limit=limit,
            offset=offset,
        )

    def search(
        self,
        study_id: str,
        query: str,
        *,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[EntityModel]:
        """Full-text search on entity display labels."""
        return self._entities.search(
            study_id,
            query,
            entity_type=entity_type,
            limit=limit,
        )

    def get_study_summary(self, study_id: str) -> dict[str, int]:
        """Return entity counts by type for a study."""
        return self._entities.count_by_type(study_id)

    # ── Delete ────────────────────────────────────────────────────────

    def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity and all cascaded data."""
        return self._entities.delete(entity_id)


__all__ = ["KernelEntityService"]
