"""Application service for running publication extraction jobs."""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.application.services.ports.extraction_processor_port import (
    ExtractionProcessorPort,
    ExtractionProcessorResult,
    ExtractionTextPayload,
)
from src.domain.entities.publication_extraction import (
    ExtractionOutcome,
    ExtractionTextSource,
    PublicationExtraction,
)
from src.type_definitions.storage import StorageUseCase

if TYPE_CHECKING:
    from src.application.services.storage_operation_coordinator import (
        StorageOperationCoordinator,
    )
    from src.domain.entities import ExtractionQueueItem, Publication
    from src.domain.repositories import (
        ExtractionQueueRepository,
        PublicationExtractionRepository,
        PublicationRepository,
    )
    from src.type_definitions.common import JSONObject, PublicationExtractionUpdate


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractionRunSummary:
    source_id: UUID | None
    ingestion_job_id: UUID | None
    requested: int
    processed: int
    completed: int
    skipped: int
    failed: int
    started_at: datetime
    completed_at: datetime

    def to_metadata(self) -> JSONObject:
        return {
            "source_id": str(self.source_id) if self.source_id else None,
            "ingestion_job_id": (
                str(self.ingestion_job_id) if self.ingestion_job_id else None
            ),
            "requested": self.requested,
            "processed": self.processed,
            "completed": self.completed,
            "skipped": self.skipped,
            "failed": self.failed,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "completed_at": self.completed_at.isoformat(timespec="seconds"),
        }


