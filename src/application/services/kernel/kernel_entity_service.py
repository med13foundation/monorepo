"""
Kernel entity application service.

Orchestrates entity creation with resolution-policy enforcement,
identifier management, and research-space-scoped search.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.application.services.kernel.kernel_entity_errors import (
    KernelEntityConflictError,
    KernelEntityValidationError,
)
from src.domain.value_objects.entity_resolution import normalize_entity_alias_labels

if TYPE_CHECKING:
    from src.domain.entities.kernel.entities import (
        KernelEntity,
        KernelEntityIdentifier,
    )
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

    def create_or_resolve(  # noqa: C901, PLR0912, PLR0913
        self,
        *,
        research_space_id: str,
        entity_type: str,
        identifiers: dict[str, str] | None = None,
        display_label: str | None = None,
        aliases: list[str] | None = None,
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

        normalized_aliases = normalize_entity_alias_labels(
            alias
            for alias in [display_label or "", *(aliases or [])]
            if isinstance(alias, str)
        )
        strategy = (
            policy.policy_strategy.strip().upper()
            if isinstance(policy.policy_strategy, str)
            else "STRICT_MATCH"
        )
        required_anchors: list[str] = (
            policy.required_anchors if isinstance(policy.required_anchors, list) else []
        )
        provided_identifiers = identifiers or {}
        missing_required_anchors = [
            anchor
            for anchor in required_anchors
            if anchor not in provided_identifiers or not provided_identifiers[anchor]
        ]

        if strategy == "STRICT_MATCH" and missing_required_anchors:
            msg = f"Missing required anchors for {entity_type}: " + ", ".join(
                sorted(missing_required_anchors),
            )
            raise KernelEntityValidationError(msg)

        if strategy != "NONE" and provided_identifiers and not missing_required_anchors:
            existing = self._resolve_exact_candidates(
                candidates=self._entities.resolve_candidates(
                    research_space_id=research_space_id,
                    entity_type=entity_type,
                    identifiers=provided_identifiers,
                ),
                match_description="identifier anchors",
            )
            if existing is not None:
                logger.info(
                    "Resolved %s to existing entity %s via identifiers",
                    entity_type,
                    existing.id,
                )
                return existing, False

        if strategy in {"LOOKUP", "FUZZY"}:
            if display_label is not None and display_label.strip():
                existing_by_label = self._resolve_exact_candidates(
                    candidates=self._entities.find_display_label_candidates(
                        research_space_id=research_space_id,
                        entity_type=entity_type,
                        display_label=display_label,
                    ),
                    match_description=f"display label '{display_label}'",
                )
                if existing_by_label is not None:
                    logger.info(
                        "Resolved %s to existing entity %s via display label",
                        entity_type,
                        existing_by_label.id,
                    )
                    return existing_by_label, False

            existing_by_alias = self._resolve_exact_candidates(
                candidates=self._collect_alias_candidates(
                    research_space_id=research_space_id,
                    entity_type=entity_type,
                    alias_labels=normalized_aliases,
                ),
                match_description="alias anchors",
            )
            if existing_by_alias is not None:
                logger.info(
                    "Resolved %s to existing entity %s via aliases",
                    entity_type,
                    existing_by_alias.id,
                )
                return existing_by_alias, False

        # 2. Create new entity
        entity = self._entities.create(
            research_space_id=research_space_id,
            entity_type=entity_type,
            display_label=display_label,
            metadata=metadata,
        )

        # 3. Attach identifiers
        if provided_identifiers:
            for namespace, value in provided_identifiers.items():
                self._entities.add_identifier(
                    entity_id=str(entity.id),
                    namespace=namespace,
                    identifier_value=value,
                )

        for alias_label in normalized_aliases:
            self._entities.add_alias(
                entity_id=str(entity.id),
                alias_label=alias_label,
                source="entity_write",
            )

        persisted_entity = self._entities.get_by_id(str(entity.id))
        if persisted_entity is None:
            msg = f"Created entity '{entity.id}' could not be reloaded."
            raise RuntimeError(msg)

        logger.info("Created new %s entity %s", entity_type, entity.id)
        return persisted_entity, True

    def _collect_alias_candidates(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        alias_labels: list[str],
    ) -> list[KernelEntity]:
        candidate_by_id: dict[str, KernelEntity] = {}
        for alias_label in alias_labels:
            for candidate in self._entities.find_alias_candidates(
                research_space_id=research_space_id,
                entity_type=entity_type,
                alias_label=alias_label,
            ):
                candidate_by_id[str(candidate.id)] = candidate
        return list(candidate_by_id.values())

    @staticmethod
    def _resolve_exact_candidates(
        *,
        candidates: list[KernelEntity],
        match_description: str,
    ) -> KernelEntity | None:
        candidate_by_id: dict[str, KernelEntity] = {}
        for candidate in candidates:
            candidate_by_id[str(candidate.id)] = candidate
        unique_candidates = list(candidate_by_id.values())
        if not unique_candidates:
            return None
        if len(unique_candidates) > 1:
            msg = f"Ambiguous exact match for {match_description}."
            raise KernelEntityConflictError(msg)
        return unique_candidates[0]

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
        aliases: list[str] | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelEntity | None:
        """Update an entity's display label and/or metadata."""
        updated = self._entities.update(
            entity_id,
            display_label=display_label,
            metadata=metadata,
        )
        if updated is None:
            return None
        normalized_aliases = normalize_entity_alias_labels(
            alias
            for alias in [display_label or "", *(aliases or [])]
            if isinstance(alias, str)
        )
        for alias_label in normalized_aliases:
            self._entities.add_alias(
                entity_id=entity_id,
                alias_label=alias_label,
                source="entity_write",
            )
        return self._entities.get_by_id(entity_id)

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
        """Search canonical entity labels and aliases."""
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
