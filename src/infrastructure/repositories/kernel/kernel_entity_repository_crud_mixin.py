"""CRUD and search mixin for the SQLAlchemy kernel entity repository."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import and_, func, or_, select

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
    from src.domain.entities.kernel.entities import KernelEntity
    from src.type_definitions.common import JSONObject


class KernelEntityCrudMixin(KernelEntityRepositoryMixinBase):
    """CRUD and search operations for kernel entities."""

    def create(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        display_label: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelEntity:
        canonical_label, normalized_label = self._normalize_display_label(display_label)
        entity = EntityModel(
            id=uuid4(),
            research_space_id=_as_uuid(research_space_id),
            entity_type=entity_type,
            display_label=canonical_label,
            display_label_normalized=normalized_label,
            metadata_payload=metadata or {},
        )
        self._session.add(entity)
        self._session.flush()
        return self._to_domain_entity(entity)

    def get_by_id(self, entity_id: str) -> KernelEntity | None:
        model = self._session.get(EntityModel, _as_uuid(entity_id))
        return self._to_domain_entity(model) if model is not None else None

    def update(
        self,
        entity_id: str,
        *,
        display_label: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelEntity | None:
        entity_model = self._session.get(EntityModel, _as_uuid(entity_id))
        if entity_model is None:
            return None

        if display_label is not None:
            canonical_label, normalized_label = self._normalize_display_label(
                display_label,
            )
            entity_model.display_label = canonical_label
            entity_model.display_label_normalized = normalized_label

        if metadata is not None:
            merged = dict(entity_model.metadata_payload or {})
            merged.update(metadata)
            entity_model.metadata_payload = merged

        self._session.flush()
        return self._to_domain_entity(entity_model)

    def find_by_type(
        self,
        research_space_id: str,
        entity_type: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelEntity]:
        stmt = (
            select(EntityModel)
            .where(
                EntityModel.research_space_id == _as_uuid(research_space_id),
                EntityModel.entity_type == entity_type,
            )
            .order_by(EntityModel.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return self._to_domain_entities(self._session.scalars(stmt).all())

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        entity_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelEntity]:
        stmt = select(EntityModel).where(
            EntityModel.research_space_id == _as_uuid(research_space_id),
        )
        if entity_type is not None:
            stmt = stmt.where(EntityModel.entity_type == entity_type)
        stmt = stmt.order_by(EntityModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return self._to_domain_entities(self._session.scalars(stmt).all())

    def search(
        self,
        research_space_id: str,
        query: str,
        *,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[KernelEntity]:
        canonical_query = canonicalize_entity_match_text(query)
        if not canonical_query:
            return []
        normalized_query = normalize_entity_match_text(canonical_query)
        stmt = (
            select(EntityModel.id)
            .outerjoin(
                EntityAliasModel,
                and_(
                    EntityAliasModel.entity_id == EntityModel.id,
                    EntityAliasModel.is_active.is_(True),
                ),
            )
            .where(
                EntityModel.research_space_id == _as_uuid(research_space_id),
                or_(
                    EntityModel.display_label.ilike(f"%{canonical_query}%"),
                    EntityModel.display_label_normalized.like(f"%{normalized_query}%"),
                    EntityAliasModel.alias_label.ilike(f"%{canonical_query}%"),
                    EntityAliasModel.alias_normalized.like(f"%{normalized_query}%"),
                ),
            )
            .order_by(EntityModel.created_at.desc())
        )
        if entity_type is not None:
            stmt = stmt.where(EntityModel.entity_type == entity_type)
        entity_ids = self._dedupe_entity_ids(self._session.scalars(stmt).all())[:limit]
        if not entity_ids:
            return []
        models = self._session.scalars(
            select(EntityModel)
            .where(EntityModel.id.in_(entity_ids))
            .order_by(EntityModel.created_at.desc()),
        ).all()
        return self._to_domain_entities(models)

    def count_by_type(self, research_space_id: str) -> dict[str, int]:
        rows = self._session.execute(
            select(EntityModel.entity_type, func.count())
            .where(EntityModel.research_space_id == _as_uuid(research_space_id))
            .group_by(EntityModel.entity_type),
        ).all()
        return {row[0]: row[1] for row in rows}

    def count_global_by_type(self) -> dict[str, int]:
        rows = self._session.execute(
            select(EntityModel.entity_type, func.count()).group_by(
                EntityModel.entity_type,
            ),
        ).all()
        return {row[0]: row[1] for row in rows}

    def delete(self, entity_id: str) -> bool:
        entity_model = self._session.get(EntityModel, _as_uuid(entity_id))
        if entity_model is None:
            return False
        self._session.delete(entity_model)
        self._session.flush()
        return True

    @staticmethod
    def _normalize_display_label(
        display_label: str | None,
    ) -> tuple[str | None, str | None]:
        if display_label is None:
            return None, None
        canonical_label = canonicalize_entity_match_text(display_label)
        if not canonical_label:
            return None, None
        return canonical_label, normalize_entity_match_text(canonical_label)
