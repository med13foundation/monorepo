"""Relation persistence helpers for extraction orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.agents.contracts.extraction import ExtractionContract
    from src.domain.entities.source_document import SourceDocument
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
    from src.domain.repositories.kernel.relation_repository import (
        KernelRelationRepository,
    )
    from src.type_definitions.common import JSONObject


class _ExtractionRelationPersistenceHelpers:
    """Shared relation-persistence helpers for extraction service."""

    _relations: KernelRelationRepository | None
    _entities: KernelEntityRepository | None

    def _persist_extracted_relations(
        self,
        *,
        research_space_id: str,
        document: SourceDocument,
        contract: ExtractionContract,
        publication_entity_ids: tuple[str, ...],
        run_id: str | None,
    ) -> tuple[int, tuple[str, ...]]:
        if not contract.relations:
            return 0, ()
        if self._relations is None or self._entities is None:
            return 0, ("relation_persistence_unavailable",)

        publication_entity_id = (
            publication_entity_ids[0] if publication_entity_ids else None
        )
        persisted_count = 0
        errors: list[str] = []

        for relation in contract.relations:
            source_entity_id = self._resolve_relation_endpoint_entity_id(
                research_space_id=research_space_id,
                entity_type=relation.source_type,
                label=relation.source_label,
                publication_entity_id=publication_entity_id,
                endpoint_name="source",
            )
            target_entity_id = self._resolve_relation_endpoint_entity_id(
                research_space_id=research_space_id,
                entity_type=relation.target_type,
                label=relation.target_label,
                publication_entity_id=publication_entity_id,
                endpoint_name="target",
            )

            if source_entity_id is None or target_entity_id is None:
                errors.append(
                    (
                        "relation_persistence_skipped:"
                        f"{relation.source_type}:{relation.relation_type}:"
                        f"{relation.target_type}"
                    ),
                )
                continue

            if source_entity_id == target_entity_id:
                errors.append(
                    (
                        "relation_persistence_skipped_self_loop:"
                        f"{relation.relation_type}:{source_entity_id}"
                    ),
                )
                continue

            relation_type = relation.relation_type.strip().upper()
            if not relation_type:
                errors.append("relation_persistence_skipped_empty_relation_type")
                continue

            try:
                self._relations.create(
                    research_space_id=research_space_id,
                    source_id=source_entity_id,
                    relation_type=relation_type,
                    target_id=target_entity_id,
                    confidence=relation.confidence,
                    evidence_summary=(f"Extracted from source_document:{document.id}"),
                    evidence_tier="COMPUTATIONAL",
                    source_document_id=str(document.id),
                    agent_run_id=run_id,
                )
                persisted_count += 1
            except (TypeError, ValueError) as exc:
                errors.append(
                    (
                        "relation_persistence_failed:"
                        f"{relation_type}:{source_entity_id}->{target_entity_id}:"
                        f"{exc!s}"
                    ),
                )

        return persisted_count, tuple(errors)

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
        candidates = self._entities.search(
            research_space_id,
            normalized_label,
            entity_type=normalized_type,
            limit=5,
        )
        normalized_label_lower = normalized_label.lower()
        for candidate in candidates:
            candidate_label = candidate.display_label
            if (
                isinstance(candidate_label, str)
                and candidate_label.strip().lower() == normalized_label_lower
            ):
                return str(candidate.id)
        if candidates:
            return str(candidates[0].id)

        metadata: JSONObject = {
            "created_from": "extraction_relation_endpoint",
            "endpoint": endpoint_name,
        }
        created = self._entities.create(
            research_space_id=research_space_id,
            entity_type=normalized_type,
            display_label=normalized_label,
            metadata=metadata,
        )
        return str(created.id)


__all__ = ["_ExtractionRelationPersistenceHelpers"]
