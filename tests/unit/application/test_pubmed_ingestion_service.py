"""Tests for the PubMed ingestion application service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from src.application.services.pubmed_ingestion_service import PubMedIngestionService
from src.application.services.storage_configuration_service import (
    StorageConfigurationService,
)
from src.domain.entities.publication import Publication, PublicationType
from src.domain.entities.source_record_ledger import (
    SourceRecordLedgerEntry,  # noqa: TC001
)
from src.domain.entities.source_sync_state import SourceSyncState  # noqa: TC001
from src.domain.entities.storage_configuration import StorageConfiguration
from src.domain.entities.user_data_source import (
    SourceConfiguration,
    SourceType,
    UserDataSource,
)
from src.domain.repositories.publication_repository import PublicationRepository
from src.domain.repositories.source_record_ledger_repository import (
    SourceRecordLedgerRepository,
)
from src.domain.services.ingestion import IngestionRunContext  # noqa: TC001
from src.domain.services.pubmed_ingestion import PubMedGateway
from src.domain.value_objects.identifiers import PublicationIdentifier
from src.type_definitions.ingestion import IngestResult
from src.type_definitions.storage import StorageUseCase

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from src.type_definitions.common import RawRecord
    from src.type_definitions.ingestion import RawRecord as PipelineRawRecord


class StubGateway(PubMedGateway):
    """Simple stub gateway returning pre-defined records."""

    def __init__(self, records: list[RawRecord]) -> None:
        self.records = records
        self.called_with: list[dict[str, object]] = []

    async def fetch_records(self, config) -> list[RawRecord]:  # type: ignore[override]
        self.called_with.append(config.model_dump())
        return self.records


class StubPublicationRepository(PublicationRepository):
    """In-memory publication repository for unit testing."""

    def __init__(self, existing: Publication | None = None) -> None:
        self.created: list[Publication] = []
        self.updated: list[tuple[int, dict]] = []
        self._existing = existing

    def find_by_pmid(self, pmid: str) -> Publication | None:
        if self._existing and self._existing.identifier.pubmed_id == pmid:
            return self._existing
        return None

    def find_by_doi(self, doi: str) -> Publication | None:  # pragma: no cover - unused
        return None

    def find_by_title(  # pragma: no cover - unused
        self,
        title: str,
        *,
        fuzzy: bool = False,
    ) -> list[Publication]:
        return []

    def find_by_author(self, author_name: str) -> list[Publication]:  # pragma: no cover
        return []

    def find_by_year_range(  # pragma: no cover
        self,
        start_year: int,
        end_year: int,
    ) -> list[Publication]:
        return []

    def find_by_gene_associations(  # pragma: no cover
        self,
        gene_id: int,
    ) -> list[Publication]:
        return []

    def find_by_variant_associations(  # pragma: no cover
        self,
        variant_id: int,
    ) -> list[Publication]:
        return []

    def search_publications(  # pragma: no cover
        self,
        query: str,
        limit: int = 10,
        filters=None,
    ) -> list[Publication]:
        return []

    def paginate_publications(  # pragma: no cover
        self,
        page: int,
        per_page: int,
        sort_by: str,
        sort_order: str,
        filters=None,
    ) -> tuple[list[Publication], int]:
        return ([], 0)

    def get_publication_statistics(
        self,
    ) -> dict[str, int | float | bool | str | None]:  # pragma: no cover
        return {}

    def find_recent_publications(
        self,
        days: int = 30,
    ) -> list[Publication]:  # pragma: no cover
        return []

    def find_med13_relevant(  # pragma: no cover
        self,
        min_relevance: int = 3,
        limit: int | None = None,
    ) -> list[Publication]:
        return []

    def update_publication(
        self,
        publication_id: int,
        updates,
    ) -> Publication:
        self.updated.append((publication_id, dict(updates)))
        assert self._existing is not None
        return self._existing

    def update(  # pragma: no cover - interface requirement
        self,
        publication_id: int,
        updates,
    ) -> Publication:
        return self.update_publication(publication_id, updates)

    def find_by_owner(self, owner_id, skip=0, limit=50):  # pragma: no cover
        return []

    def find_by_type(self, source_type, skip=0, limit=50):  # pragma: no cover
        return []

    def find_by_status(self, status, skip=0, limit=50):  # pragma: no cover
        return []

    def find_active_sources(self, skip=0, limit=50):  # pragma: no cover
        return []

    def find_by_tag(self, tag, skip=0, limit=50):  # pragma: no cover
        return []

    def search_by_name(
        self,
        query,
        owner_id=None,
        skip=0,
        limit=50,
    ):  # pragma: no cover
        return []

    def update_status(self, source_id, status):  # pragma: no cover
        raise NotImplementedError

    def update_quality_metrics(self, source_id, metrics):  # pragma: no cover
        raise NotImplementedError

    def update_configuration(self, source_id, config):  # pragma: no cover
        raise NotImplementedError

    def update_ingestion_schedule(self, source_id, schedule):  # pragma: no cover
        raise NotImplementedError

    def record_ingestion(self, source_id):  # pragma: no cover
        raise NotImplementedError

    def delete(self, source_id):  # pragma: no cover
        raise NotImplementedError

    def save(self, entity):  # pragma: no cover
        raise NotImplementedError

    def find_by_id(self, entity_id):  # pragma: no cover
        raise NotImplementedError

    def find_all(self, skip=0, limit=50):  # pragma: no cover
        return []

    def create(self, publication: Publication) -> Publication:
        self.created.append(publication)
        return publication

    def get_by_id(self, entity_id: int) -> Publication | None:  # pragma: no cover
        if self._existing and self._existing.id == entity_id:
            return self._existing
        return None

    def count(self) -> int:  # pragma: no cover
        return len(self.created) + (1 if self._existing else 0)

    def exists(self, entity_id: int) -> bool:  # pragma: no cover
        return bool(self.get_by_id(entity_id))

    def find_by_criteria(self, *_args, **_kwargs):  # pragma: no cover
        return []


class StubPipeline:
    """In-memory ingestion pipeline test double."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[PipelineRawRecord], str]] = []

    def run(
        self,
        records: list[PipelineRawRecord],
        research_space_id: str,
    ) -> IngestResult:
        self.calls.append((records, research_space_id))
        return IngestResult(success=True, observations_created=len(records))