class ExtractionRunnerService:
    """Claims pending extraction queue items and processes them."""

    def __init__(  # noqa: PLR0913 - explicit dependencies keep orchestration clear
        self,
        *,
        queue_repository: ExtractionQueueRepository,
        publication_repository: PublicationRepository,
        extraction_repository: PublicationExtractionRepository,
        processor: ExtractionProcessorPort,
        storage_coordinator: StorageOperationCoordinator | None = None,
        batch_size: int = 25,
    ) -> None:
        self._queue_repository = queue_repository
        self._publication_repository = publication_repository
        self._extraction_repository = extraction_repository
        self._processor = processor
        self._storage_coordinator = storage_coordinator
        self._batch_size = max(batch_size, 1)

    async def run_for_ingestion_job(
        self,
        *,
        source_id: UUID,
        ingestion_job_id: UUID,
        expected_items: int,
        batch_size: int | None = None,
    ) -> ExtractionRunSummary:
        started_at = datetime.now(UTC)
        processed = 0
        completed = 0
        skipped = 0
        failed = 0
        batch_limit = batch_size or self._batch_size

        while True:
            batch = await self._run_batch(
                limit=batch_limit,
                source_id=source_id,
                ingestion_job_id=ingestion_job_id,
            )
            processed += batch.processed
            completed += batch.completed
            skipped += batch.skipped
            failed += batch.failed

            if batch.processed == 0:
                break
            if processed >= expected_items:
                break

        completed_at = datetime.now(UTC)
        return ExtractionRunSummary(
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
            requested=expected_items,
            processed=processed,
            completed=completed,
            skipped=skipped,
            failed=failed,
            started_at=started_at,
            completed_at=completed_at,
        )

    async def run_pending(
        self,
        *,
        limit: int | None = None,
        source_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
    ) -> ExtractionRunSummary:
        started_at = datetime.now(UTC)
        batch = await self._run_batch(
            limit=limit or self._batch_size,
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
        )
        completed_at = datetime.now(UTC)
        return ExtractionRunSummary(
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
            requested=batch.processed,
            processed=batch.processed,
            completed=batch.completed,
            skipped=batch.skipped,
            failed=batch.failed,
            started_at=started_at,
            completed_at=completed_at,
        )

    async def _run_batch(
        self,
        *,
        limit: int,
        source_id: UUID | None,
        ingestion_job_id: UUID | None,
    ) -> _BatchSummary:
        items = self._queue_repository.claim_pending(
            limit=limit,
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
        )
        if not items:
            return _BatchSummary()

        completed = 0
        skipped = 0
        failed = 0

        for item in items:
            publication = self._publication_repository.get_by_id(item.publication_id)
            text_payload = self._build_text_payload(publication)
            if text_payload is not None:
                text_payload = await self._store_text_payload(
                    item=item,
                    publication=publication,
                    payload=text_payload,
                )
            try:
                result = self._processor.extract_publication(
                    queue_item=item,
                    publication=publication,
                    text_payload=text_payload,
                )
            except Exception as exc:  # pragma: no cover - defensive
                failed += 1
                self._queue_repository.mark_failed(
                    item.id,
                    error_message=str(exc),
                )
                logger.exception(
                    "Extraction processor failed for item %s",
                    item.id,
                )
                continue

            failed_increment = self._handle_result(
                item=item,
                publication=publication,
                result=result,
            )
            if failed_increment:
                failed += 1
            elif result.status == "skipped":
                skipped += 1
            else:
                completed += 1

        return _BatchSummary(
            processed=len(items),
            completed=completed,
            skipped=skipped,
            failed=failed,
        )

    def _build_text_payload(
        self,
        publication: Publication | None,
    ) -> ExtractionTextPayload | None:
        if publication is None:
            return None
        title = publication.title.strip() if publication.title else ""
        abstract = publication.abstract.strip() if publication.abstract else ""
        if title and abstract:
            return ExtractionTextPayload(
                text=f"{title} {abstract}",
                text_source="title_abstract",
            )
        if title:
            return ExtractionTextPayload(text=title, text_source="title")
        if abstract:
            return ExtractionTextPayload(text=abstract, text_source="abstract")
        return None

    async def _store_text_payload(
        self,
        *,
        item: ExtractionQueueItem,
        publication: Publication | None,
        payload: ExtractionTextPayload,
    ) -> ExtractionTextPayload:
        if payload.document_reference or self._storage_coordinator is None:
            return payload

        key = self._build_storage_key(
            item=item,
            publication=publication,
            payload=payload,
        )
        metadata = self._build_storage_metadata(
            item=item,
            publication=publication,
            payload=payload,
        )
        temp_path = self._write_text_payload(payload.text)
        try:
            record = await self._storage_coordinator.store_for_use_case(
                StorageUseCase.RAW_SOURCE,
                key=key,
                file_path=temp_path,
                content_type="text/plain",
                user_id=None,
                metadata=metadata,
            )
        except Exception:  # pragma: no cover - defensive logging
            logger.exception(
                "Failed to store extraction text for queue item %s",
                item.id,
            )
            return payload
        finally:
            temp_path.unlink(missing_ok=True)
        return replace(payload, document_reference=record.key)

    @staticmethod
    def _write_text_payload(text: str) -> Path:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(text)
            return Path(tmp.name)

    @staticmethod
    def _build_storage_key(
        *,
        item: ExtractionQueueItem,
        publication: Publication | None,
        payload: ExtractionTextPayload,
    ) -> str:
        identifier = (
            publication.identifier.pubmed_id
            if publication and publication.identifier.pubmed_id
            else str(item.publication_id)
        )
        return (
            "extractions/"
            f"{item.source_id}/"
            f"{item.ingestion_job_id}/"
            f"{identifier}/"
            f"v{item.extraction_version}/"
            f"{item.id}_{payload.text_source}.txt"
        )

    @staticmethod
    def _build_storage_metadata(
        *,
        item: ExtractionQueueItem,
        publication: Publication | None,
        payload: ExtractionTextPayload,
    ) -> JSONObject:
        metadata: JSONObject = {
            "queue_item_id": str(item.id),
            "source_id": str(item.source_id),
            "ingestion_job_id": str(item.ingestion_job_id),
            "publication_id": item.publication_id,
            "extraction_version": item.extraction_version,
            "text_source": payload.text_source,
        }
        if publication is not None:
            metadata.update(
                {
                    "pubmed_id": publication.identifier.pubmed_id,
                    "pmc_id": publication.identifier.pmc_id,
                    "doi": publication.identifier.doi,
                },
            )
        return metadata

    def _handle_result(
        self,
        *,
        item: ExtractionQueueItem,
        publication: Publication | None,
        result: ExtractionProcessorResult,
    ) -> bool:
        try:
            extraction_record = self._persist_extraction(
                item=item,
                publication=publication,
                result=result,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._queue_repository.mark_failed(
                item.id,
                error_message=str(exc),
            )
            logger.exception(
                "Failed to persist extraction record for queue item %s",
                item.id,
            )
            return True

        if result.status == "failed":
            error_message = result.error_message or "extraction_failed"
            self._queue_repository.mark_failed(
                item.id,
                error_message=error_message,
            )
            return True

        metadata = self._build_metadata(
            item=item,
            publication=publication,
            result=result,
            extraction_id=extraction_record.id,
        )
        self._queue_repository.mark_completed(
            item.id,
            metadata=metadata,
        )
        return False

    def _build_metadata(
        self,
        *,
        item: ExtractionQueueItem,
        publication: Publication | None,
        result: ExtractionProcessorResult,
        extraction_id: UUID,
    ) -> JSONObject:
        payload: JSONObject = dict(result.metadata)
        payload["extraction_outcome"] = result.status
        payload["extraction_version"] = item.extraction_version
        payload["extracted_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        payload["extraction_id"] = str(extraction_id)
        payload["text_source"] = result.text_source
        payload["document_reference"] = result.document_reference

        if publication is not None:
            if publication.id is not None:
                payload["publication_id"] = publication.id
            payload["publication_title"] = publication.title
            payload["pubmed_id"] = publication.identifier.pubmed_id
            payload["pmc_id"] = publication.identifier.pmc_id
            payload["doi"] = publication.identifier.doi

        return payload

    def _persist_extraction(
        self,
        *,
        item: ExtractionQueueItem,
        publication: Publication | None,
        result: ExtractionProcessorResult,
    ) -> PublicationExtraction:
        now = datetime.now(UTC)
        outcome = ExtractionOutcome(result.status)
        text_source = ExtractionTextSource(result.text_source)
        pubmed_id = publication.identifier.pubmed_id if publication else None

        existing = self._extraction_repository.find_by_queue_item_id(item.id)
        if existing is not None:
            updates: PublicationExtractionUpdate = {
                "status": outcome.value,
                "facts": list(result.facts),
                "metadata": dict(result.metadata),
                "extracted_at": now,
                "processor_name": result.processor_name,
                "processor_version": result.processor_version,
                "text_source": text_source.value,
                "document_reference": result.document_reference,
            }
            return self._extraction_repository.update(existing.id, updates)

        extraction = PublicationExtraction(
            id=uuid4(),
            publication_id=item.publication_id,
            pubmed_id=pubmed_id,
            source_id=item.source_id,
            ingestion_job_id=item.ingestion_job_id,
            queue_item_id=item.id,
            status=outcome,
            extraction_version=item.extraction_version,
            processor_name=result.processor_name,
            processor_version=result.processor_version,
            text_source=text_source,
            document_reference=result.document_reference,
            facts=list(result.facts),
            metadata=dict(result.metadata),
            extracted_at=now,
            created_at=now,
            updated_at=now,
        )
        return self._extraction_repository.create(extraction)


@dataclass(frozen=True)
class _BatchSummary:
    processed: int = 0
    completed: int = 0
    skipped: int = 0
    failed: int = 0


__all__ = ["ExtractionRunSummary", "ExtractionRunnerService"]
