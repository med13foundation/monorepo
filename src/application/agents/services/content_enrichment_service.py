"""Application service for Tier-2 content-enrichment orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from src.application.agents.services._content_enrichment_contract_helpers import (
    _ContentEnrichmentContractHelpers,
)
from src.application.agents.services._content_enrichment_helpers import (
    PASS_THROUGH_SOURCE_TYPES,
    build_content_enrichment_context,
    build_metadata_patch,
    merge_metadata,
    resolve_run_id,
    try_parse_uuid,
)
from src.application.agents.services._content_enrichment_storage_helpers import (
    _ContentEnrichmentStorageHelpers,
)
from src.application.agents.services._content_enrichment_types import (
    ContentEnrichmentDocumentOutcome,
    ContentEnrichmentRunSummary,
)
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.content_enrichment import ContentEnrichmentContract
from src.domain.entities.source_document import EnrichmentStatus, SourceDocument

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services.storage_operation_coordinator import (
        StorageOperationCoordinator,
    )
    from src.domain.agents.ports.content_enrichment_port import ContentEnrichmentPort
    from src.domain.repositories.source_document_repository import (
        SourceDocumentRepository,
    )


@dataclass(frozen=True)
class ContentEnrichmentServiceDependencies:
    source_document_repository: SourceDocumentRepository
    content_enrichment_agent: ContentEnrichmentPort | None = None
    storage_coordinator: StorageOperationCoordinator | None = None


class ContentEnrichmentService(
    _ContentEnrichmentStorageHelpers,
    _ContentEnrichmentContractHelpers,
):
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
        ingestion_job_id: UUID | None = None,
        research_space_id: UUID | None = None,
        source_type: str | None = None,
        model_id: str | None = None,
        pipeline_run_id: str | None = None,
    ) -> ContentEnrichmentRunSummary:
        started_at = datetime.now(UTC)
        requested_limit = max(limit, 1)
        fetch_limit = requested_limit
        if ingestion_job_id is not None:
            fetch_limit = max(requested_limit * 20, 200)
        pending_documents = self._source_documents.list_pending_enrichment(
            limit=fetch_limit,
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
        if ingestion_job_id is not None:
            pending_documents = [
                document
                for document in pending_documents
                if document.ingestion_job_id == ingestion_job_id
            ]
        pending_documents = sorted(
            pending_documents,
            key=lambda document: document.created_at,
            reverse=True,
        )[:requested_limit]

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

    async def _process_document(  # noqa: PLR0911
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

        full_text_validation_failure = self._validate_required_full_text_contract(
            document=document,
            contract=contract,
        )
        if full_text_validation_failure is not None:
            non_blocking_skip = self._should_treat_full_text_validation_as_skip(
                failure_reason=full_text_validation_failure,
                contract=contract,
            )
            persisted_status = (
                EnrichmentStatus.SKIPPED
                if non_blocking_skip
                else EnrichmentStatus.FAILED
            )
            outcome_status: Literal["skipped", "failed"] = (
                "skipped" if non_blocking_skip else "failed"
            )
            self._persist_document_with_status(
                document=document,
                status=persisted_status,
                run_uuid=run_uuid,
                acquisition_method=contract.acquisition_method,
                metadata_patch=build_metadata_patch(
                    contract=contract,
                    run_id=run_id,
                    pipeline_run_id=pipeline_run_id,
                    reason=full_text_validation_failure,
                    content_storage_key=None,
                    content_hash=None,
                ),
            )
            return ContentEnrichmentDocumentOutcome(
                document_id=document.id,
                status=outcome_status,
                execution_mode=execution_mode,
                reason=full_text_validation_failure,
                acquisition_method=contract.acquisition_method,
                run_id=run_id,
                errors=() if non_blocking_skip else (full_text_validation_failure,),
            )

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
        metadata_patch = build_metadata_patch(
            contract=contract,
            run_id=run_id,
            pipeline_run_id=pipeline_run_id,
            reason="enriched",
            content_storage_key=storage_result.storage_key,
            content_hash=storage_result.content_hash,
        )
        metadata_patch = merge_metadata(
            metadata_patch,
            self._build_extraction_input_patch(
                metadata=updated.metadata,
                contract=contract,
            ),
        )
        self._source_documents.upsert(
            updated.model_copy(
                update={
                    "metadata": merge_metadata(
                        updated.metadata,
                        metadata_patch,
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
            errors=(),
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


__all__ = [
    "ContentEnrichmentDocumentOutcome",
    "ContentEnrichmentRunSummary",
    "ContentEnrichmentService",
    "ContentEnrichmentServiceDependencies",
]
