"""
SQLAlchemy implementation of KernelEntityRepository.

Handles entity CRUD, identifier management, and resolution-policy-based
deduplication against the ``entities`` and ``entity_identifiers`` tables.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy import insert as sa_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.domain.entities.kernel.entities import KernelEntity, KernelEntityIdentifier
from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
from src.infrastructure.security.phi_encryption import (
    PHIEncryptionService,
    build_phi_encryption_service_from_env,
    is_phi_encryption_enabled,
)
from src.models.database.kernel.entities import EntityIdentifierModel, EntityModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class SqlAlchemyKernelEntityRepository(KernelEntityRepository):
    """SQLAlchemy implementation of the kernel entity repository."""

    def __init__(
        self,
        session: Session,
        *,
        phi_encryption_service: PHIEncryptionService | None = None,
        enable_phi_encryption: bool | None = None,
    ) -> None:
        self._session = session
        self._phi_encryption_enabled = (
            enable_phi_encryption
            if enable_phi_encryption is not None
            else is_phi_encryption_enabled()
        )
        self._phi_encryption_service = phi_encryption_service
        if self._phi_encryption_enabled and self._phi_encryption_service is None:
            self._phi_encryption_service = build_phi_encryption_service_from_env()

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
        entity_uuid = _as_uuid(entity_id)
        normalized_sensitivity = sensitivity.strip().upper() or "INTERNAL"
        uses_phi_encryption = self._uses_phi_encryption(normalized_sensitivity)
        blind_index: str | None = None
        stored_identifier_value = identifier_value
        encryption_key_version: str | None = None
        blind_index_version: str | None = None

        if uses_phi_encryption:
            if self._phi_encryption_service is None:
                message = "PHI encryption is enabled but encryption service is missing"
                raise RuntimeError(message)
            blind_index = self._phi_encryption_service.blind_index(identifier_value)
            existing_row = self._find_existing_phi_identifier(
                entity_id=entity_uuid,
                namespace=namespace,
                plaintext_identifier_value=identifier_value,
                blind_index=blind_index,
            )
            if existing_row is not None:
                return self._to_domain_identifier(existing_row)
            stored_identifier_value = self._phi_encryption_service.encrypt(
                identifier_value,
            )
            encryption_key_version = self._phi_encryption_service.key_version
            blind_index_version = self._phi_encryption_service.blind_index_version
        else:
            existing_row = self._find_existing_identifier(
                entity_id=entity_uuid,
                namespace=namespace,
                identifier_value=identifier_value,
            )
            if existing_row is not None:
                return self._to_domain_identifier(existing_row)

        # Upsert — skip if already exists.
        #
        # Use dialect-appropriate INSERT .. ON CONFLICT to keep the kernel
        # repositories usable in SQLite-backed tests as well as Postgres.
        bind = self._session.get_bind()
        dialect_name = getattr(bind.dialect, "name", "")
        values = {
            "entity_id": entity_uuid,
            "namespace": namespace,
            "identifier_value": stored_identifier_value,
            "identifier_blind_index": blind_index,
            "encryption_key_version": encryption_key_version,
            "blind_index_version": blind_index_version,
            "sensitivity": normalized_sensitivity,
        }
        if dialect_name == "sqlite":
            index_elements = (
                ["entity_id", "namespace", "identifier_blind_index"]
                if uses_phi_encryption
                else ["entity_id", "namespace", "identifier_value"]
            )
            self._session.execute(
                sqlite_insert(EntityIdentifierModel)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=index_elements,
                ),
            )
        elif dialect_name == "postgresql":
            index_elements = (
                ["entity_id", "namespace", "identifier_blind_index"]
                if uses_phi_encryption
                else ["entity_id", "namespace", "identifier_value"]
            )
            self._session.execute(
                pg_insert(EntityIdentifierModel)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=index_elements,
                ),
            )
        else:
            # Fallback: attempt a plain insert and rely on the unique index to raise.
            self._session.execute(sa_insert(EntityIdentifierModel).values(**values))
        self._session.flush()

        # Return the (possibly pre-existing) identifier row
        if uses_phi_encryption:
            if blind_index is None:
                message = (
                    "PHI blind index was not computed for PHI identifier upsert lookup"
                )
                raise RuntimeError(message)
            lookup = select(EntityIdentifierModel).where(
                EntityIdentifierModel.entity_id == entity_uuid,
                EntityIdentifierModel.namespace == namespace,
                EntityIdentifierModel.identifier_blind_index == blind_index,
                EntityIdentifierModel.sensitivity == "PHI",
            )
        else:
            lookup = select(EntityIdentifierModel).where(
                EntityIdentifierModel.entity_id == entity_uuid,
                EntityIdentifierModel.namespace == namespace,
                EntityIdentifierModel.identifier_value == identifier_value,
            )
        model = self._session.scalars(lookup).one()
        return self._to_domain_identifier(model)

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
            )
        )
        if self._phi_encryption_enabled and self._phi_encryption_service is not None:
            blind_index = self._phi_encryption_service.blind_index(identifier_value)
            stmt = stmt.where(
                or_(
                    and_(
                        EntityIdentifierModel.sensitivity == "PHI",
                        EntityIdentifierModel.identifier_blind_index == blind_index,
                    ),
                    and_(
                        EntityIdentifierModel.sensitivity == "PHI",
                        EntityIdentifierModel.identifier_blind_index.is_(None),
                        EntityIdentifierModel.identifier_value == identifier_value,
                    ),
                    and_(
                        EntityIdentifierModel.sensitivity != "PHI",
                        EntityIdentifierModel.identifier_value == identifier_value,
                    ),
                ),
            )
        else:
            stmt = stmt.where(
                EntityIdentifierModel.identifier_value == identifier_value,
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

    def _uses_phi_encryption(self, sensitivity: str) -> bool:
        return (
            self._phi_encryption_enabled
            and self._phi_encryption_service is not None
            and sensitivity == "PHI"
        )

    def _find_existing_identifier(
        self,
        *,
        entity_id: UUID,
        namespace: str,
        identifier_value: str,
    ) -> EntityIdentifierModel | None:
        lookup = select(EntityIdentifierModel).where(
            EntityIdentifierModel.entity_id == entity_id,
            EntityIdentifierModel.namespace == namespace,
            EntityIdentifierModel.identifier_value == identifier_value,
        )
        return self._session.scalars(lookup).first()

    def _find_existing_phi_identifier(
        self,
        *,
        entity_id: UUID,
        namespace: str,
        plaintext_identifier_value: str,
        blind_index: str,
    ) -> EntityIdentifierModel | None:
        lookup = select(EntityIdentifierModel).where(
            EntityIdentifierModel.entity_id == entity_id,
            EntityIdentifierModel.namespace == namespace,
            EntityIdentifierModel.sensitivity == "PHI",
            or_(
                EntityIdentifierModel.identifier_blind_index == blind_index,
                and_(
                    EntityIdentifierModel.identifier_blind_index.is_(None),
                    EntityIdentifierModel.identifier_value
                    == plaintext_identifier_value,
                ),
            ),
        )
        return self._session.scalars(lookup).first()

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


__all__ = ["SqlAlchemyKernelEntityRepository"]