class StubLedgerRepository(SourceRecordLedgerRepository):
    def __init__(self, entries: list[SourceRecordLedgerEntry] | None = None) -> None:
        self._entries: dict[tuple[str, str], SourceRecordLedgerEntry] = {
            (str(entry.source_id), entry.external_record_id): entry
            for entry in (entries or [])
        }

    def get_entry(
        self,
        *,
        source_id: UUID,
        external_record_id: str,
    ) -> SourceRecordLedgerEntry | None:
        return self._entries.get((str(source_id), external_record_id))

    def get_entries_by_external_ids(
        self,
        *,
        source_id: UUID,
        external_record_ids: list[str],
    ) -> dict[str, SourceRecordLedgerEntry]:
        results: dict[str, SourceRecordLedgerEntry] = {}
        for external_record_id in external_record_ids:
            entry = self._entries.get((str(source_id), external_record_id))
            if entry is not None:
                results[external_record_id] = entry
        return results

    def upsert_entries(
        self,
        entries: list[SourceRecordLedgerEntry],
    ) -> list[SourceRecordLedgerEntry]:
        for entry in entries:
            self._entries[(str(entry.source_id), entry.external_record_id)] = entry
        return entries

    def delete_by_source(self, source_id: UUID) -> int:
        prefix = str(source_id)
        keys = [key for key in self._entries if key[0] == prefix]
        for key in keys:
            self._entries.pop(key, None)
        return len(keys)

    def count_for_source(self, source_id: UUID) -> int:
        prefix = str(source_id)
        return sum(1 for key in self._entries if key[0] == prefix)

    def delete_entries_older_than(
        self,
        *,
        cutoff: datetime,
        limit: int = 1000,
    ) -> int:
        _ = cutoff
        _ = limit
        return 0


