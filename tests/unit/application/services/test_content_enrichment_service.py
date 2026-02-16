"""Tests for ContentEnrichmentService orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from src.application.agents.services.content_enrichment_service import (
    ContentEnrichmentService,
    ContentEnrichmentServiceDependencies,
)
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.content_enrichment import ContentEnrichmentContract
from src.domain.entities.source_document import (
    DocumentExtractionStatus,
    DocumentFormat,
    EnrichmentStatus,
    SourceDocument,
)
from src.domain.entities.user_data_source import SourceType
from src.domain.repositories.source_document_repository import SourceDocumentRepository

if TYPE_CHECKING:
    from src.domain.agents.contexts.content_enrichment_context import (
        ContentEnrichmentContext,
    )


class StubSourceDocumentRepository(SourceDocumentRepository):
    """In-memory SourceDocument repository for service tests."""

    def __init__(self, documents: list[SourceDocument]) -> None:
        self._documents: dict[UUID, SourceDocument] = {doc.id: doc for doc in documents}

    def get_by_id(self, document_id: UUID) -> SourceDocument | None:
        return self._documents.get(document_id)

    def get_by_source_external_record(
        self,
        *,
        source_id: UUID,
        external_record_id: str,
    ) -> SourceDocument | None:
        for document in self._documents.values():
            if (
                document.source_id == source_id
                and document.external_record_id == external_record_id
            ):
                return document
        return None

    def upsert(self, document: SourceDocument) -> SourceDocument:
        self._documents[document.id] = document
        return document

    def upsert_many(
        self,
        documents: list[SourceDocument],
    ) -> list[SourceDocument]:
        for document in documents:
            self._documents[document.id] = document
        return documents

    def list_pending_enrichment(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
    ) -> list[SourceDocument]:
        docs = [
            document
            for document in self._documents.values()
            if document.enrichment_status == EnrichmentStatus.PENDING
        ]
        if source_id is not None:
            docs = [doc for doc in docs if doc.source_id == source_id]
        if research_space_id is not None:
            docs = [doc for doc in docs if doc.research_space_id == research_space_id]
        docs.sort(key=lambda item: item.created_at)
        return docs[: max(limit, 1)]

    def list_pending_extraction(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
    ) -> list[SourceDocument]:
        docs = [
            document
            for document in self._documents.values()
            if document.extraction_status == DocumentExtractionStatus.PENDING
        ]
        if source_id is not None:
            docs = [doc for doc in docs if doc.source_id == source_id]
        if research_space_id is not None:
            docs = [doc for doc in docs if doc.research_space_id == research_space_id]
        docs.sort(key=lambda item: item.created_at)
        return docs[: max(limit, 1)]

    def delete_by_source(self, source_id: UUID) -> int:
        to_delete = [
            document_id
            for document_id, document in self._documents.items()
            if document.source_id == source_id
        ]
        for document_id in to_delete:
            self._documents.pop(document_id, None)
        return len(to_delete)

    def count_for_source(self, source_id: UUID) -> int:
        return sum(1 for doc in self._documents.values() if doc.source_id == source_id)


class StubEnrichmentAgent:
    """Content enrichment agent stub returning pre-configured contracts."""

    def __init__(self, contract: ContentEnrichmentContract | None = None) -> None:
        self._contract = contract
        self.calls = 0

    async def enrich(
        self,
        context: ContentEnrichmentContext,
        *,
        model_id: str | None = None,
    ) -> ContentEnrichmentContract:
        _ = context
        _ = model_id
        self.calls += 1
        if self._contract is None:
            msg = "agent not configured"
            raise RuntimeError(msg)
        return self._contract

    async def close(self) -> None:
        return None


class StubStorageCoordinator:
    """Storage coordinator stub capturing stored content keys."""

    def __init__(self) -> None:
        self.calls = 0

    async def store_for_use_case(  # noqa: PLR0913
        self,
        use_case: object,
        *,
        key: str,
        file_path: object,
        content_type: str | None = None,
        user_id: UUID | None = None,
        metadata: dict[str, object] | None = None,
    ) -> object:
        _ = use_case
        _ = file_path
        _ = content_type
        _ = user_id
        _ = metadata
        self.calls += 1
        return SimpleNamespace(key=key)


def _build_document(
    *,
    source_type: SourceType = SourceType.PUBMED,
    enrichment_status: EnrichmentStatus = EnrichmentStatus.PENDING,
    raw_storage_key: str | None = None,
) -> SourceDocument:
    now = datetime.now(UTC)
    return SourceDocument(
        id=uuid4(),
        source_id=uuid4(),
        research_space_id=uuid4(),
        ingestion_job_id=uuid4(),
        external_record_id="record-1",
        source_type=source_type,
        document_format=(
            DocumentFormat.CLINVAR_XML
            if source_type == SourceType.CLINVAR
            else DocumentFormat.MEDLINE_XML
        ),
        raw_storage_key=raw_storage_key,
        enrichment_status=enrichment_status,
        extraction_status=DocumentExtractionStatus.PENDING,
        metadata={
            "raw_record": {
                "title": "MED13 signal",
                "abstract": "Abstract text for enrichment",
                "clinical_significance": "Pathogenic",
            },
        },
        created_at=now,
        updated_at=now,
    )


def _build_agent_contract(document_id: UUID) -> ContentEnrichmentContract:
    return ContentEnrichmentContract(
        decision="enriched",
        confidence_score=0.91,
        rationale="Fetched open-access text from enrichment source.",
        evidence=[
            EvidenceItem(
                source_type="api",
                locator="pmc:PMC123",
                excerpt="Full XML fetched successfully.",
                relevance=0.9,
            ),
        ],
        document_id=str(document_id),
        source_type="pubmed",
        acquisition_method="pmc_oa",
        content_format="text",
        content_length_chars=19,
        content_text="Enriched full text.",
        agent_run_id=str(uuid4()),
    )


@pytest.mark.asyncio
async def test_process_pending_documents_passes_through_structured_source() -> None:
    document = _build_document(
        source_type=SourceType.CLINVAR,
        raw_storage_key="clinvar/raw/record-1.json",
    )
    repository = StubSourceDocumentRepository([document])
    agent = StubEnrichmentAgent()
    service = ContentEnrichmentService(
        dependencies=ContentEnrichmentServiceDependencies(
            content_enrichment_agent=agent,
            source_document_repository=repository,
            storage_coordinator=None,
        ),
    )

    summary = await service.process_pending_documents(limit=5)
    updated = repository.get_by_id(document.id)
    assert updated is not None

    assert summary.enriched == 1
    assert summary.failed == 0
    assert agent.calls == 0
    assert updated.enrichment_status == EnrichmentStatus.ENRICHED
    assert updated.enrichment_method == "pass_through"
    assert updated.enriched_storage_key == "clinvar/raw/record-1.json"


@pytest.mark.asyncio
async def test_pass_through_reuses_raw_storage_key_when_coordinator_present() -> None:
    document = _build_document(
        source_type=SourceType.CLINVAR,
        raw_storage_key="clinvar/raw/record-1.json",
    )
    repository = StubSourceDocumentRepository([document])
    storage = StubStorageCoordinator()
    service = ContentEnrichmentService(
        dependencies=ContentEnrichmentServiceDependencies(
            content_enrichment_agent=None,
            source_document_repository=repository,
            storage_coordinator=storage,
        ),
    )

    summary = await service.process_pending_documents(limit=5)
    updated = repository.get_by_id(document.id)
    assert updated is not None

    assert summary.enriched == 1
    assert summary.failed == 0
    assert storage.calls == 0
    assert updated.enrichment_method == "pass_through"
    assert updated.enriched_storage_key == "clinvar/raw/record-1.json"


@pytest.mark.asyncio
async def test_pass_through_uses_inline_key_when_raw_storage_key_missing() -> None:
    document = _build_document(source_type=SourceType.CLINVAR)
    repository = StubSourceDocumentRepository([document])
    storage = StubStorageCoordinator()
    service = ContentEnrichmentService(
        dependencies=ContentEnrichmentServiceDependencies(
            content_enrichment_agent=None,
            source_document_repository=repository,
            storage_coordinator=storage,
        ),
    )

    summary = await service.process_pending_documents(limit=5)
    updated = repository.get_by_id(document.id)
    assert updated is not None

    assert summary.enriched == 1
    assert summary.failed == 0
    assert storage.calls == 0
    assert updated.enrichment_method == "pass_through"
    assert updated.enriched_storage_key is not None
    assert updated.enriched_storage_key.startswith("inline://documents/")


@pytest.mark.asyncio
async def test_process_document_uses_agent_and_storage_for_pubmed() -> None:
    document = _build_document(source_type=SourceType.PUBMED)
    repository = StubSourceDocumentRepository([document])
    agent = StubEnrichmentAgent(_build_agent_contract(document.id))
    storage = StubStorageCoordinator()
    service = ContentEnrichmentService(
        dependencies=ContentEnrichmentServiceDependencies(
            content_enrichment_agent=agent,
            source_document_repository=repository,
            storage_coordinator=storage,
        ),
    )

    outcome = await service.process_document(document_id=document.id)
    updated = repository.get_by_id(document.id)
    assert updated is not None

    assert outcome.status == "enriched"
    assert outcome.acquisition_method == "pmc_oa"
    assert storage.calls == 1
    assert updated.enrichment_status == EnrichmentStatus.ENRICHED
    assert updated.enrichment_method == "pmc_oa"
    assert updated.enriched_storage_key is not None
    assert updated.content_length_chars == 19


@pytest.mark.asyncio
async def test_process_document_marks_skipped_when_agent_skips() -> None:
    document = _build_document(source_type=SourceType.PUBMED)
    repository = StubSourceDocumentRepository([document])
    agent = StubEnrichmentAgent(
        ContentEnrichmentContract(
            decision="skipped",
            confidence_score=0.5,
            rationale="No open-access full text available.",
            evidence=[],
            document_id=str(document.id),
            source_type="pubmed",
            acquisition_method="skipped",
            content_format="text",
            content_length_chars=0,
            warning="No enrichment path available",
        ),
    )
    service = ContentEnrichmentService(
        dependencies=ContentEnrichmentServiceDependencies(
            content_enrichment_agent=agent,
            source_document_repository=repository,
            storage_coordinator=None,
        ),
    )

    outcome = await service.process_document(document_id=document.id)
    updated = repository.get_by_id(document.id)
    assert updated is not None

    assert outcome.status == "skipped"
    assert updated.enrichment_status == EnrichmentStatus.SKIPPED
    assert updated.enrichment_method == "skipped"


@pytest.mark.asyncio
async def test_process_document_marks_failed_when_agent_raises() -> None:
    document = _build_document(source_type=SourceType.PUBMED)
    repository = StubSourceDocumentRepository([document])
    agent = StubEnrichmentAgent(contract=None)
    service = ContentEnrichmentService(
        dependencies=ContentEnrichmentServiceDependencies(
            content_enrichment_agent=agent,
            source_document_repository=repository,
            storage_coordinator=None,
        ),
    )

    outcome = await service.process_document(document_id=document.id)
    updated = repository.get_by_id(document.id)
    assert updated is not None

    assert outcome.status == "failed"
    assert updated.enrichment_status == EnrichmentStatus.FAILED
