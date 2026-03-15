"""SQLAlchemy implementation of the kernel entity repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
from src.infrastructure.repositories.kernel.kernel_entity_repository_alias_mixin import (
    KernelEntityAliasMixin,
)
from src.infrastructure.repositories.kernel.kernel_entity_repository_crud_mixin import (
    KernelEntityCrudMixin,
)
from src.infrastructure.repositories.kernel.kernel_entity_repository_identifier_mixin import (
    KernelEntityIdentifierMixin,
)
from src.infrastructure.repositories.kernel.kernel_entity_repository_mapping_mixin import (
    KernelEntityRepositoryMappingMixin,
)
from src.infrastructure.security.phi_encryption import (
    build_phi_encryption_service_from_env,
    is_phi_encryption_enabled,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.infrastructure.security.phi_encryption import PHIEncryptionService


class SqlAlchemyKernelEntityRepository(
    KernelEntityCrudMixin,
    KernelEntityIdentifierMixin,
    KernelEntityAliasMixin,
    KernelEntityRepositoryMappingMixin,
    KernelEntityRepository,
):
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


__all__ = ["SqlAlchemyKernelEntityRepository"]
