"""
Kernel entity application service.

Orchestrates entity creation with resolution-policy enforcement,
identifier management, and research-space-scoped search.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.kernel.entities import KernelEntity, KernelEntityIdentifier
    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )
    from src.domain.repositories.kernel.entity_repository import (
        KernelEntityRepository,
    )
    from src.type_definitions.common import JSONObject

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
        research_space_id: str,
        entity_type: str,
        identifiers: dict[str, str] | None = None,
        display_label: str | None = None,
        metadata: JSONObject | None = None,
    ) -> tuple[KernelEntity, bool]:
        """
        Create an entity or return existing match.

        Uses the entity resolution policy to determine dedup strategy.
        Returns (entity, created) — ``created`` is False if resolved to existing.
        """
        # 1. Enforce dictionary-defined entity types.
        policy = self._dictionary.get_resolution_policy(entity_type)
        if policy is None:
            msg = (
                f"Unknown entity_type '{entity_type}'. "
                "Add an entity resolution policy before creating this type."
            )
            raise ValueError(msg)

        if policy and identifiers and policy.policy_strategy != "NONE":
            required_anchors: list[str] = (
                policy.required_anchors
                if isinstance(policy.required_anchors, list)
                else []
            )
            missing = [
                anchor
                for anchor in required_anchors
                if anchor not in identifiers or not identifiers[anchor]
            ]
            if missing:
                logger.info(
                    "Missing required anchors %s for %s; creating new entity.",
                    missing,
                    entity_type,
                )
            else:
                existing = self._entities.resolve(
                    research_space_id=research_space_id,
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
            research_space_id=research_space_id,
            entity_type=entity_type,
            display_label=display_label,
            metadata=metadata,
        )

        # 3. Attach identifiers
        if identifiers:
            for namespace, value in identifiers.items():
                self._entities.add_identifier(
                    entity_id=str(entity.id),
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
    ) -> KernelEntityIdentifier:
        """Add an external identifier to an entity."""
        return self._entities.add_identifier(
            entity_id=entity_id,
            namespace=namespace,
            identifier_value=identifier_value,
            sensitivity=sensitivity,
        )

    # ── Read operations ───────────────────────────────────────────────

    def get_entity(self, entity_id: str) -> KernelEntity | None:
        """Retrieve a single entity."""
        return self._entities.get_by_id(entity_id)

    def update_entity(
        self,
        entity_id: str,
        *,
        display_label: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelEntity | None:
        """Update an entity's display label and/or metadata."""
        return self._entities.update(
            entity_id,
            display_label=display_label,
            metadata=metadata,
        )

    def list_by_type(
        self,
        research_space_id: str,
        entity_type: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelEntity]:
        """List entities of a specific type in a research space."""
        return self._entities.find_by_type(
            research_space_id,
            entity_type,
            limit=limit,
            offset=offset,
        )

    def search(
        self,
        research_space_id: str,
        query: str,
        *,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[KernelEntity]:
        """Full-text search on entity display labels."""
        return self._entities.search(
            research_space_id,
            query,
            entity_type=entity_type,
            limit=limit,
        )

    def get_research_space_summary(self, research_space_id: str) -> dict[str, int]:
        """Return entity counts by type for a research space."""
        return self._entities.count_by_type(research_space_id)

    # ── Delete ────────────────────────────────────────────────────────

    def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity and all cascaded data."""
        return self._entities.delete(entity_id)


__all__ = ["KernelEntityService"]
