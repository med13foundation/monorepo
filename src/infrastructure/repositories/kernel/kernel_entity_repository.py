"""
SQLAlchemy implementation of KernelEntityRepository.

Handles entity CRUD, identifier management, and resolution-policy-based
deduplication against the ``entities`` and ``entity_identifiers`` tables.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
from src.models.database.kernel.entities import EntityIdentifierModel, EntityModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SqlAlchemyKernelEntityRepository(KernelEntityRepository):
    """SQLAlchemy implementation of the kernel entity repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── CRUD ──────────────────────────────────────────────────────────

    def create(
        self,
        *,
        study_id: str,
        entity_type: str,
        display_label: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> EntityModel:
        entity = EntityModel(
            id=str(uuid4()),
            study_id=study_id,
            entity_type=entity_type,
            display_label=display_label,
            metadata_payload=metadata or {},
        )
        self._session.add(entity)
        self._session.flush()
        return entity

    def get_by_id(self, entity_id: str) -> EntityModel | None:
        return self._session.get(EntityModel, entity_id)

    def find_by_type(
        self,
        study_id: str,
        entity_type: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[EntityModel]:
        stmt = (
            select(EntityModel)
            .where(
                EntityModel.study_id == study_id,
                EntityModel.entity_type == entity_type,
            )
            .order_by(EntityModel.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return list(self._session.scalars(stmt).all())

    def search(
        self,
        study_id: str,
        query: str,
        *,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[EntityModel]:
        stmt = select(EntityModel).where(
            EntityModel.study_id == study_id,
            EntityModel.display_label.ilike(f"%{query}%"),
        )
        if entity_type is not None:
            stmt = stmt.where(EntityModel.entity_type == entity_type)
        return list(self._session.scalars(stmt.limit(limit)).all())

    def count_by_type(self, study_id: str) -> dict[str, int]:
        rows = self._session.execute(
            select(EntityModel.entity_type, func.count())
            .where(EntityModel.study_id == study_id)
            .group_by(EntityModel.entity_type),
        ).all()
        return {row[0]: row[1] for row in rows}

    def delete(self, entity_id: str) -> bool:
        entity = self.get_by_id(entity_id)
        if entity is None:
            return False
        self._session.delete(entity)
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
    ) -> EntityIdentifierModel:
        # Upsert — skip if already exists
        stmt = (
            pg_insert(EntityIdentifierModel)
            .values(
                entity_id=entity_id,
                namespace=namespace,
                identifier_value=identifier_value,
                sensitivity=sensitivity,
            )
            .on_conflict_do_nothing(
                index_elements=["entity_id", "namespace", "identifier_value"],
            )
        )
        self._session.execute(stmt)
        self._session.flush()

        # Return the (possibly pre-existing) identifier row
        lookup = select(EntityIdentifierModel).where(
            EntityIdentifierModel.entity_id == entity_id,
            EntityIdentifierModel.namespace == namespace,
            EntityIdentifierModel.identifier_value == identifier_value,
        )
        return self._session.scalars(lookup).one()

    def find_by_identifier(
        self,
        *,
        namespace: str,
        identifier_value: str,
        study_id: str | None = None,
    ) -> EntityModel | None:
        stmt = (
            select(EntityModel)
            .join(EntityIdentifierModel)
            .where(
                EntityIdentifierModel.namespace == namespace,
                EntityIdentifierModel.identifier_value == identifier_value,
            )
        )
        if study_id is not None:
            stmt = stmt.where(EntityModel.study_id == study_id)
        return self._session.scalars(stmt).first()

    # ── Resolution ────────────────────────────────────────────────────

    def resolve(
        self,
        *,
        study_id: str,
        entity_type: str,
        identifiers: dict[str, str],
    ) -> EntityModel | None:
        """
        Try to match an existing entity using its identifiers.

        For each namespace→value pair, check ``entity_identifiers``.
        Return the first entity that matches within the study + type scope.
        """
        for namespace, value in identifiers.items():
            entity = self.find_by_identifier(
                namespace=namespace,
                identifier_value=value,
                study_id=study_id,
            )
            if entity is not None and entity.entity_type == entity_type:
                return entity
        return None


__all__ = ["SqlAlchemyKernelEntityRepository"]
