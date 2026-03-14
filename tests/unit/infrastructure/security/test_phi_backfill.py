from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from src.domain.entities.user import UserRole, UserStatus
from src.infrastructure.security.key_provider import PHIKeyMaterial
from src.infrastructure.security.phi_backfill import PHIIdentifierBackfillRunner
from src.infrastructure.security.phi_encryption import PHIEncryptionService
from src.models.database.kernel.entities import EntityIdentifierModel, EntityModel
from src.models.database.research_space import ResearchSpaceModel, SpaceStatusEnum
from src.models.database.user import UserModel
from tests.graph_seed_helpers import ensure_entity_types

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


@dataclass(slots=True)
class StaticKeyProvider:
    key_material: PHIKeyMaterial

    def get_key_material(self) -> PHIKeyMaterial:
        return self.key_material


def _build_encryption_service() -> PHIEncryptionService:
    provider = StaticKeyProvider(
        PHIKeyMaterial(
            encryption_key=bytes([21]) * 32,
            blind_index_key=bytes([22]) * 32,
            key_version="v1",
            blind_index_version="v1",
        ),
    )
    return PHIEncryptionService(provider)


def _session_factory(engine: Engine):
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


@pytest.fixture(autouse=True)
def _reset_identifier_table(db_session: Session) -> None:
    db_session.execute(delete(EntityIdentifierModel))
    db_session.commit()


def _seed_entity(session: Session) -> tuple[UUID, UUID]:
    ensure_entity_types(session, "PATIENT")
    owner_id = uuid4()
    session.add(
        UserModel(
            id=owner_id,
            email=f"{owner_id}@example.org",
            username=f"user_{str(owner_id).replace('-', '')[:8]}",
            full_name="Backfill User",
            hashed_password="hashed",
            role=UserRole.RESEARCHER,
            status=UserStatus.ACTIVE,
            email_verified=True,
        ),
    )

    research_space_id = uuid4()
    session.add(
        ResearchSpaceModel(
            id=research_space_id,
            slug=f"space-{str(research_space_id).replace('-', '')[:8]}",
            name="Backfill Space",
            description="Research space for PHI backfill tests",
            owner_id=owner_id,
            status=SpaceStatusEnum.ACTIVE,
            settings={},
            tags=[],
        ),
    )

    entity_id = uuid4()
    session.add(
        EntityModel(
            id=entity_id,
            research_space_id=research_space_id,
            entity_type="PATIENT",
            display_label="Patient Backfill",
            metadata_payload={},
        ),
    )
    session.flush()
    return research_space_id, entity_id


def test_backfill_updates_plaintext_phi_rows(db_session: Session) -> None:
    encryption_service = _build_encryption_service()
    space_id, entity_id = _seed_entity(db_session)
    db_session.add(
        EntityIdentifierModel(
            entity_id=entity_id,
            research_space_id=space_id,
            namespace="MRN",
            identifier_value="PLAIN-123",
            identifier_blind_index=None,
            sensitivity="PHI",
        ),
    )
    db_session.commit()

    factory = _session_factory(db_session.get_bind())
    runner = PHIIdentifierBackfillRunner(factory, encryption_service)
    summary = runner.run(batch_size=10, dry_run=False)

    assert summary.updated_rows == 1
    assert summary.failed_rows == 0

    with factory() as verify_session:
        row = verify_session.scalars(
            select(EntityIdentifierModel).where(
                EntityIdentifierModel.entity_id == entity_id,
                EntityIdentifierModel.namespace == "MRN",
            ),
        ).one()
        assert row.identifier_value != "PLAIN-123"
        assert row.identifier_blind_index == encryption_service.blind_index("PLAIN-123")
        assert row.encryption_key_version == "v1"
        assert row.blind_index_version == "v1"


