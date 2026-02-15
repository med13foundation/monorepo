"""Application service for Tier-2 content-enrichment orchestration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from src.application.agents.services._content_enrichment_helpers import (
    PASS_THROUGH_SOURCE_TYPES,
    StorageResult,
    build_content_enrichment_context,
    build_metadata_patch,
    compute_character_count,
    extract_structured_payload,
    infer_storage_format,
    merge_metadata,
    resolve_run_id,
    serialize_contract_payload,
    try_parse_uuid,
    write_temp_payload,
)
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.content_enrichment import ContentEnrichmentContract
from src.domain.entities.source_document import EnrichmentStatus, SourceDocument
from src.type_definitions.storage import StorageUseCase

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services.storage_operation_coordinator import (
        StorageOperationCoordinator,
    )
    from src.domain.agents.ports.content_enrichment_port import ContentEnrichmentPort
    from src.domain.repositories.source_document_repository import (
        SourceDocumentRepository,
    )
    from src.type_definitions.common import JSONObject


@dataclass(frozen=True)
class ContentEnrichmentServiceDependencies:
    source_document_repository: SourceDocumentRepository
    content_enrichment_agent: ContentEnrichmentPort | None = None
    storage_coordinator: StorageOperationCoordinator | None = None


@dataclass(frozen=True)
class ContentEnrichmentDocumentOutcome:
    document_id: UUID
    status: Literal["enriched", "skipped", "failed"]
    execution_mode: Literal["ai", "deterministic"]
    reason: str
    acquisition_method: str | None = None
    content_storage_key: str | None = None
    content_length_chars: int = 0
    run_id: str | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContentEnrichmentRunSummary:
    requested: int
    processed: int
    enriched: int
    skipped: int
    failed: int
    ai_runs: int
    deterministic_runs: int
    errors: tuple[str, ...]
    started_at: datetime
    completed_at: datetime


class ContentEnrichmentService:
    def __init__(
        self,
        dependencies: ContentEnrichmentServiceDependencies,
    ) -> None:
        self._agent = dependencies.content_enrichment_agent
        self._source_documents = dependencies.source_document_repository
        self._storage_coordinator = dependencies.storage_coordinator

    async def process_pending_documents(  # noqa: PLR0913
        self,
        *,
        limit: int = 25,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        source_type: str | None = None,
        model_id: str | None = None,
        pipeline_run_id: str | None = None,
    ) -> ContentEnrichmentRunSummary:
        started_at = datetime.now(UTC)
        pending_documents = self._source_documents.list_pending_enrichment(
            limit=max(limit, 1),
            source_id=source_id,
            research_space_id=research_space_id,
        )
        normalized_source_type = (
            source_type.strip().lower() if isinstance(source_type, str) else None
        )
        if normalized_source_type:
            pending_documents = [
                document
                for document in pending_documents
                if document.source_type.value.strip().lower() == normalized_source_type
            ]

        outcomes = [
            await self._process_document(
                document=document,
                model_id=model_id,
                force=False,
                pipeline_run_id=pipeline_run_id,
            )
            for document in pending_documents
        ]

        completed_at = datetime.now(UTC)
        return self._build_run_summary(
            outcomes=outcomes,
            requested=len(pending_documents),
            started_at=started_at,
            completed_at=completed_at,
        )

    async def process_document(
        self,
        *,
        document_id: UUID,
        model_id: str | None = None,
        force: bool = False,
    ) -> ContentEnrichmentDocumentOutcome:
        document = self._source_documents.get_by_id(document_id)
        if document is None:
            msg = f"Source document not found: {document_id}"
            raise LookupError(msg)
        return await self._process_document(
            document=document,
            model_id=model_id,
            force=force,
            pipeline_run_id=None,
        )

    async def close(self) -> None:
        if self._agent is not None:
            await self._agent.close()

    async def _process_document(
        self,
        *,
        document: SourceDocument,
        model_id: str | None,
        force: bool,
        pipeline_run_id: str | None,
    ) -> ContentEnrichmentDocumentOutcome:
        execution_mode = self._resolve_execution_mode(document=document)
        if not force and document.enrichment_status != EnrichmentStatus.PENDING:
            return ContentEnrichmentDocumentOutcome(
                document_id=document.id,
                status="skipped",
                execution_mode=execution_mode,
                reason=f"document_status={document.enrichment_status.value}",
            )

        try:
            contract = await self._build_contract(document=document, model_id=model_id)
        except Exception as exc:  # noqa: BLE001
            failure_reason = "agent_execution_failed"
            self._persist_document_with_status(
                document=document,
                status=EnrichmentStatus.FAILED,
                run_uuid=None,
                acquisition_method="skipped",
                metadata_patch={
                    "content_enrichment_error": str(exc),
                    "content_enrichment_failure_reason": failure_reason,
                    "pipeline_run_id": pipeline_run_id,
                },
            )
            return ContentEnrichmentDocumentOutcome(
                document_id=document.id,
                status="failed",
                execution_mode=execution_mode,
                reason=failure_reason,
                errors=(str(exc),),
            )

        run_id = resolve_run_id(contract)
        run_uuid = try_parse_uuid(run_id)

        if contract.decision == "skipped":
            self._persist_document_with_status(
                document=document,
                status=EnrichmentStatus.SKIPPED,
                run_uuid=run_uuid,
                acquisition_method=contract.acquisition_method,
                metadata_patch=build_metadata_patch(
                    contract=contract,
                    run_id=run_id,
                    pipeline_run_id=pipeline_run_id,
                    reason="skipped",
                    content_storage_key=None,
                    content_hash=None,
                ),
            )
            return ContentEnrichmentDocumentOutcome(
                document_id=document.id,
                status="skipped",
                execution_mode=execution_mode,
                reason="skipped",
                acquisition_method=contract.acquisition_method,
                run_id=run_id,
            )

        if contract.decision == "failed":
            self._persist_document_with_status(
                document=document,
                status=EnrichmentStatus.FAILED,
                run_uuid=run_uuid,
                acquisition_method=contract.acquisition_method,
                metadata_patch=build_metadata_patch(
                    contract=contract,
                    run_id=run_id,
                    pipeline_run_id=pipeline_run_id,
                    reason="failed",
                    content_storage_key=None,
                    content_hash=None,
                ),
            )
            return ContentEnrichmentDocumentOutcome(
                document_id=document.id,
                status="failed",
                execution_mode=execution_mode,
                reason="failed",
                acquisition_method=contract.acquisition_method,
                run_id=run_id,
                errors=(contract.warning,) if contract.warning else (),
            )

        storage_result = await self._resolve_content_storage(
            document=document,
            contract=contract,
            run_id=run_id,
            pipeline_run_id=pipeline_run_id,
        )
        if storage_result is None:
            failure_reason = "missing_enriched_content"
            self._persist_document_with_status(
                document=document,
                status=EnrichmentStatus.FAILED,
                run_uuid=run_uuid,
                acquisition_method=contract.acquisition_method,
                metadata_patch=build_metadata_patch(
                    contract=contract,
                    run_id=run_id,
                    pipeline_run_id=pipeline_run_id,
                    reason=failure_reason,
                    content_storage_key=None,
                    content_hash=None,
                ),
            )
            return ContentEnrichmentDocumentOutcome(
                document_id=document.id,
                status="failed",
                execution_mode=execution_mode,
                reason=failure_reason,
                acquisition_method=contract.acquisition_method,
                run_id=run_id,
                errors=(failure_reason,),
            )

        updated = document.mark_enriched(
            enriched_storage_key=storage_result.storage_key,
            content_hash=storage_result.content_hash,
            content_length_chars=storage_result.content_length_chars,
            enrichment_method=contract.acquisition_method,
            enrichment_agent_run_id=run_uuid,
            enriched_at=datetime.now(UTC),
        )
        self._source_documents.upsert(
            updated.model_copy(
                update={
                    "metadata": merge_metadata(
                        updated.metadata,
                        build_metadata_patch(
                            contract=contract,
                            run_id=run_id,
                            pipeline_run_id=pipeline_run_id,
                            reason="enriched",
                            content_storage_key=storage_result.storage_key,
                            content_hash=storage_result.content_hash,
                        ),
                    ),
                },
            ),
        )

        return ContentEnrichmentDocumentOutcome(
            document_id=document.id,
            status="enriched",
            execution_mode=execution_mode,
            reason="enriched",
            acquisition_method=contract.acquisition_method,
            content_storage_key=storage_result.storage_key,
            content_length_chars=storage_result.content_length_chars,
            run_id=run_id,
            errors=(contract.warning,) if contract.warning else (),
        )

    async def _build_contract(
        self,
        *,
        document: SourceDocument,
        model_id: str | None,
    ) -> ContentEnrichmentContract:
        if document.source_type in PASS_THROUGH_SOURCE_TYPES:
            return self._build_pass_through_contract(document=document)
        if self._agent is None:
            return ContentEnrichmentContract(
                decision="skipped",
                confidence_score=1.0,
                rationale=(
                    "Content-enrichment agent is disabled "
                    "(MED13_ENABLE_CONTENT_ENRICHMENT_AGENT != 1)."
                ),
                evidence=[
                    EvidenceItem(
                        source_type="note",
                        locator=f"document:{document.id}",
                        excerpt="Tier-2 agent execution skipped by configuration flag.",
                        relevance=1.0,
                    ),
                ],
                document_id=str(document.id),
                source_type=document.source_type.value,
                acquisition_method="skipped",
                content_format="text",
                content_length_chars=0,
                warning="Content-enrichment agent is disabled by configuration.",
                agent_run_id=None,
            )
        context = build_content_enrichment_context(document)
        return await self._agent.enrich(context, model_id=model_id)

    def _resolve_execution_mode(
        self,
        *,
        document: SourceDocument,
    ) -> Literal["ai", "deterministic"]:
        if document.source_type in PASS_THROUGH_SOURCE_TYPES:
            return "deterministic"
        if self._agent is None:
            return "deterministic"
        return "ai"

    @staticmethod
    def _build_pass_through_contract(
        *,
        document: SourceDocument,
    ) -> ContentEnrichmentContract:
        payload = extract_structured_payload(document.metadata)
        serialized = json.dumps(payload, default=str)
        return ContentEnrichmentContract(
            decision="enriched",
            confidence_score=0.98,
            rationale="Structured source type uses deterministic pass-through enrichment.",
            evidence=[
                EvidenceItem(
                    source_type="db",
                    locator=f"document:{document.id}",
                    excerpt="Structured payload copied to enriched document content.",
                    relevance=0.98,
                ),
            ],
            document_id=str(document.id),
            source_type=document.source_type.value,
            acquisition_method="pass_through",
            content_format="structured_json",
            content_length_chars=len(serialized),
            content_payload=payload,
            agent_run_id=None,
        )

    async def _resolve_content_storage(
        self,
        *,
        document: SourceDocument,
        contract: ContentEnrichmentContract,
        run_id: str | None,
        pipeline_run_id: str | None,
    ) -> StorageResult | None:
        if contract.content_storage_key is not None:
            payload = serialize_contract_payload(contract)
            content_hash = (
                hashlib.sha256(payload).hexdigest() if payload is not None else None
            )
            length = contract.content_length_chars
            if payload is not None and length <= 0:
                length = compute_character_count(contract, payload)
            return StorageResult(
                storage_key=contract.content_storage_key,
                content_hash=content_hash,
                content_length_chars=max(length, 0),
            )

        payload = serialize_contract_payload(contract)
        if payload is None:
            if (
                contract.acquisition_method == "pass_through"
                and document.raw_storage_key is not None
            ):
                return StorageResult(
                    storage_key=document.raw_storage_key,
                    content_hash=None,
                    content_length_chars=max(contract.content_length_chars, 0),
                )
            return None

        content_hash = hashlib.sha256(payload).hexdigest()
        if self._storage_coordinator is None:
            if (
                contract.acquisition_method == "pass_through"
                and document.raw_storage_key is not None
            ):
                return StorageResult(
                    storage_key=document.raw_storage_key,
                    content_hash=content_hash,
                    content_length_chars=compute_character_count(
                        contract,
                        payload,
                    ),
                )
            return None

        extension, content_type = infer_storage_format(contract.content_format)
        key = f"documents/{document.id}/enriched/{content_hash}.{extension}"
        metadata: JSONObject = {
            "document_id": str(document.id),
            "source_id": str(document.source_id),
            "source_type": document.source_type.value,
            "external_record_id": document.external_record_id,
            "acquisition_method": contract.acquisition_method,
            "content_format": contract.content_format,
        }
        if run_id is not None:
            metadata["enrichment_run_id"] = run_id
        if pipeline_run_id is not None and pipeline_run_id.strip():
            metadata["pipeline_run_id"] = pipeline_run_id.strip()

        temp_path = write_temp_payload(payload, suffix=f".{extension}")
        try:
            record = await self._storage_coordinator.store_for_use_case(
                StorageUseCase.DOCUMENT_CONTENT,
                key=key,
                file_path=temp_path,
                content_type=content_type,
                user_id=None,
                metadata=metadata,
            )
        finally:
            temp_path.unlink(missing_ok=True)

        return StorageResult(
            storage_key=record.key,
            content_hash=content_hash,
            content_length_chars=compute_character_count(contract, payload),
        )

    def _persist_document_with_status(
        self,
        *,
        document: SourceDocument,
        status: EnrichmentStatus,
        run_uuid: UUID | None,
        acquisition_method: str,
        metadata_patch: JSONObject,
    ) -> None:
        updated = document.model_copy(
            update={
                "enrichment_status": status,
                "enrichment_method": acquisition_method,
                "enrichment_agent_run_id": run_uuid,
                "updated_at": datetime.now(UTC),
                "metadata": merge_metadata(document.metadata, metadata_patch),
            },
        )
        self._source_documents.upsert(updated)

    @staticmethod
    def _build_run_summary(
        *,
        outcomes: list[ContentEnrichmentDocumentOutcome],
        requested: int,
        started_at: datetime,
        completed_at: datetime,
    ) -> ContentEnrichmentRunSummary:
        errors: list[str] = []
        enriched = 0
        skipped = 0
        failed = 0
        ai_runs = 0
        deterministic_runs = 0
        for outcome in outcomes:
            if outcome.status == "enriched":
                enriched += 1
            elif outcome.status == "skipped":
                skipped += 1
            elif outcome.status == "failed":
                failed += 1
            if outcome.execution_mode == "ai":
                ai_runs += 1
            else:
                deterministic_runs += 1
            errors.extend(error for error in outcome.errors if error)
        return ContentEnrichmentRunSummary(
            requested=requested,
            processed=len(outcomes),
            enriched=enriched,
            skipped=skipped,
            failed=failed,
            ai_runs=ai_runs,
            deterministic_runs=deterministic_runs,
            errors=tuple(dict.fromkeys(errors)),
            started_at=started_at,
            completed_at=completed_at,
        )


__all__ = [
    "ContentEnrichmentDocumentOutcome",
    "ContentEnrichmentRunSummary",
    "ContentEnrichmentService",
    "ContentEnrichmentServiceDependencies",
]
