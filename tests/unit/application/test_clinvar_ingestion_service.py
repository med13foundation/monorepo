"""Tests for the ClinVar ingestion application service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from src.application.services.clinvar_ingestion_service import ClinVarIngestionService
from src.application.services.storage_configuration_service import (
    StorageConfigurationService,
)
from src.domain.entities.source_document import (
    DocumentExtractionStatus,
    DocumentFormat,
    EnrichmentStatus,
    SourceDocument,
)
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
from src.domain.repositories.source_document_repository import SourceDocumentRepository
from src.domain.repositories.source_record_ledger_repository import (
    SourceRecordLedgerRepository,
)
from src.domain.services.clinvar_ingestion import ClinVarGateway
from src.domain.services.ingestion import IngestionRunContext  # noqa: TC001
from src.type_definitions.ingestion import IngestResult
from src.type_definitions.storage import StorageUseCase

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from src.domain.entities.data_source_configs import ClinVarQueryConfig
    from src.type_definitions.common import RawRecord
    from src.type_definitions.ingestion import RawRecord as PipelineRawRecord


class StubGateway(ClinVarGateway):
    """Simple stub gateway returning pre-defined records."""

    def __init__(self, records: list[RawRecord]) -> None:
        self.records = records
        self.called = 0

    async def fetch_records(self, config: ClinVarQueryConfig) -> list[RawRecord]:
        assert config.gene_symbol == "MED13"
        self.called += 1
        return self.records


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


class StubSourceDocumentRepository(SourceDocumentRepository):
    def __init__(self) -> None:
        self._documents: dict[tuple[str, str], SourceDocument] = {}

    def get_by_id(self, document_id: UUID) -> SourceDocument | None:
        for document in self._documents.values():
            if document.id == document_id:
                return document
        return None

    def get_by_source_external_record(
        self,
        *,
        source_id: UUID,
        external_record_id: str,
    ) -> SourceDocument | None:
        return self._documents.get((str(source_id), external_record_id))

    def upsert(self, document: SourceDocument) -> SourceDocument:
        persisted = self.upsert_many([document])
        return persisted[0]

    def upsert_many(
        self,
        documents: list[SourceDocument],
    ) -> list[SourceDocument]:
        persisted: list[SourceDocument] = []
        for document in documents:
            key = (str(document.source_id), document.external_record_id)
            existing = self._documents.get(key)
            if existing is None:
                self._documents[key] = document
                persisted.append(document)
                continue
            updated = document.model_copy(update={"id": existing.id})
            self._documents[key] = updated
            persisted.append(updated)
        return persisted

    def list_pending_enrichment(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
    ) -> list[SourceDocument]:
        pending = [
            document
            for document in self._documents.values()
            if document.enrichment_status == EnrichmentStatus.PENDING
        ]
        if source_id is not None:
            pending = [
                document for document in pending if document.source_id == source_id
            ]
        if research_space_id is not None:
            pending = [
                document
                for document in pending
                if document.research_space_id == research_space_id
            ]
        if ingestion_job_id is not None:
            pending = [
                document
                for document in pending
                if document.ingestion_job_id == ingestion_job_id
            ]
        if isinstance(source_type, str) and source_type.strip():
            normalized_source_type = source_type.strip().lower()
            pending = [
                document
                for document in pending
                if document.source_type.value.strip().lower() == normalized_source_type
            ]
        return pending[: max(limit, 1)]

    def list_pending_extraction(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
    ) -> list[SourceDocument]:
        pending = [
            document
            for document in self._documents.values()
            if document.extraction_status == DocumentExtractionStatus.PENDING
        ]
        if source_id is not None:
            pending = [
                document for document in pending if document.source_id == source_id
            ]
        if research_space_id is not None:
            pending = [
                document
                for document in pending
                if document.research_space_id == research_space_id
            ]
        if ingestion_job_id is not None:
            pending = [
                document
                for document in pending
                if document.ingestion_job_id == ingestion_job_id
            ]
        if isinstance(source_type, str) and source_type.strip():
            normalized_source_type = source_type.strip().lower()
            pending = [
                document
                for document in pending
                if document.source_type.value.strip().lower() == normalized_source_type
            ]
        return pending[: max(limit, 1)]

    def delete_by_source(self, source_id: UUID) -> int:
        keys = [key for key in self._documents if key[0] == str(source_id)]
        for key in keys:
            self._documents.pop(key, None)
        return len(keys)

    def count_for_source(self, source_id: UUID) -> int:
        return sum(1 for key in self._documents if key[0] == str(source_id))


def _build_source() -> UserDataSource:
    return UserDataSource(
        id=uuid4(),
        owner_id=uuid4(),
        research_space_id=uuid4(),
        name="ClinVar Source",
        description="",
        source_type=SourceType.CLINVAR,
        template_id=None,
        configuration=SourceConfiguration(
            metadata={
                "query": "MED13 pathogenic variant",
                "gene_symbol": "MED13",
                "max_results": 5,
            },
        ),
        tags=[],
    )


@pytest.mark.asyncio
async def test_ingest_runs_pipeline_and_returns_summary() -> None:
    gateway = StubGateway(
        records=[
            {
                "clinvar_id": "1001",
                "parsed_data": {
                    "gene_symbol": "MED13",
                    "clinical_significance": "pathogenic",
                },
            },
            {
                "clinvar_id": "1002",
                "parsed_data": {
                    "gene_symbol": "MED13",
                    "clinical_significance": "likely_pathogenic",
                },
            },
        ],
    )
    pipeline = StubPipeline()
    service = ClinVarIngestionService(gateway=gateway, pipeline=pipeline)

    source = _build_source()
    summary = await service.ingest(source)

    assert gateway.called == 1
    assert len(pipeline.calls) == 1
    assert summary.source_id == source.id
    assert summary.fetched_records == 2
    assert summary.parsed_publications == 2
    assert summary.created_publications == 2
    assert summary.updated_publications == 0
    assert summary.executed_query == "MED13 pathogenic variant"


@pytest.mark.asyncio
async def test_ingest_stores_raw_records_and_upserts_source_documents() -> None:
    gateway = StubGateway(
        records=[
            {
                "clinvar_id": "1001",
                "parsed_data": {"gene_symbol": "MED13"},
            },
        ],
    )
    pipeline = StubPipeline()
    mock_storage = Mock(spec=StorageConfigurationService)
    mock_config = Mock(spec=StorageConfiguration)
    mock_storage.resolve_backend_for_use_case.return_value = mock_config
    mock_store_operation = Mock()
    mock_store_operation.key = "clinvar/raw/batch.json"
    mock_storage.record_store_operation = AsyncMock(return_value=mock_store_operation)
    source_document_repository = StubSourceDocumentRepository()
    service = ClinVarIngestionService(
        gateway=gateway,
        pipeline=pipeline,
        storage_service=mock_storage,
        source_document_repository=source_document_repository,
    )
    source = _build_source()

    await service.ingest(source)

    mock_storage.resolve_backend_for_use_case.assert_called_with(
        StorageUseCase.RAW_SOURCE,
    )
    mock_storage.record_store_operation.assert_called_once()
    saved_document = source_document_repository.get_by_source_external_record(
        source_id=source.id,
        external_record_id="clinvar:clinvar_id:1001",
    )
    assert saved_document is not None
    assert saved_document.document_format == DocumentFormat.CLINVAR_XML
    assert saved_document.raw_storage_key == "clinvar/raw/batch.json"
    assert saved_document.enrichment_status == EnrichmentStatus.PENDING
    assert saved_document.extraction_status == DocumentExtractionStatus.PENDING


@pytest.mark.asyncio
async def test_ingest_emits_source_record_extraction_targets() -> None:
    gateway = StubGateway(
        records=[
            {
                "clinvar_id": "1001",
                "parsed_data": {"gene_symbol": "MED13"},
            },
            {
                "clinvar_id": "1002",
                "parsed_data": {"gene_symbol": "MED13"},
            },
        ],
    )
    pipeline = StubPipeline()
    service = ClinVarIngestionService(gateway=gateway, pipeline=pipeline)

    summary = await service.ingest(_build_source())

    assert len(summary.extraction_targets) == 2
    first_target = summary.extraction_targets[0]
    assert first_target.source_type == SourceType.CLINVAR.value
    assert first_target.source_record_id.startswith("clinvar:clinvar_id:")
    assert first_target.metadata is not None
    assert first_target.metadata.get("source_type") == SourceType.CLINVAR.value


@pytest.mark.asyncio
async def test_rejects_non_clinvar_source() -> None:
    gateway = StubGateway(records=[])
    pipeline = StubPipeline()
    service = ClinVarIngestionService(gateway=gateway, pipeline=pipeline)

    source = _build_source().model_copy(update={"source_type": SourceType.API})

    with pytest.raises(ValueError):
        await service.ingest(source)


@pytest.mark.asyncio
async def test_ingest_skips_unchanged_records_using_ledger() -> None:
    unchanged_record: RawRecord = {
        "clinvar_id": "1001",
        "parsed_data": {"gene_symbol": "MED13"},
    }
    changed_record: RawRecord = {
        "clinvar_id": "1002",
        "parsed_data": {"gene_symbol": "MED13"},
    }
    gateway = StubGateway(records=[unchanged_record, changed_record])
    pipeline = StubPipeline()
    service = ClinVarIngestionService(gateway=gateway, pipeline=pipeline)
    source = _build_source()

    existing_entry = SourceRecordLedgerEntry(
        source_id=source.id,
        external_record_id="clinvar:clinvar_id:1001",
        payload_hash=ClinVarIngestionService._compute_payload_hash(unchanged_record),
    )
    ledger = StubLedgerRepository(entries=[existing_entry])
    context = IngestionRunContext(
        ingestion_job_id=uuid4(),
        source_sync_state=SourceSyncState(
            source_id=source.id,
            source_type=SourceType.CLINVAR,
        ),
        query_signature="clinvar-signature",
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
