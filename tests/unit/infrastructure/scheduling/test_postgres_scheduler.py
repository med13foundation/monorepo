"""Tests for the Postgres-backed scheduler backend."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.domain.entities.user_data_source import IngestionSchedule, ScheduleFrequency
from src.infrastructure.scheduling import PostgresScheduler
from src.models.database import Base, UserDataSourceModel

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session


@pytest.fixture
def scheduler_components(
    tmp_path: Path,
) -> Iterator[tuple[sessionmaker[Session], PostgresScheduler, Engine]]:
    db_path = tmp_path / "postgres_scheduler_unit.sqlite"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    scheduler = PostgresScheduler(session_factory=session_factory)
    try:
        yield session_factory, scheduler, engine
    finally:
        engine.dispose()


def _seed_source(session_factory: sessionmaker[Session], *, name: str) -> UUID:
    source_id = uuid4()
    with session_factory() as session:
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


def _build_schedule(
    *,
    frequency: ScheduleFrequency,
    start_time: datetime,
    timezone: str = "UTC",
    cron_expression: str | None = None,
) -> IngestionSchedule:
    return IngestionSchedule(
        enabled=True,
        frequency=frequency,
        start_time=start_time,
        timezone=timezone,
        cron_expression=cron_expression,
    )


def test_register_job_survives_scheduler_restart(
    scheduler_components: tuple[sessionmaker[Session], PostgresScheduler, Engine],
) -> None:
    session_factory, scheduler, _engine = scheduler_components
    source_id = _seed_source(session_factory, name="Restart Durability Source")
    schedule = _build_schedule(
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=2),
    )

    registered = scheduler.register_job(source_id, schedule)

    restarted_scheduler = PostgresScheduler(session_factory=session_factory)
    stored = restarted_scheduler.get_job(registered.job_id)
    assert stored is not None
    assert stored.source_id == source_id
    assert stored.job_id == registered.job_id
    assert stored.schedule.backend_job_id == registered.job_id


def test_due_job_claim_advances_next_run_and_prevents_immediate_redelivery(
    scheduler_components: tuple[sessionmaker[Session], PostgresScheduler, Engine],
) -> None:
    session_factory, scheduler, _engine = scheduler_components
    source_id = _seed_source(session_factory, name="Due Claim Source")
    schedule = _build_schedule(
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=3),
    )
    job = scheduler.register_job(source_id, schedule)
    due_as_of = datetime.now(UTC) + timedelta(hours=1, seconds=5)

    first_claim = scheduler.get_due_jobs(as_of=due_as_of)
    assert len(first_claim) == 1
    assert first_claim[0].job_id == job.job_id

    refreshed = scheduler.get_job(job.job_id)
    assert refreshed is not None
    assert refreshed.next_run_at > due_as_of

    second_claim = scheduler.get_due_jobs(as_of=due_as_of)
    assert second_claim == []


def test_due_job_batch_size_limits_claimed_rows(
    scheduler_components: tuple[sessionmaker[Session], PostgresScheduler, Engine],
) -> None:
    session_factory, _scheduler, _engine = scheduler_components
    scheduler = PostgresScheduler(session_factory=session_factory, due_job_batch_size=1)
    source_a = _seed_source(session_factory, name="Batch Source A")
    source_b = _seed_source(session_factory, name="Batch Source B")
    schedule = _build_schedule(
        frequency=ScheduleFrequency.HOURLY,
        start_time=datetime.now(UTC) - timedelta(hours=4),
    )

    scheduler.register_job(source_a, schedule)
    scheduler.register_job(source_b, schedule)
    due_as_of = datetime.now(UTC) + timedelta(hours=1, seconds=5)

    first_batch = scheduler.get_due_jobs(as_of=due_as_of)
    second_batch = scheduler.get_due_jobs(as_of=due_as_of)
    third_batch = scheduler.get_due_jobs(as_of=due_as_of)

    assert len(first_batch) == 1
    assert len(second_batch) == 1
    assert third_batch == []
    assert {first_batch[0].source_id, second_batch[0].source_id} == {
        source_a,
        source_b,
    }


def test_register_cron_schedule_persists_expression(
    scheduler_components: tuple[sessionmaker[Session], PostgresScheduler, Engine],
) -> None:
    session_factory, scheduler, _engine = scheduler_components
    source_id = _seed_source(session_factory, name="Cron Source")
    schedule = _build_schedule(
        frequency=ScheduleFrequency.CRON,
        start_time=datetime.now(UTC),
        cron_expression="*/15 * * * *",
    )

    job = scheduler.register_job(source_id, schedule)
    stored = scheduler.get_job(job.job_id)

    assert stored is not None
    assert stored.schedule.frequency == ScheduleFrequency.CRON
    assert stored.schedule.cron_expression == "*/15 * * * *"
    assert stored.next_run_at.tzinfo is not None
