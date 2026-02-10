"""Tests for the SQLAlchemy ingestion job repository adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.domain.entities.ingestion_job import (
    IngestionError,
    IngestionJob,
    IngestionStatus,
    IngestionTrigger,
    JobMetrics,
)
from src.domain.value_objects.provenance import DataSource, Provenance
from src.infrastructure.repositories import SqlAlchemyIngestionJobRepository
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
            name="PubMed Source",
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


def _build_job(source_id: UUID) -> IngestionJob:
    return IngestionJob(
        id=uuid4(),
        source_id=source_id,
        trigger=IngestionTrigger.SCHEDULED,
        triggered_by=None,
        triggered_at=datetime.now(UTC),
        status=IngestionStatus.PENDING,
        provenance=Provenance(
            source=DataSource.COMPUTED,
            source_version=None,
            source_url=None,
            acquired_by="test",
            processing_steps=["test"],
        ),
        metadata={},
        source_config_snapshot={"metadata": {"query": "MED13"}},
    )


def test_save_and_find_job(session):
    source_id = _seed_source(session)
    repository = SqlAlchemyIngestionJobRepository(session)
    job = _build_job(source_id)

    saved = repository.save(job)
    assert saved.id == job.id

    fetched = repository.find_by_id(job.id)
    assert fetched is not None
    assert fetched.source_id == source_id
    assert fetched.status == IngestionStatus.PENDING


def test_update_metrics_and_errors(session):
    source_id = _seed_source(session)
    repository = SqlAlchemyIngestionJobRepository(session)
    job = repository.save(_build_job(source_id))

    metrics = JobMetrics(
        records_processed=5,
        records_failed=0,
        records_skipped=0,
        bytes_processed=1024,
        api_calls_made=1,
    )
    updated = repository.update_metrics(job.id, metrics)
    assert updated is not None
    assert updated.metrics.records_processed == 5

    updated_with_error = repository.add_error(
        job.id,
        IngestionError(
            error_type="timeout",
            error_message="API timed out",
        ),
    )
    assert updated_with_error is not None
    assert len(updated_with_error.errors) == 1