def _build_source(metadata: dict) -> UserDataSource:
    return UserDataSource(
        id=uuid4(),
        owner_id=uuid4(),
        research_space_id=None,
        name="PubMed Source",
        description="",
        source_type=SourceType.PUBMED,
        template_id=None,
        configuration=SourceConfiguration(metadata=metadata),
        tags=[],
    )


def _make_publication(pmid: str) -> Publication:
    return Publication(
        identifier=PublicationIdentifier(pubmed_id=pmid),
        title="Existing Article",
        authors=("Smith, Jane",),
        journal="Existing Journal",
        publication_year=2020,
        publication_type=PublicationType.JOURNAL_ARTICLE,
    )


@pytest.mark.asyncio
async def test_ingest_stores_raw_records_if_configured() -> None:
    """Test that raw records are stored when storage service is available."""
    repository = StubPublicationRepository()
    gateway = StubGateway(records=[{"pubmed_id": "100", "title": "Test"}])

    # Mock storage service
    mock_storage = Mock(spec=StorageConfigurationService)
    mock_config = Mock(spec=StorageConfiguration)
    mock_storage.resolve_backend_for_use_case.return_value = mock_config
    mock_storage.record_store_operation = AsyncMock()

    service = PubMedIngestionService(
        gateway=gateway,
        pipeline=Mock(),
        publication_repository=repository,
        storage_service=mock_storage,
    )
    source = _build_source({"query": "MED13"})

    await service.ingest(source)

    # Verify storage interactions
    mock_storage.resolve_backend_for_use_case.assert_called_with(
        StorageUseCase.RAW_SOURCE,
    )
    mock_storage.record_store_operation.assert_called_once()

    # Verify call args
    call_args = mock_storage.record_store_operation.call_args
    assert call_args.kwargs["configuration"] == mock_config
    assert call_args.kwargs["content_type"] == "application/json"
    assert call_args.kwargs["user_id"] == source.owner_id
    assert "raw/" in call_args.kwargs["key"]


@pytest.mark.asyncio
async def test_rejects_non_pubmed_source() -> None:
    repository = StubPublicationRepository()
    gateway = StubGateway(records=[])
    service = PubMedIngestionService(
        gateway=gateway,
        pipeline=Mock(),
        publication_repository=repository,
    )

    source = _build_source({"query": "MED13"}).model_copy(
        update={"source_type": SourceType.API},
    )

    with pytest.raises(ValueError):
        await service.ingest(source)


@pytest.mark.asyncio
async def test_ingest_skips_unchanged_records_using_ledger() -> None:
    unchanged_record: RawRecord = {"pmid": "100", "title": "Known"}
    changed_record: RawRecord = {"pmid": "101", "title": "New"}
    gateway = StubGateway(records=[unchanged_record, changed_record])
    pipeline = StubPipeline()
    service = PubMedIngestionService(
        gateway=gateway,
        pipeline=pipeline,
        publication_repository=StubPublicationRepository(),
    )

    source = _build_source({"query": "MED13"}).model_copy(
        update={"research_space_id": uuid4()},
    )
    existing_entry = SourceRecordLedgerEntry(
        source_id=source.id,
        external_record_id="pubmed:pmid:100",
        payload_hash=PubMedIngestionService._compute_payload_hash(unchanged_record),
    )
    ledger = StubLedgerRepository(entries=[existing_entry])
    context = IngestionRunContext(
        ingestion_job_id=uuid4(),
        source_sync_state=SourceSyncState(
            source_id=source.id,
            source_type=SourceType.PUBMED,
        ),
        query_signature="pubmed-signature",
        source_record_ledger_repository=ledger,
    )

    summary = await service.ingest(source, context=context)

    assert summary.fetched_records == 2
    assert summary.parsed_publications == 1
    assert summary.new_records == 1
    assert summary.unchanged_records == 1
    assert summary.skipped_records == 1
    assert len(pipeline.calls) == 1
    assert len(pipeline.calls[0][0]) == 1
    assert ledger.count_for_source(source.id) == 2
