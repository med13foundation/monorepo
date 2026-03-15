"""Identifier and resolution mixin for the SQLAlchemy kernel entity repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import and_, or_, select
from sqlalchemy import insert as sa_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

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
from src.models.database.kernel.entities import EntityIdentifierModel, EntityModel

if TYPE_CHECKING:
    from uuid import UUID

    from src.domain.entities.kernel.entities import KernelEntity, KernelEntityIdentifier


class KernelEntityIdentifierMixin(KernelEntityRepositoryMixinBase):
    """Identifier, label resolution, and candidate lookup operations."""

    def add_identifier(  # noqa: C901, PLR0912, PLR0915
        self,
        *,
        entity_id: str,
        namespace: str,
        identifier_value: str,
        sensitivity: str = "INTERNAL",
    ) -> KernelEntityIdentifier:
        entity_uuid = _as_uuid(entity_id)
        entity_model = self._session.get(EntityModel, entity_uuid)
        if entity_model is None:
            msg = f"Entity '{entity_id}' does not exist."
            raise KernelEntityValidationError(msg)

        normalized_namespace = namespace.strip()
        if not normalized_namespace:
            msg = "namespace is required"
            raise KernelEntityValidationError(msg)
        canonical_identifier_value = canonicalize_entity_match_text(identifier_value)
        if not canonical_identifier_value:
            msg = "identifier_value is required"
            raise KernelEntityValidationError(msg)

        normalized_sensitivity = sensitivity.strip().upper() or "INTERNAL"
        uses_phi_encryption = self._uses_phi_encryption(normalized_sensitivity)
        blind_index: str | None = None
        normalized_identifier: str | None = None
        stored_identifier_value = canonical_identifier_value
        encryption_key_version: str | None = None
        blind_index_version: str | None = None

        if uses_phi_encryption:
            if self._phi_encryption_service is None:
                message = "PHI encryption is enabled but encryption service is missing"
                raise RuntimeError(message)
            blind_index = self._phi_encryption_service.blind_index(
                canonical_identifier_value,
            )
            stored_identifier_value = self._phi_encryption_service.encrypt(
                canonical_identifier_value,
            )
            encryption_key_version = self._phi_encryption_service.key_version
            blind_index_version = self._phi_encryption_service.blind_index_version
        else:
            normalized_identifier = normalize_entity_match_text(
                canonical_identifier_value,
            )

        existing_row = self._find_identifier_conflict(
            entity_id=entity_uuid,
            research_space_id=entity_model.research_space_id,
            namespace=normalized_namespace,
            canonical_identifier_value=canonical_identifier_value,
            normalized_identifier=normalized_identifier,
            blind_index=blind_index,
        )
        if existing_row is not None:
            if existing_row.entity_id == entity_uuid:
                return self._to_domain_identifier(existing_row)
            msg = (
                f"Identifier '{canonical_identifier_value}' in namespace "
                f"'{normalized_namespace}' is already assigned to another entity."
            )
            raise KernelEntityConflictError(msg)

        bind = self._session.get_bind()
        dialect_name = getattr(bind.dialect, "name", "")
        values = {
            "entity_id": entity_uuid,
            "research_space_id": entity_model.research_space_id,
            "namespace": normalized_namespace,
            "identifier_value": stored_identifier_value,
            "identifier_blind_index": blind_index,
            "identifier_normalized": normalized_identifier,
            "encryption_key_version": encryption_key_version,
            "blind_index_version": blind_index_version,
            "sensitivity": normalized_sensitivity,
        }
        if dialect_name == "postgresql":
            index_elements = (
                ["entity_id", "namespace", "identifier_blind_index"]
                if uses_phi_encryption
                else ["entity_id", "namespace", "identifier_value"]
            )
            self._session.execute(
                pg_insert(EntityIdentifierModel)
                .values(**values)
                .on_conflict_do_nothing(index_elements=index_elements),
            )
        else:
            self._session.execute(sa_insert(EntityIdentifierModel).values(**values))
        self._session.flush()

        if uses_phi_encryption:
            if blind_index is None:
                message = (
                    "PHI blind index was not computed for PHI identifier upsert lookup"
                )
                raise RuntimeError(message)
            lookup = select(EntityIdentifierModel).where(
                EntityIdentifierModel.entity_id == entity_uuid,
                EntityIdentifierModel.namespace == normalized_namespace,
                EntityIdentifierModel.identifier_blind_index == blind_index,
                EntityIdentifierModel.sensitivity == "PHI",
            )
        else:
            lookup = select(EntityIdentifierModel).where(
                EntityIdentifierModel.entity_id == entity_uuid,
                EntityIdentifierModel.namespace == normalized_namespace,
                EntityIdentifierModel.identifier_normalized == normalized_identifier,
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
        candidates = self.find_identifier_candidates(
            namespace=namespace,
            identifier_value=identifier_value,
            research_space_id=research_space_id,
        )
        return self._resolve_single_candidate(
            candidates,
            match_description=(
                f"identifier '{identifier_value}' in namespace '{namespace.strip()}'"
            ),
        )

    def find_identifier_candidates(
        self,
        *,
        namespace: str,
        identifier_value: str,
        research_space_id: str | None = None,
        entity_type: str | None = None,
    ) -> list[KernelEntity]:
        normalized_namespace = namespace.strip()
        if not normalized_namespace:
            return []
        models = self._find_identifier_matches(
            namespace=normalized_namespace,
            identifier_value=identifier_value,
            research_space_id=research_space_id,
            entity_type=entity_type,
        )
        return self._to_domain_entities(models)

    def find_by_display_label(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        display_label: str,
    ) -> KernelEntity | None:
        candidates = self.find_display_label_candidates(
            research_space_id=research_space_id,
            entity_type=entity_type,
            display_label=display_label,
        )
        return self._resolve_single_candidate(
            candidates,
            match_description=f"display label '{display_label}'",
        )

    def find_display_label_candidates(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        display_label: str,
    ) -> list[KernelEntity]:
        normalized_display_label = normalize_entity_match_text(display_label)
        if not normalized_display_label:
            return []
        models = self._session.scalars(
            select(EntityModel).where(
                EntityModel.research_space_id == _as_uuid(research_space_id),
                EntityModel.entity_type == entity_type,
                EntityModel.display_label_normalized == normalized_display_label,
            ),
        ).all()
        return self._to_domain_entities(self._dedupe_entity_models(models))

    def resolve_candidates(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        identifiers: dict[str, str],
    ) -> list[KernelEntity]:
        candidate_by_id: dict[UUID, KernelEntity] = {}
        for namespace, value in identifiers.items():
            for candidate in self.find_identifier_candidates(
                namespace=namespace,
                identifier_value=value,
                research_space_id=research_space_id,
                entity_type=entity_type,
            ):
                candidate_by_id[candidate.id] = candidate
        return list(candidate_by_id.values())

    def resolve(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        identifiers: dict[str, str],
    ) -> KernelEntity | None:
        candidates = self.resolve_candidates(
            research_space_id=research_space_id,
            entity_type=entity_type,
            identifiers=identifiers,
        )
        return self._resolve_single_candidate(
            candidates,
            match_description="identifier anchors",
        )

    def _uses_phi_encryption(self, sensitivity: str) -> bool:
        return (
            self._phi_encryption_enabled
            and self._phi_encryption_service is not None
            and sensitivity == "PHI"
        )

    def _find_identifier_conflict(  # noqa: PLR0913
        self,
        *,
        entity_id: UUID,
        research_space_id: UUID,
        namespace: str,
        canonical_identifier_value: str,
        normalized_identifier: str | None,
        blind_index: str | None,
    ) -> EntityIdentifierModel | None:
        stmt = select(EntityIdentifierModel).where(
            EntityIdentifierModel.research_space_id == research_space_id,
            EntityIdentifierModel.namespace == namespace,
        )
        if blind_index is not None:
            stmt = stmt.where(
                or_(
                    and_(
                        EntityIdentifierModel.sensitivity == "PHI",
                        EntityIdentifierModel.identifier_blind_index == blind_index,
                    ),
                    and_(
                        EntityIdentifierModel.sensitivity == "PHI",
                        EntityIdentifierModel.identifier_blind_index.is_(None),
                        EntityIdentifierModel.identifier_value
                        == canonical_identifier_value,
                    ),
                ),
            )
        else:
            stmt = stmt.where(
                and_(
                    EntityIdentifierModel.sensitivity != "PHI",
                    or_(
                        EntityIdentifierModel.identifier_normalized
                        == normalized_identifier,
                        and_(
                            EntityIdentifierModel.identifier_normalized.is_(None),
                            EntityIdentifierModel.identifier_value
                            == canonical_identifier_value,
                        ),
                    ),
                ),
            )
        models = self._session.scalars(stmt).all()
        if not models:
            return None
        for model in models:
            if model.entity_id == entity_id:
                return model
        return models[0]

    def _find_identifier_matches(
        self,
        *,
        namespace: str,
        identifier_value: str,
        research_space_id: str | None = None,
        entity_type: str | None = None,
    ) -> list[EntityModel]:
        canonical_identifier_value = canonicalize_entity_match_text(identifier_value)
        if not canonical_identifier_value:
            return []
        normalized_identifier = normalize_entity_match_text(canonical_identifier_value)
        stmt = (
            select(EntityModel)
            .join(EntityIdentifierModel)
            .where(EntityIdentifierModel.namespace == namespace)
        )
        blind_index: str | None = None
        if self._phi_encryption_enabled and self._phi_encryption_service is not None:
            blind_index = self._phi_encryption_service.blind_index(
                canonical_identifier_value,
            )

        non_phi_match = and_(
            EntityIdentifierModel.sensitivity != "PHI",
            or_(
                EntityIdentifierModel.identifier_normalized == normalized_identifier,
                and_(
                    EntityIdentifierModel.identifier_normalized.is_(None),
                    EntityIdentifierModel.identifier_value
                    == canonical_identifier_value,
                ),
            ),
        )
        conditions = [
            and_(
                EntityIdentifierModel.sensitivity == "PHI",
                EntityIdentifierModel.identifier_blind_index.is_(None),
                EntityIdentifierModel.identifier_value == canonical_identifier_value,
            ),
            non_phi_match,
        ]
        if blind_index is not None:
            conditions.insert(
                0,
                and_(
                    EntityIdentifierModel.sensitivity == "PHI",
                    EntityIdentifierModel.identifier_blind_index == blind_index,
                ),
            )
        stmt = stmt.where(or_(*conditions))
        if research_space_id is not None:
            stmt = stmt.where(
                EntityModel.research_space_id == _as_uuid(research_space_id),
            )
        if entity_type is not None:
            stmt = stmt.where(EntityModel.entity_type == entity_type)
        return self._dedupe_entity_models(self._session.scalars(stmt).all())
