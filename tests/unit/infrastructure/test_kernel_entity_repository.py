"""Unit tests for SQLAlchemy kernel entity repository adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import select

from src.domain.entities.user import UserRole, UserStatus
from src.infrastructure.repositories.kernel.kernel_entity_repository import (
    SqlAlchemyKernelEntityRepository,
)
from src.infrastructure.security.key_provider import PHIKeyMaterial
from src.infrastructure.security.phi_encryption import PHIEncryptionService
from src.models.database.kernel.entities import EntityIdentifierModel, EntityModel
from src.models.database.research_space import ResearchSpaceModel, SpaceStatusEnum
from src.models.database.user import UserModel
from tests.graph_seed_helpers import ensure_entity_types

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(slots=True)
class StaticKeyProvider:
    key_material: PHIKeyMaterial

    def get_key_material(self) -> PHIKeyMaterial:
        return self.key_material


def _build_phi_encryption_service() -> PHIEncryptionService:
    provider = StaticKeyProvider(
        PHIKeyMaterial(
            encryption_key=bytes([9]) * 32,
            blind_index_key=bytes([10]) * 32,
            key_version="v1",
            blind_index_version="v1",
        ),
    )
    return PHIEncryptionService(provider)


def _seed_space_and_entity(db_session: Session) -> tuple[UUID, UUID]:
    ensure_entity_types(db_session, "PATIENT")
    owner_id = uuid4()
    db_session.add(
        UserModel(
            id=owner_id,
            email=f"{owner_id}@example.org",
            username=f"user_{str(owner_id).replace('-', '')[:8]}",
            full_name="Entity Repo User",
            hashed_password="hashed",
            role=UserRole.RESEARCHER,
            status=UserStatus.ACTIVE,
            email_verified=True,
        ),
    )

    research_space_id = uuid4()
    db_session.add(
        ResearchSpaceModel(
            id=research_space_id,
            slug=f"space-{str(research_space_id).replace('-', '')[:8]}",
            name="Entity Repo Space",
            description="Research space for entity repository tests",
            owner_id=owner_id,
            status=SpaceStatusEnum.ACTIVE,
            settings={},
            tags=[],
        ),
    )

    entity_id = uuid4()
    db_session.add(
        EntityModel(
            id=entity_id,
            research_space_id=research_space_id,
            entity_type="PATIENT",
            display_label="Patient 1",
            metadata_payload={},
        ),
    )
    db_session.flush()
    return research_space_id, entity_id


def test_add_phi_identifier_encrypts_and_resolves(db_session: Session) -> None:
    research_space_id, entity_id = _seed_space_and_entity(db_session)
    encryption_service = _build_phi_encryption_service()
    repository = SqlAlchemyKernelEntityRepository(
        db_session,
        phi_encryption_service=encryption_service,
        enable_phi_encryption=True,
    )

    created = repository.add_identifier(
        entity_id=str(entity_id),
        namespace="MRN",
        identifier_value="MRN-123",
        sensitivity="PHI",
    )

    assert created.identifier_value == "MRN-123"
    assert created.identifier_blind_index is not None
    assert created.encryption_key_version == "v1"
    assert created.blind_index_version == "v1"

    persisted = db_session.scalars(
        select(EntityIdentifierModel).where(
            EntityIdentifierModel.entity_id == entity_id,
            EntityIdentifierModel.namespace == "MRN",
        ),
    ).one()
    assert persisted.identifier_value != "MRN-123"
    assert persisted.identifier_blind_index == encryption_service.blind_index("MRN-123")

    resolved = repository.find_by_identifier(
        namespace="MRN",
        identifier_value="MRN-123",
        research_space_id=str(research_space_id),
    )
    assert resolved is not None
    assert str(resolved.id) == str(entity_id)


def test_add_phi_identifier_is_idempotent_by_blind_index(db_session: Session) -> None:
    _research_space_id, entity_id = _seed_space_and_entity(db_session)
    encryption_service = _build_phi_encryption_service()
    repository = SqlAlchemyKernelEntityRepository(
        db_session,
        phi_encryption_service=encryption_service,
        enable_phi_encryption=True,
    )

    first = repository.add_identifier(
        entity_id=str(entity_id),
        namespace="MRN",
        identifier_value="MRN-456",
        sensitivity="PHI",
    )
    second = repository.add_identifier(
        entity_id=str(entity_id),
        namespace="MRN",
        identifier_value="MRN-456",
        sensitivity="PHI",
    )

    assert first.id == second.id

    rows = db_session.scalars(
        select(EntityIdentifierModel).where(
            EntityIdentifierModel.entity_id == entity_id,
            EntityIdentifierModel.namespace == "MRN",
        ),
    ).all()
    assert len(rows) == 1


def test_non_phi_identifier_passthrough_when_encryption_enabled(
    db_session: Session,
) -> None:
    _research_space_id, entity_id = _seed_space_and_entity(db_session)
    repository = SqlAlchemyKernelEntityRepository(
        db_session,
        phi_encryption_service=_build_phi_encryption_service(),
        enable_phi_encryption=True,
    )

    created = repository.add_identifier(
        entity_id=str(entity_id),
        namespace="HGNC",
        identifier_value="HGNC:1234",
        sensitivity="INTERNAL",
    )

    assert created.identifier_value == "HGNC:1234"
    assert created.identifier_blind_index is None

    persisted = db_session.scalars(
        select(EntityIdentifierModel).where(
            EntityIdentifierModel.entity_id == entity_id,
            EntityIdentifierModel.namespace == "HGNC",
        ),
    ).one()
    assert persisted.identifier_value == "HGNC:1234"
    assert persisted.identifier_blind_index is None


def test_find_by_identifier_supports_legacy_plaintext_phi_rows(
    db_session: Session,
) -> None:
    research_space_id, entity_id = _seed_space_and_entity(db_session)
    repository = SqlAlchemyKernelEntityRepository(
        db_session,
        phi_encryption_service=_build_phi_encryption_service(),
        enable_phi_encryption=True,
    )

    db_session.add(
        EntityIdentifierModel(
            entity_id=entity_id,
            namespace="MRN",
            identifier_value="LEGACY-MRN-001",
            identifier_blind_index=None,
            sensitivity="PHI",
        ),
    )
    db_session.flush()

    resolved = repository.find_by_identifier(
        namespace="MRN",
        identifier_value="LEGACY-MRN-001",
        research_space_id=str(research_space_id),
    )
    assert resolved is not None
    assert str(resolved.id) == str(entity_id)
