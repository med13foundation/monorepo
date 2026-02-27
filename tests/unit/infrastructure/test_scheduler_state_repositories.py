"""Tests for scheduler job and source lock repository adapters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.domain.entities.ingestion_scheduler_job import IngestionSchedulerJob
from src.domain.entities.ingestion_source_lock import IngestionSourceLock
from src.domain.entities.user_data_source import ScheduleFrequency
from src.infrastructure.repositories import (
    SqlAlchemyIngestionSchedulerJobRepository,
    SqlAlchemyIngestionSourceLockRepository,
)
from src.models.database import Base, UserDataSourceModel

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()


def _seed_source(session: Session, *, name: str) -> UUID:
    source_id = uuid4()
    session.add(
        UserDataSourceModel(
            id=str(source_id),
            owner_id=str(uuid4()),
            research_space_id=None,
            name=name,
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


def test_scheduler_job_repository_upsert_due_and_delete(session: Session) -> None:
    source_due = _seed_source(session, name="Due Source")
    source_future = _seed_source(session, name="Future Source")
    repository = SqlAlchemyIngestionSchedulerJobRepository(session)
    now = datetime.now(UTC)

    due_job = IngestionSchedulerJob(
        job_id="job-due",
        source_id=source_due,
        frequency=ScheduleFrequency.HOURLY,
        timezone="UTC",
        next_run_at=now - timedelta(minutes=1),
    )
    future_job = IngestionSchedulerJob(
        job_id="job-future",
        source_id=source_future,
        frequency=ScheduleFrequency.DAILY,
        timezone="UTC",
        next_run_at=now + timedelta(hours=2),
    )

    persisted_due = repository.upsert(due_job)
    repository.upsert(future_job)

    fetched_by_job = repository.get_by_job_id("job-due")
    assert fetched_by_job is not None
    assert fetched_by_job.source_id == source_due

    fetched_by_source = repository.get_by_source(source_due)
    assert fetched_by_source is not None
    assert fetched_by_source.job_id == persisted_due.job_id

    due_jobs = repository.list_due(as_of=now, limit=10)
    assert len(due_jobs) == 1
    assert due_jobs[0].job_id == "job-due"

    assert repository.delete_by_job_id("job-due") is True
    assert repository.delete_by_job_id("job-due") is False
    assert repository.delete_by_source(source_future) is True
    assert repository.delete_by_source(source_future) is False


def test_ingestion_source_lock_repository_expiry_and_delete(session: Session) -> None:
    source_expired = _seed_source(session, name="Expired Lock Source")
    source_active = _seed_source(session, name="Active Lock Source")
    repository = SqlAlchemyIngestionSourceLockRepository(session)
    now = datetime.now(UTC)

    expired_lock = IngestionSourceLock(
        source_id=source_expired,
        lock_token="expired-token",
        lease_expires_at=now - timedelta(seconds=15),
        last_heartbeat_at=now - timedelta(minutes=1),
        acquired_by="scheduler-worker-a",
    )
    active_lock = IngestionSourceLock(
        source_id=source_active,
        lock_token="active-token",
        lease_expires_at=now + timedelta(minutes=5),
        last_heartbeat_at=now,
        acquired_by="scheduler-worker-b",
    )
    repository.upsert(expired_lock)
    repository.upsert(active_lock)

    fetched = repository.get_by_source(source_expired)
    assert fetched is not None
    assert fetched.lock_token == "expired-token"

    expired_locks = repository.list_expired(as_of=now, limit=10)
    assert len(expired_locks) == 1
    assert expired_locks[0].source_id == source_expired
    assert expired_locks[0].is_expired(as_of=now) is True

    deleted_expired = repository.delete_expired(as_of=now, limit=10)
    assert deleted_expired == 1
    assert repository.get_by_source(source_expired) is None

    assert repository.delete_by_source(source_active) is True
    assert repository.delete_by_source(source_active) is False


def test_ingestion_source_lock_repository_try_acquire_respects_lease_ownership(
    session: Session,
) -> None:
    source_id = _seed_source(session, name="Lock Contention Source")
    repository = SqlAlchemyIngestionSourceLockRepository(session)
    now = datetime.now(UTC)
    repository.upsert(
        IngestionSourceLock(
            source_id=source_id,
            lock_token="worker-a-token",
            lease_expires_at=now + timedelta(minutes=3),
            last_heartbeat_at=now,
            acquired_by="worker-a",
        ),
    )

    rejected = repository.try_acquire(
        source_id=source_id,
        lock_token="worker-b-token",
        lease_expires_at=now + timedelta(minutes=4),
        heartbeat_at=now,
        acquired_by="worker-b",
    )
    assert rejected is None

    taken_over = repository.try_acquire(
        source_id=source_id,
        lock_token="worker-c-token",
        lease_expires_at=now + timedelta(minutes=5),
        heartbeat_at=now + timedelta(minutes=4),
        acquired_by="worker-c",
    )
    assert taken_over is not None
    assert taken_over.lock_token == "worker-c-token"


def test_ingestion_source_lock_repository_refresh_and_release_are_token_scoped(
    session: Session,
) -> None:
    source_id = _seed_source(session, name="Lock Refresh Source")
    repository = SqlAlchemyIngestionSourceLockRepository(session)
    now = datetime.now(UTC)
    token = "owner-token"

    acquired = repository.try_acquire(
        source_id=source_id,
        lock_token=token,
        lease_expires_at=now + timedelta(minutes=2),
        heartbeat_at=now,
        acquired_by="worker-a",
    )
    assert acquired is not None

    wrong_refresh = repository.refresh_lease(
        source_id=source_id,
        lock_token="wrong-token",
        lease_expires_at=now + timedelta(minutes=3),
        heartbeat_at=now + timedelta(seconds=30),
    )
    assert wrong_refresh is None

    refreshed = repository.refresh_lease(
        source_id=source_id,
        lock_token=token,
        lease_expires_at=now + timedelta(minutes=3),
        heartbeat_at=now + timedelta(seconds=30),
    )
    assert refreshed is not None
    assert refreshed.lock_token == token

    assert repository.release(source_id=source_id, lock_token="wrong-token") is False
    assert repository.release(source_id=source_id, lock_token=token) is True
