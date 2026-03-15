"""Alias mixin for the SQLAlchemy kernel entity repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from src.application.services.kernel.kernel_entity_errors import (
    KernelEntityConflictError,
    KernelEntityValidationError,
)
from src.domain.value_objects.entity_resolution import (
    canonicalize_entity_match_text,
    normalize_entity_match_text,
)
from src.infrastructure.repositories.kernel.kernel_entity_repository_support import (
    KernelEntityRepositoryMixinBase,
    _as_uuid,
)
from src.models.database.kernel.entities import EntityAliasModel, EntityModel

if TYPE_CHECKING:
    from src.domain.entities.kernel.entities import KernelEntity, KernelEntityAlias


class KernelEntityAliasMixin(KernelEntityRepositoryMixinBase):
    """Alias management operations for kernel entities."""

    def add_alias(
        self,
        *,
        entity_id: str,
        alias_label: str,
        source: str | None = None,
        review_status: str = "ACTIVE",
    ) -> KernelEntityAlias:
        entity_model = self._session.get(EntityModel, _as_uuid(entity_id))
        if entity_model is None:
            msg = f"Entity '{entity_id}' does not exist."
            raise KernelEntityValidationError(msg)

        canonical_alias = canonicalize_entity_match_text(alias_label)
        if not canonical_alias:
            msg = "alias_label is required"
            raise KernelEntityValidationError(msg)
        normalized_alias = normalize_entity_match_text(canonical_alias)
        existing_models = self._session.scalars(
            select(EntityAliasModel).where(
                EntityAliasModel.research_space_id == entity_model.research_space_id,
                EntityAliasModel.entity_type == entity_model.entity_type,
                EntityAliasModel.alias_normalized == normalized_alias,
                EntityAliasModel.is_active.is_(True),
            ),
        ).all()
        for existing_model in existing_models:
            if existing_model.entity_id == entity_model.id:
                return self._to_domain_alias(existing_model)
            msg = (
                f"Alias '{canonical_alias}' is already assigned to another "
                "entity in this research space."
            )
            raise KernelEntityConflictError(msg)

        same_entity_alias = self._session.scalars(
            select(EntityAliasModel).where(
                EntityAliasModel.entity_id == entity_model.id,
                EntityAliasModel.alias_normalized == normalized_alias,
            ),
        ).first()
        if same_entity_alias is not None:
            return self._to_domain_alias(same_entity_alias)

        alias_model = EntityAliasModel(
            entity_id=entity_model.id,
            research_space_id=entity_model.research_space_id,
            entity_type=entity_model.entity_type,
            alias_label=canonical_alias,
            alias_normalized=normalized_alias,
            source=source,
            created_by="system:kernel_entity_repository",
            review_status=review_status,
        )
        self._session.add(alias_model)
        self._session.flush()
        return self._to_domain_alias(alias_model)

    def list_aliases(
        self,
        *,
        entity_id: str,
        include_inactive: bool = False,
    ) -> list[KernelEntityAlias]:
        stmt = select(EntityAliasModel).where(
            EntityAliasModel.entity_id == _as_uuid(entity_id),
        )
        if not include_inactive:
            stmt = stmt.where(EntityAliasModel.is_active.is_(True))
        stmt = stmt.order_by(
            EntityAliasModel.created_at.asc(),
            EntityAliasModel.id.asc(),
        )
        return [self._to_domain_alias(model) for model in self._session.scalars(stmt)]

    def find_by_alias(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        alias_label: str,
    ) -> KernelEntity | None:
        candidates = self.find_alias_candidates(
            research_space_id=research_space_id,
            entity_type=entity_type,
            alias_label=alias_label,
        )
        return self._resolve_single_candidate(
            candidates,
            match_description=f"alias '{alias_label}'",
        )

    def find_alias_candidates(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        alias_label: str,
    ) -> list[KernelEntity]:
        normalized_alias = normalize_entity_match_text(alias_label)
        if not normalized_alias:
            return []
        models = self._session.scalars(
            select(EntityModel)
            .join(EntityAliasModel, EntityAliasModel.entity_id == EntityModel.id)
            .where(
                EntityAliasModel.research_space_id == _as_uuid(research_space_id),
                EntityAliasModel.entity_type == entity_type,
                EntityAliasModel.alias_normalized == normalized_alias,
                EntityAliasModel.is_active.is_(True),
            ),
        ).all()
        return self._to_domain_entities(self._dedupe_entity_models(models))