def test_backfill_dry_run_rolls_back_changes(db_session: Session) -> None:
    encryption_service = _build_encryption_service()
    space_id, entity_id = _seed_entity(db_session)
    db_session.add(
        EntityIdentifierModel(
            entity_id=entity_id,
            research_space_id=space_id,
            namespace="MRN",
            identifier_value="PLAIN-DRY-RUN",
            identifier_blind_index=None,
            sensitivity="PHI",
        ),
    )
    db_session.commit()

    factory = _session_factory(db_session.get_bind())
    runner = PHIIdentifierBackfillRunner(factory, encryption_service)
    summary = runner.run(batch_size=10, dry_run=True)

    assert summary.updated_rows == 1
    assert summary.dry_run is True

    with factory() as verify_session:
        row = verify_session.scalars(
            select(EntityIdentifierModel).where(
                EntityIdentifierModel.entity_id == entity_id,
                EntityIdentifierModel.namespace == "MRN",
            ),
        ).one()
        assert row.identifier_value == "PLAIN-DRY-RUN"
        assert row.identifier_blind_index is None
        assert row.encryption_key_version is None


def test_backfill_skips_rows_without_pending_work(db_session: Session) -> None:
    encryption_service = _build_encryption_service()
    encrypted_value = encryption_service.encrypt("ALREADY-MIGRATED")
    blind_index = encryption_service.blind_index("ALREADY-MIGRATED")

    space_id, entity_id = _seed_entity(db_session)
    db_session.add(
        EntityIdentifierModel(
            entity_id=entity_id,
            research_space_id=space_id,
            namespace="MRN",
            identifier_value=encrypted_value,
            identifier_blind_index=blind_index,
            encryption_key_version="v1",
            blind_index_version="v1",
            sensitivity="PHI",
        ),
    )
    db_session.commit()

    factory = _session_factory(db_session.get_bind())
    runner = PHIIdentifierBackfillRunner(factory, encryption_service)
    summary = runner.run(batch_size=10, dry_run=False)

    assert summary.scanned_rows == 0
    assert summary.updated_rows == 0
    assert summary.failed_rows == 0


def test_backfill_completes_encrypted_rows_missing_blind_index(
    db_session: Session,
) -> None:
    encryption_service = _build_encryption_service()
    encrypted_value = encryption_service.encrypt("MISSING-BLIND")

    space_id, entity_id = _seed_entity(db_session)
    db_session.add(
        EntityIdentifierModel(
            entity_id=entity_id,
            research_space_id=space_id,
            namespace="MRN",
            identifier_value=encrypted_value,
            identifier_blind_index=None,
            encryption_key_version=None,
            blind_index_version=None,
            sensitivity="PHI",
        ),
    )
    db_session.commit()

    factory = _session_factory(db_session.get_bind())
    runner = PHIIdentifierBackfillRunner(factory, encryption_service)
    summary = runner.run(batch_size=10, dry_run=False)

    assert summary.updated_rows == 1

    with factory() as verify_session:
        row = verify_session.scalars(
            select(EntityIdentifierModel).where(
                EntityIdentifierModel.entity_id == entity_id,
                EntityIdentifierModel.namespace == "MRN",
            ),
        ).one()
        assert row.identifier_value == encrypted_value
        assert row.identifier_blind_index == encryption_service.blind_index(
            "MISSING-BLIND",
        )
        assert row.encryption_key_version == "v1"
        assert row.blind_index_version == "v1"


def test_backfill_load_batch_uses_graph_service_helper() -> None:
    encryption_service = _build_encryption_service()
    runner = PHIIdentifierBackfillRunner(lambda: Session(), encryption_service)
    session = Session()
    rows = [SimpleNamespace(id=101)]

    with pytest.MonkeyPatch.context() as monkeypatch:
        captured: dict[str, object] = {}

        def _fake_loader(*args: object, **kwargs: object) -> list[object]:
            captured["args"] = args
            captured["kwargs"] = kwargs
            return rows

        monkeypatch.setattr(
            "src.infrastructure.security.phi_backfill.load_phi_identifier_backfill_batch",
            _fake_loader,
        )
        result = runner._load_batch(
            session,
            last_seen_id=100,
            limit=25,
        )

    assert captured["args"] == (session,)
    assert captured["kwargs"] == {"last_seen_id": 100, "limit": 25}
    assert result == []
