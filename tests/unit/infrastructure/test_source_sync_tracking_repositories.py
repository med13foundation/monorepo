"""Tests for source sync state and source record ledger repositories."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.domain.entities.source_record_ledger import SourceRecordLedgerEntry
from src.domain.entities.source_sync_state import CheckpointKind, SourceSyncState
from src.domain.entities.user_data_source import SourceType
from src.infrastructure.repositories import (
    SqlAlchemySourceRecordLedgerRepository,
    SqlAlchemySourceSyncStateRepository,
)
from src.models.database import Base, UserDataSourceModel


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()


def _seed_source(session) -> UUID:
    source_id = uuid4()
    session.add(
        UserDataSourceModel(
            id=str(source_id),
            owner_id=str(uuid4()),
            research_space_id=None,
            name="Source with Sync State",
            description="",
            source_type="pubmed",
            template_id=None,
            configuration={"metadata": {"query": "MED13"}},
            status="active",
            ingestion_schedule={
                "enabled": True,
                "frequency": "hourly",
                "start_time": datetime.now(UTC).isoformat(),
                "timezone": "UTC",
                "backend_job_id": None,
            },
            quality_metrics={
                "completeness_score": None,
                "consistency_score": None,
                "timeliness_score": None,
                "overall_score": None,
                "last_assessed": None,
                "issues_count": 0,
            },
            last_ingested_at=None,
            tags=[],
            version="1.0",
        ),
    )
    session.commit()
    return source_id


def test_source_sync_state_upsert_and_fetch(session) -> None:
    source_id = _seed_source(session)
    repository = SqlAlchemySourceSyncStateRepository(session)

    initial_state = SourceSyncState(
        source_id=source_id,
        source_type=SourceType.CLINVAR,
        checkpoint_kind=CheckpointKind.CURSOR,
        checkpoint_payload={"cursor": "page-1"},
        query_signature="clinvar-med13-v1",
    )

    saved = repository.upsert(initial_state)
    assert saved.source_id == source_id
    assert saved.checkpoint_payload.get("cursor") == "page-1"

    fetched = repository.get_by_source(source_id)
    assert fetched is not None
    assert fetched.query_signature == "clinvar-med13-v1"

    updated = fetched.mark_success(
        successful_job_id=None,
        checkpoint_payload={"cursor": "page-2"},
    ).model_copy(update={"query_signature": "clinvar-med13-v2"})
    saved_updated = repository.upsert(updated)

    assert saved_updated.query_signature == "clinvar-med13-v2"
    assert saved_updated.checkpoint_payload.get("cursor") == "page-2"

    listed = repository.list_by_source_type(SourceType.CLINVAR)
    assert len(listed) == 1
    assert listed[0].source_id == source_id

    deleted = repository.delete_by_source(source_id)
    assert deleted is True
    assert repository.get_by_source(source_id) is None


def test_source_record_ledger_upsert_lookup_and_delete(session) -> None:
    source_id = _seed_source(session)
    repository = SqlAlchemySourceRecordLedgerRepository(session)

    entries = [
        SourceRecordLedgerEntry(
            source_id=source_id,
            external_record_id="CV-1001",
            payload_hash="hash-a",
        ),
        SourceRecordLedgerEntry(
            source_id=source_id,
            external_record_id="CV-1002",
            payload_hash="hash-b",
        ),
    ]
    saved_entries = repository.upsert_entries(entries)

    assert len(saved_entries) == 2
    assert repository.count_for_source(source_id) == 2

    fetched = repository.get_entries_by_external_ids(
        source_id=source_id,
        external_record_ids=["CV-1001", "CV-9999"],
    )
    assert set(fetched.keys()) == {"CV-1001"}
    assert fetched["CV-1001"].payload_hash == "hash-a"

    changed_entry = fetched["CV-1001"].mark_seen(
        payload_hash="hash-a-v2",
        seen_job_id=None,
    )
    repository.upsert_entries([changed_entry])
    changed_fetched = repository.get_entry(
        source_id=source_id,
        external_record_id="CV-1001",
    )

    assert changed_fetched is not None
    assert changed_fetched.payload_hash == "hash-a-v2"

    deleted_count = repository.delete_by_source(source_id)
    assert deleted_count == 2
    assert repository.count_for_source(source_id) == 0
