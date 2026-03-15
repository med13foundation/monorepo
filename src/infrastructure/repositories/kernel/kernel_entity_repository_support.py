"""Shared support types for the SQLAlchemy kernel entity repository."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

    from src.domain.entities.kernel.entities import (
        KernelEntity,
        KernelEntityAlias,
        KernelEntityIdentifier,
    )
    from src.infrastructure.security.phi_encryption import PHIEncryptionService
    from src.models.database.kernel.entities import (
        EntityAliasModel,
        EntityIdentifierModel,
        EntityModel,
    )

logger = logging.getLogger(__name__)


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class KernelEntityRepositoryMixinBase:
    """Shared state and typing hooks for kernel entity repository mixins."""

    _session: Session
    _phi_encryption_enabled: bool
    _phi_encryption_service: PHIEncryptionService | None

    def _to_domain_entity(self, model: EntityModel) -> KernelEntity:
        raise NotImplementedError

    def _to_domain_entities(self, models: Sequence[EntityModel]) -> list[KernelEntity]:
        raise NotImplementedError

    def _to_domain_alias(self, model: EntityAliasModel) -> KernelEntityAlias:
        raise NotImplementedError

    def _to_domain_identifier(
        self,
        model: EntityIdentifierModel,
    ) -> KernelEntityIdentifier:
        raise NotImplementedError

    def _resolve_single_candidate(
        self,
        candidates: Sequence[KernelEntity],
        *,
        match_description: str,
    ) -> KernelEntity | None:
        raise NotImplementedError

    def _dedupe_entity_models(self, models: Sequence[EntityModel]) -> list[EntityModel]:
        raise NotImplementedError

    def _dedupe_entity_ids(self, entity_ids: Sequence[UUID]) -> list[UUID]:
        raise NotImplementedError

    def _dedupe_domain_entities(
        self,
        entities: Sequence[KernelEntity],
    ) -> list[KernelEntity]:
        raise NotImplementedError
