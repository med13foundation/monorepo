"""Endpoint entity-resolution helpers for extraction relation persistence."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.application.agents.services._relation_endpoint_label_resolution_helpers import (
    build_concept_family_key,
    build_entity_concept_key,
    build_label_variants,
    select_best_candidate,
)
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.domain.entities.kernel.entities import KernelEntity
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)
_ENDPOINT_ENTITY_TYPE_CREATED_BY = "agent:extraction_endpoint_entity_bootstrap"


class _RelationEndpointEntityResolutionHelpers:
    """Shared endpoint resolution and concept-identifier helpers."""

    _entities: KernelEntityRepository | None
    _dictionary: DictionaryPort | None

    def _resolve_relation_endpoint_entity_id(  # noqa: PLR0911
        self,
        *,
        research_space_id: str,
        entity_type: str,
        label: str | None,
        publication_entity_id: str | None,
        endpoint_name: str,
    ) -> str | None:
        normalized_type = entity_type.strip().upper()
        if not normalized_type:
            return None

        if normalized_type == "PUBLICATION" and publication_entity_id is not None:
            return publication_entity_id

        normalized_label = label.strip() if isinstance(label, str) else ""
        if not normalized_label:
            return None

        if self._entities is None:
            return None

        concept_match = self._resolve_existing_entity_by_concept_key(
            research_space_id=research_space_id,
            entity_type=normalized_type,
            normalized_label=normalized_label,
        )
        if concept_match is not None:
            return concept_match

        label_search_match = self._resolve_existing_entity_by_label_search(
            research_space_id=research_space_id,
            entity_type=normalized_type,
            normalized_label=normalized_label,
        )
        if label_search_match is not None:
            return label_search_match

        return self._create_relation_endpoint_entity(
            research_space_id=research_space_id,
            entity_type=normalized_type,
            normalized_label=normalized_label,
            endpoint_name=endpoint_name,
        )

    def _resolve_existing_entity_by_concept_key(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        normalized_label: str,
    ) -> str | None:
        if self._entities is None:
            return None
        concept_key = build_entity_concept_key(entity_type, normalized_label)
        if concept_key is None:
            return None
        concept_entity = self._entities.find_by_identifier(
            namespace="CONCEPT_KEY",
            identifier_value=concept_key,
            research_space_id=research_space_id,
        )
        if concept_entity is None:
            return None
        if concept_entity.entity_type.strip().upper() != entity_type:
            return None
        concept_entity_id = str(concept_entity.id)
        self._ensure_concept_identifiers(
            entity_id=concept_entity_id,
            entity_type=entity_type,
            label=(
                concept_entity.display_label
                if isinstance(concept_entity.display_label, str)
                else normalized_label
            ),
        )
        return concept_entity_id

    def _resolve_existing_entity_by_label_search(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        normalized_label: str,
    ) -> str | None:
        if self._entities is None:
            return None
        label_variants = build_label_variants(normalized_label)
        candidate_by_id: dict[str, KernelEntity] = {}
        for query_variant in label_variants:
            for candidate in self._entities.search(
                research_space_id,
                query_variant,
                entity_type=entity_type,
                limit=10,
            ):
                candidate_by_id[str(candidate.id)] = candidate
        candidates = tuple(candidate_by_id.values())
        resolved = select_best_candidate(
            query_label=normalized_label,
            candidates=candidates,
        )
        if resolved is not None:
            resolved_id = str(resolved.id)
            self._ensure_concept_identifiers(
                entity_id=resolved_id,
                entity_type=entity_type,
                label=(
                    resolved.display_label
                    if isinstance(resolved.display_label, str)
                    else normalized_label
                ),
            )
            return resolved_id
        if not candidates:
            return None
        fallback_entity = candidates[0]
        fallback_id = str(fallback_entity.id)
        self._ensure_concept_identifiers(
            entity_id=fallback_id,
            entity_type=entity_type,
            label=(
                fallback_entity.display_label
                if isinstance(fallback_entity.display_label, str)
                else normalized_label
            ),
        )
        return fallback_id

    def _create_relation_endpoint_entity(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        normalized_label: str,
        endpoint_name: str,
    ) -> str | None:
        if self._entities is None:
            return None
        if not self._ensure_active_endpoint_entity_type(
            entity_type=entity_type,
            endpoint_name=endpoint_name,
        ):
            return None

        metadata: JSONObject = {
            "created_from": "extraction_relation_endpoint",
            "endpoint": endpoint_name,
        }
        try:
            created = self._entities.create(
                research_space_id=research_space_id,
                entity_type=entity_type,
                display_label=normalized_label,
                metadata={
                    str(key): to_json_value(value) for key, value in metadata.items()
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to create extraction endpoint entity type=%s label=%s: %s",
                entity_type,
                normalized_label,
                exc,
            )
            return None
        created_id = str(created.id)
        self._ensure_concept_identifiers(
            entity_id=created_id,
            entity_type=entity_type,
            label=normalized_label,
        )
        return created_id

    def _ensure_active_endpoint_entity_type(
        self,
        *,
        entity_type: str,
        endpoint_name: str,
    ) -> bool:
        dictionary = self._dictionary
        if dictionary is None:
            return False

        existing = dictionary.get_entity_type(
            entity_type,
            include_inactive=True,
        )
        if existing is not None:
            if existing.is_active and existing.review_status == "ACTIVE":
                return True
            try:
                dictionary.set_entity_type_review_status(
                    entity_type,
                    review_status="ACTIVE",
                    reviewed_by=_ENDPOINT_ENTITY_TYPE_CREATED_BY,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to activate endpoint entity type=%s: %s",
                    entity_type,
                    exc,
                )
                return False
            else:
                return True

        try:
            dictionary.create_entity_type(
                entity_type=entity_type,
                display_name=entity_type.replace("_", " ").title(),
                description=(
                    "Auto-created entity type for extraction relation endpoint "
                    "persistence."
                ),
                domain_context="general",
                created_by=_ENDPOINT_ENTITY_TYPE_CREATED_BY,
                source_ref=f"extraction_relation_endpoint:{endpoint_name}",
                research_space_settings={"dictionary_agent_creation_policy": "ACTIVE"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to create endpoint entity type=%s: %s",
                entity_type,
                exc,
            )
            return False
        else:
            return True

    def _ensure_concept_identifiers(
        self,
        *,
        entity_id: str,
        entity_type: str,
        label: str,
    ) -> None:
        if self._entities is None:
            return
        concept_key = build_entity_concept_key(entity_type, label)
        if concept_key is not None:
            self._add_internal_identifier(
                entity_id=entity_id,
                namespace="CONCEPT_KEY",
                identifier_value=concept_key,
            )
        family_key = build_concept_family_key(entity_type, label)
        if family_key is not None:
            self._add_internal_identifier(
                entity_id=entity_id,
                namespace="CONCEPT_FAMILY",
                identifier_value=family_key,
            )

    def _add_internal_identifier(
        self,
        *,
        entity_id: str,
        namespace: str,
        identifier_value: str,
    ) -> None:
        if self._entities is None:
            return
        try:
            self._entities.add_identifier(
                entity_id=entity_id,
                namespace=namespace,
                identifier_value=identifier_value,
                sensitivity="INTERNAL",
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            logger.debug(
                "Failed to add %s identifier for entity_id=%s: %s",
                namespace,
                entity_id,
                exc,
            )


__all__ = ["_RelationEndpointEntityResolutionHelpers"]
