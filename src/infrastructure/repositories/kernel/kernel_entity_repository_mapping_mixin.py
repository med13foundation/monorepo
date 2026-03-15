"""Domain mapping mixin for the SQLAlchemy kernel entity repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from src.application.services.kernel.kernel_entity_errors import (
    KernelEntityConflictError,
)
from src.domain.entities.kernel.entities import (
    KernelEntity,
    KernelEntityAlias,
    KernelEntityIdentifier,
)
from src.infrastructure.repositories.kernel.kernel_entity_repository_support import (
    KernelEntityRepositoryMixinBase,
    logger,
)
from src.models.database.kernel.entities import (
    EntityAliasModel,
    EntityIdentifierModel,
    EntityModel,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID


class KernelEntityRepositoryMappingMixin(KernelEntityRepositoryMixinBase):
    """Mapping and deduplication helpers for kernel entities."""

    def _resolve_single_candidate(
        self,
        candidates: Sequence[KernelEntity],
        *,
        match_description: str,
    ) -> KernelEntity | None:
        if not candidates:
            return None
        unique_candidates = self._dedupe_domain_entities(candidates)
        if len(unique_candidates) > 1:
            msg = f"Ambiguous exact match for {match_description}."
            raise KernelEntityConflictError(msg)
        return unique_candidates[0]

    @staticmethod
    def _dedupe_entity_models(models: Sequence[EntityModel]) -> list[EntityModel]:
        deduped: list[EntityModel] = []
        seen: set[UUID] = set()
        for model in models:
            if model.id in seen:
                continue
            seen.add(model.id)
            deduped.append(model)
        return deduped

    @staticmethod
    def _dedupe_entity_ids(entity_ids: Sequence[UUID]) -> list[UUID]:
        deduped: list[UUID] = []
        seen: set[UUID] = set()
        for entity_id in entity_ids:
            if entity_id in seen:
                continue
            seen.add(entity_id)
            deduped.append(entity_id)
        return deduped

    @staticmethod
    def _dedupe_domain_entities(
        entities: Sequence[KernelEntity],
    ) -> list[KernelEntity]:
        deduped: list[KernelEntity] = []
        seen: set[UUID] = set()
        for entity in entities:
            if entity.id in seen:
                continue
            seen.add(entity.id)
            deduped.append(entity)
        return deduped

    def _alias_map_for_entity_ids(
        self,
        entity_ids: Sequence[UUID],
    ) -> dict[UUID, list[str]]:
        if not entity_ids:
            return {}
        rows = self._session.execute(
            select(EntityAliasModel.entity_id, EntityAliasModel.alias_label)
            .where(
                EntityAliasModel.entity_id.in_(entity_ids),
                EntityAliasModel.is_active.is_(True),
            )
            .order_by(EntityAliasModel.created_at.asc(), EntityAliasModel.id.asc()),
        ).all()
        alias_map: dict[UUID, list[str]] = {entity_id: [] for entity_id in entity_ids}
        for entity_id, alias_label in rows:
            labels = alias_map.setdefault(entity_id, [])
            if alias_label in labels:
                continue
            labels.append(alias_label)
        return alias_map

    def _to_domain_entity(self, model: EntityModel) -> KernelEntity:
        alias_map = self._alias_map_for_entity_ids([model.id])
        return KernelEntity.model_validate(
            {
                "id": model.id,
                "research_space_id": model.research_space_id,
                "entity_type": model.entity_type,
                "display_label": model.display_label,
                "aliases": alias_map.get(model.id, []),
                "metadata_payload": model.metadata_payload or {},
                "created_at": model.created_at,
                "updated_at": model.updated_at,
            },
        )

    def _to_domain_entities(self, models: Sequence[EntityModel]) -> list[KernelEntity]:
        entity_ids = [model.id for model in models]
        alias_map = self._alias_map_for_entity_ids(entity_ids)
        return [
            KernelEntity.model_validate(
                {
                    "id": model.id,
                    "research_space_id": model.research_space_id,
                    "entity_type": model.entity_type,
                    "display_label": model.display_label,
                    "aliases": alias_map.get(model.id, []),
                    "metadata_payload": model.metadata_payload or {},
                    "created_at": model.created_at,
                    "updated_at": model.updated_at,
                },
            )
            for model in models
        ]

    @staticmethod
    def _to_domain_alias(model: EntityAliasModel) -> KernelEntityAlias:
        return KernelEntityAlias.model_validate(model)

    def _to_domain_identifier(
        self,
        model: EntityIdentifierModel,
    ) -> KernelEntityIdentifier:
        identifier_value = model.identifier_value
        if (
            model.sensitivity == "PHI"
            and model.identifier_blind_index
            and self._phi_encryption_enabled
            and self._phi_encryption_service is not None
            and self._phi_encryption_service.is_encrypted_identifier(identifier_value)
        ):
            try:
                identifier_value = self._phi_encryption_service.decrypt(
                    identifier_value,
                )
            except ValueError:
                logger.warning(
                    "Failed to decrypt PHI identifier %s/%s; returning stored payload",
                    model.namespace,
                    model.id,
                )

        return KernelEntityIdentifier.model_validate(
            {
                "id": model.id,
                "entity_id": model.entity_id,
                "namespace": model.namespace,
                "identifier_value": identifier_value,
                "identifier_blind_index": model.identifier_blind_index,
                "encryption_key_version": model.encryption_key_version,
                "blind_index_version": model.blind_index_version,
                "sensitivity": model.sensitivity,
                "created_at": model.created_at,
                "updated_at": model.updated_at,
            },
        )
