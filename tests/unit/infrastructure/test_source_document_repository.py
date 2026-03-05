"""Tests for source document repository persistence and queue queries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.domain.entities.source_document import (
    DocumentExtractionStatus,
    DocumentFormat,
    EnrichmentStatus,
    SourceDocument,
)
from src.domain.entities.user_data_source import SourceType
from src.infrastructure.repositories import SqlAlchemySourceDocumentRepository
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


def _seed_source(session: Session) -> UUID:
    source_id = uuid4()
    session.add(
        UserDataSourceModel(
            id=str(source_id),
            owner_id=str(uuid4()),
            research_space_id=None,
            name="Source Document Test Source",
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


def test_upsert_and_pending_queries(session: Session) -> None:
    source_id = _seed_source(session)
    repository = SqlAlchemySourceDocumentRepository(session)
    initial_doc = SourceDocument(
        id=uuid4(),
        source_id=source_id,
        external_record_id="pubmed:pmid:1001",
        source_type=SourceType.PUBMED,
        document_format=DocumentFormat.MEDLINE_XML,
        raw_storage_key="pubmed/source/raw/batch-1.json",
        enrichment_status=EnrichmentStatus.PENDING,
        extraction_status=DocumentExtractionStatus.PENDING,
    )
    second_doc = SourceDocument(
        id=uuid4(),
        source_id=source_id,
        external_record_id="pubmed:pmid:1002",
        source_type=SourceType.PUBMED,
        document_format=DocumentFormat.MEDLINE_XML,
        raw_storage_key="pubmed/source/raw/batch-1.json",
        enrichment_status=EnrichmentStatus.ENRICHED,
        extraction_status=DocumentExtractionStatus.EXTRACTED,
    )

    created = repository.upsert_many([initial_doc, second_doc])
    assert len(created) == 2
    assert repository.count_for_source(source_id) == 2

    pending_enrichment = repository.list_pending_enrichment(
        source_id=source_id,
        limit=10,
    )
    assert len(pending_enrichment) == 1
    assert pending_enrichment[0].external_record_id == "pubmed:pmid:1001"

    pending_extraction = repository.list_pending_extraction(
        source_id=source_id,
        limit=10,
    )
    assert len(pending_extraction) == 1
    assert pending_extraction[0].external_record_id == "pubmed:pmid:1001"

    fetched = repository.get_by_source_external_record(
        source_id=source_id,
        external_record_id="pubmed:pmid:1001",
    )
    assert fetched is not None
    assert fetched.id == initial_doc.id

    updated_doc = SourceDocument(
        id=uuid4(),
        source_id=source_id,
        external_record_id="pubmed:pmid:1001",
        source_type=SourceType.PUBMED,
        document_format=DocumentFormat.MEDLINE_XML,
        raw_storage_key="pubmed/source/raw/batch-2.json",
        enriched_storage_key="documents/doc-1001/enriched.txt",
        enrichment_status=EnrichmentStatus.ENRICHED,
        extraction_status=DocumentExtractionStatus.EXTRACTED,
    )
    persisted_update = repository.upsert(updated_doc)

    assert persisted_update.id == initial_doc.id
    assert repository.count_for_source(source_id) == 2
    assert persisted_update.raw_storage_key == "pubmed/source/raw/batch-2.json"
    assert persisted_update.extraction_status == DocumentExtractionStatus.EXTRACTED


def test_delete_by_source(session: Session) -> None:
    source_id = _seed_source(session)
    repository = SqlAlchemySourceDocumentRepository(session)
    repository.upsert(
        SourceDocument(
            id=uuid4(),
            source_id=source_id,
            external_record_id="pubmed:pmid:delete-me",
            source_type=SourceType.PUBMED,
            document_format=DocumentFormat.MEDLINE_XML,
            enrichment_status=EnrichmentStatus.PENDING,
            extraction_status=DocumentExtractionStatus.PENDING,
        ),
    )

    assert repository.count_for_source(source_id) == 1
    deleted = repository.delete_by_source(source_id)
    assert deleted == 1
    assert repository.count_for_source(source_id) == 0


def test_upsert_round_trips_non_uuid_agent_run_ids(session: Session) -> None:
    source_id = _seed_source(session)
    repository = SqlAlchemySourceDocumentRepository(session)
    document = SourceDocument(
        id=uuid4(),
        source_id=source_id,
        external_record_id="pubmed:pmid:run-id-opaque",
        source_type=SourceType.PUBMED,
        document_format=DocumentFormat.MEDLINE_XML,
        enrichment_status=EnrichmentStatus.ENRICHED,
        extraction_status=DocumentExtractionStatus.EXTRACTED,
        enrichment_agent_run_id="enrich:pubmed:sha256:abc123",
        extraction_agent_run_id="extract:pubmed:sha256:def456",
    )

    persisted = repository.upsert(document)
    fetched = repository.get_by_source_external_record(
        source_id=source_id,
        external_record_id="pubmed:pmid:run-id-opaque",
    )

    assert persisted.enrichment_agent_run_id == "enrich:pubmed:sha256:abc123"
    assert persisted.extraction_agent_run_id == "extract:pubmed:sha256:def456"
    assert fetched is not None
    assert fetched.enrichment_agent_run_id == "enrich:pubmed:sha256:abc123"
    assert fetched.extraction_agent_run_id == "extract:pubmed:sha256:def456"


def test_recover_stale_in_progress_extraction(session: Session) -> None:
    source_id = _seed_source(session)
    repository = SqlAlchemySourceDocumentRepository(session)
    now = datetime.now(UTC)
    stale_document = SourceDocument(
        id=uuid4(),
        source_id=source_id,
        external_record_id="pubmed:pmid:stale-in-progress",
        source_type=SourceType.PUBMED,
        document_format=DocumentFormat.MEDLINE_XML,
        enrichment_status=EnrichmentStatus.ENRICHED,
        extraction_status=DocumentExtractionStatus.IN_PROGRESS,
        extraction_agent_run_id="entity-run-stale",
        updated_at=now - timedelta(minutes=45),
    )
    fresh_document = SourceDocument(
        id=uuid4(),
        source_id=source_id,
        external_record_id="pubmed:pmid:fresh-in-progress",
        source_type=SourceType.PUBMED,
        document_format=DocumentFormat.MEDLINE_XML,
        enrichment_status=EnrichmentStatus.ENRICHED,
        extraction_status=DocumentExtractionStatus.IN_PROGRESS,
        extraction_agent_run_id="entity-run-fresh",
        updated_at=now - timedelta(minutes=1),
    )
    pending_document = SourceDocument(
        id=uuid4(),
        source_id=source_id,
        external_record_id="pubmed:pmid:already-pending",
        source_type=SourceType.PUBMED,
        document_format=DocumentFormat.MEDLINE_XML,
        enrichment_status=EnrichmentStatus.ENRICHED,
        extraction_status=DocumentExtractionStatus.PENDING,
    )
    repository.upsert_many([stale_document, fresh_document, pending_document])

    recovered = repository.recover_stale_in_progress_extraction(
        stale_before=now - timedelta(minutes=10),
        source_id=source_id,
    )
    assert recovered == 1

    persisted_stale = repository.get_by_id(stale_document.id)
    assert persisted_stale is not None
    assert persisted_stale.extraction_status == DocumentExtractionStatus.PENDING
    assert persisted_stale.extraction_agent_run_id is None
    assert (
        persisted_stale.metadata.get("extraction_stale_recovery_reason")
        == "in_progress_timeout_recovered_to_pending"
    )

    persisted_fresh = repository.get_by_id(fresh_document.id)
    assert persisted_fresh is not None
    assert persisted_fresh.extraction_status == DocumentExtractionStatus.IN_PROGRESS

    pending_ids = {
        document.id
        for document in repository.list_pending_extraction(
            source_id=source_id,
            limit=10,
        )
    }
    assert stale_document.id in pending_ids
    assert pending_document.id in pending_ids
