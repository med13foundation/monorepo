"""
SQLAlchemy implementation of KernelEntityRepository.

Handles entity CRUD, identifier management, and resolution-policy-based
deduplication against the ``entities`` and ``entity_identifiers`` tables.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy import insert as sa_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.domain.entities.kernel.entities import KernelEntity, KernelEntityIdentifier
from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
from src.models.database.kernel.entities import EntityIdentifierModel, EntityModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class SqlAlchemyKernelEntityRepository(KernelEntityRepository):
    """SQLAlchemy implementation of the kernel entity repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── CRUD ──────────────────────────────────────────────────────────

    def create(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        display_label: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelEntity:
        entity = EntityModel(
            id=uuid4(),
            research_space_id=_as_uuid(research_space_id),
            entity_type=entity_type,
            display_label=display_label,
            metadata_payload=metadata or {},
        )
        self._session.add(entity)
        self._session.flush()
        return KernelEntity.model_validate(entity)

    def get_by_id(self, entity_id: str) -> KernelEntity | None:
        model = self._session.get(EntityModel, _as_uuid(entity_id))
        return KernelEntity.model_validate(model) if model is not None else None

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
            entity_model.display_label = display_label

        if metadata is not None:
            merged = dict(entity_model.metadata_payload or {})
            merged.update(metadata)
            entity_model.metadata_payload = merged

        self._session.flush()
        return KernelEntity.model_validate(entity_model)

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
        return [
            KernelEntity.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

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
        return [
            KernelEntity.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def search(
        self,
        research_space_id: str,
        query: str,
        *,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[KernelEntity]:
        stmt = select(EntityModel).where(
            EntityModel.research_space_id == _as_uuid(research_space_id),
            EntityModel.display_label.ilike(f"%{query}%"),
        )
        if entity_type is not None:
            stmt = stmt.where(EntityModel.entity_type == entity_type)
        return [
            KernelEntity.model_validate(model)
            for model in self._session.scalars(stmt.limit(limit)).all()
        ]

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

    # ── Identifiers ───────────────────────────────────────────────────

    def add_identifier(
        self,
        *,
        entity_id: str,
        namespace: str,
        identifier_value: str,
        sensitivity: str = "INTERNAL",
    ) -> KernelEntityIdentifier:
        # Upsert — skip if already exists.
        #
        # Use dialect-appropriate INSERT .. ON CONFLICT to keep the kernel
        # repositories usable in SQLite-backed tests as well as Postgres.
        bind = self._session.get_bind()
        dialect_name = getattr(bind.dialect, "name", "")
        values = {
            "entity_id": _as_uuid(entity_id),
            "namespace": namespace,
            "identifier_value": identifier_value,
            "sensitivity": sensitivity,
        }
        if dialect_name == "sqlite":
            self._session.execute(
                sqlite_insert(EntityIdentifierModel)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=["entity_id", "namespace", "identifier_value"],
                ),
            )
        elif dialect_name == "postgresql":
            self._session.execute(
                pg_insert(EntityIdentifierModel)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=["entity_id", "namespace", "identifier_value"],
                ),
            )
        else:
            # Fallback: attempt a plain insert and rely on the unique index to raise.
            self._session.execute(sa_insert(EntityIdentifierModel).values(**values))
        self._session.flush()

        # Return the (possibly pre-existing) identifier row
        lookup = select(EntityIdentifierModel).where(
            EntityIdentifierModel.entity_id == _as_uuid(entity_id),
            EntityIdentifierModel.namespace == namespace,
            EntityIdentifierModel.identifier_value == identifier_value,
        )
        model = self._session.scalars(lookup).one()
        return KernelEntityIdentifier.model_validate(model)

    def find_by_identifier(
        self,
        *,
        namespace: str,
        identifier_value: str,
        research_space_id: str | None = None,
    ) -> KernelEntity | None:
        stmt = (
            select(EntityModel)
            .join(EntityIdentifierModel)
            .where(
                EntityIdentifierModel.namespace == namespace,
                EntityIdentifierModel.identifier_value == identifier_value,
            )
        )
        if research_space_id is not None:
            stmt = stmt.where(
                EntityModel.research_space_id == _as_uuid(research_space_id),
            )
        model = self._session.scalars(stmt).first()
        return KernelEntity.model_validate(model) if model is not None else None

    # ── Resolution ────────────────────────────────────────────────────

    def resolve(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        identifiers: dict[str, str],
    ) -> KernelEntity | None:
        """
        Try to match an existing entity using its identifiers.

        For each namespace→value pair, check ``entity_identifiers``.
        Return the first entity that matches within the research space + type scope.
        """
        for namespace, value in identifiers.items():
            entity = self.find_by_identifier(
                namespace=namespace,
                identifier_value=value,
                research_space_id=research_space_id,
            )
            if entity is not None and entity.entity_type == entity_type:
                return entity
        return None


__all__ = ["SqlAlchemyKernelEntityRepository"]
