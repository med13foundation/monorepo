"""Helper mixin for PubMed ingestion orchestration details."""

# mypy: disable-error-code="misc"

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from src.domain.entities import source_document
from src.domain.entities.source_record_ledger import SourceRecordLedgerEntry
from src.domain.services import pubmed_ingestion
from src.domain.services.ingestion import IngestionExtractionTarget
from src.type_definitions.ingestion import RawRecord as IngestionRawRecord
from src.type_definitions.storage import StorageUseCase

if TYPE_CHECKING:
    from src.application.services.pubmed_ingestion_service import (
        PubMedIngestionService,
    )
    from src.domain.entities import data_source_configs, user_data_source
    from src.domain.services.ingestion import IngestionRunContext
    from src.type_definitions.common import JSONObject


logger = logging.getLogger(__name__)
LOW_CONFIDENCE_THRESHOLD = 0.5


@dataclass(frozen=True)
class _LedgerDedupOutcome:
    """Result of applying record-ledger deduplication to fetched records."""

    filtered_records: list[JSONObject]
    entries_to_upsert: list[SourceRecordLedgerEntry]
    new_records: int
    updated_records: int
    unchanged_records: int


@dataclass(frozen=True)
class _QueryResolution:
    """Resolved query configuration and AI generation metadata."""

    config: data_source_configs.PubMedQueryConfig
    query_generation_decision: str
    query_generation_confidence: float
    query_generation_run_id: str | None
    query_generation_execution_mode: str
    query_generation_fallback_reason: str | None


class PubMedIngestionServiceHelpers:
    """Private helpers for PubMed ingestion orchestration."""

    def _build_extraction_targets(
        self: PubMedIngestionService,
        records: list[JSONObject],
        *,
        source_type: user_data_source.SourceType,
    ) -> tuple[IngestionExtractionTarget, ...]:
        targets: list[IngestionExtractionTarget] = []
        seen_source_record_ids: set[str] = set()
        for record in records:
            source_record_id = self._extract_external_record_id(record)
            if source_record_id in seen_source_record_ids:
                continue
            seen_source_record_ids.add(source_record_id)
            metadata_payload: JSONObject = {
                "raw_record": dict(record),
                "source_record_id": source_record_id,
                "source_type": source_type.value,
            }
            targets.append(
                IngestionExtractionTarget(
                    source_record_id=source_record_id,
                    source_type=source_type.value,
                    publication_id=None,
                    pubmed_id=self._extract_pubmed_id(record),
                    metadata=metadata_payload,
                ),
            )
        return tuple(targets)

    @staticmethod
    def _extract_pubmed_id(record: JSONObject) -> str | None:
        for key in ("pmid", "pubmed_id"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int):
                return str(value)
        return None

    async def _resolve_query_configuration(
        self: PubMedIngestionService,
        *,
        source: user_data_source.UserDataSource,
        config: data_source_configs.PubMedQueryConfig,
    ) -> _QueryResolution:
        """Resolve AI-managed query overrides and associated metadata."""
        from .query_generation_service import QueryGenerationRequest

        request: QueryGenerationRequest = QueryGenerationRequest(
            base_query=config.query,
            source_type=config.agent_config.query_agent_source_type,
            is_ai_managed=config.agent_config.is_ai_managed,
            agent_prompt=config.agent_config.agent_prompt,
            model_id=config.agent_config.model_id,
            use_research_space_context=config.agent_config.use_research_space_context,
            research_space_id=source.research_space_id,
        )
        result = await self._query_generation_service.resolve_query(request)

        resolved_query = config.query
        if result.query.strip() and result.query.strip() != config.query:
            resolved_query = result.query.strip()
        resolved_query = self._apply_pinned_pubmed_filter(
            query=resolved_query,
            pinned_pubmed_id=config.pinned_pubmed_id,
        )
        resolved_config = config.model_copy(update={"query": resolved_query})

        if result.decision == "escalate":
            logger.warning(
                "AI query generation escalated: %s (confidence=%.2f)",
                "agent requested escalation",
                result.confidence,
            )
        elif (
            result.execution_mode == "ai"
            and result.confidence < LOW_CONFIDENCE_THRESHOLD
        ):
            logger.warning(
                "Low confidence AI query (%.2f): %s",
                result.confidence,
                result.decision,
            )

        return _QueryResolution(
            config=resolved_config,
            query_generation_decision=result.decision,
            query_generation_confidence=result.confidence,
            query_generation_run_id=result.run_id,
            query_generation_execution_mode=result.execution_mode,
            query_generation_fallback_reason=result.fallback_reason,
        )

    @staticmethod
    def _apply_pinned_pubmed_filter(
        *,
        query: str,
        pinned_pubmed_id: str | None,
    ) -> str:
        if pinned_pubmed_id is None:
            return query
        normalized_pmid = pinned_pubmed_id.strip()
        if not normalized_pmid:
            return query
        pmid_filter = f"{normalized_pmid}[PMID]"
        lowered_query = query.casefold()
        if pmid_filter.casefold() in lowered_query:
            return query
        return f"(({query})) AND ({pmid_filter})"

    async def _fetch_records_with_checkpoint(
        self: PubMedIngestionService,
        *,
        config: data_source_configs.PubMedQueryConfig,
        checkpoint_before: JSONObject | None,
    ) -> pubmed_ingestion.PubMedGatewayFetchResult:
        checkpoint_for_fetch = checkpoint_before
        if isinstance(config.pinned_pubmed_id, str) and config.pinned_pubmed_id.strip():
            checkpoint_for_fetch = None
        if isinstance(self._gateway, pubmed_ingestion.PubMedIncrementalGateway):
            return await self._gateway.fetch_records_incremental(
                config,
                checkpoint=checkpoint_for_fetch,
            )

        records = await self._gateway.fetch_records(config)
        return pubmed_ingestion.PubMedGatewayFetchResult(
            records=records,
            fetched_records=len(records),
            checkpoint_after=None,
        )

    @staticmethod
    def _build_fallback_checkpoint(
        *,
        fetched_records: int,
        processed_records: int,
    ) -> JSONObject:
        checkpoint_after: JSONObject = {
            "last_processed_at": datetime.now(UTC).isoformat(),
            "fetched_records": fetched_records,
            "processed_records": processed_records,
        }
        return checkpoint_after

    def _to_pipeline_records(
        self: PubMedIngestionService,
        records: list[JSONObject],
        *,
        original_source_id: str,
    ) -> list[IngestionRawRecord]:
        raw_records: list[IngestionRawRecord] = []
        for record in records:
            pmid = record.get("pmid")
            record_id = pmid if isinstance(pmid, str) and pmid.strip() else str(uuid4())

            raw_records.append(
                IngestionRawRecord(
                    source_id=record_id,
                    data=record,
                    metadata={
                        "original_source_id": original_source_id,
                        "type": "pubmed",
                        "entity_type": "PUBLICATION",
                        "pmid": record.get("pmid"),
                        "doi": record.get("doi"),
                    },
                ),
            )
        return raw_records

    def _build_ledger_dedup_outcome(
        self: PubMedIngestionService,
        *,
        source: user_data_source.UserDataSource,
        records: list[JSONObject],
        context: IngestionRunContext | None,
        force_external_record_ids: set[str] | None = None,
    ) -> _LedgerDedupOutcome:
        if context is None or context.source_record_ledger_repository is None:
            return _LedgerDedupOutcome(
                filtered_records=records,
                entries_to_upsert=[],
                new_records=len(records),
                updated_records=0,
                unchanged_records=0,
            )

        ledger_repository = context.source_record_ledger_repository
        record_pairs = [
            (
                record,
                self._extract_external_record_id(record),
                self._compute_payload_hash(record),
            )
            for record in records
        ]
        external_ids = [external_id for _, external_id, _ in record_pairs]
        existing_by_external_id = ledger_repository.get_entries_by_external_ids(
            source_id=source.id,
            external_record_ids=list(dict.fromkeys(external_ids)),
        )

        now = datetime.now(UTC)
        forced_external_ids = force_external_record_ids or set()
        current_entries: dict[str, SourceRecordLedgerEntry] = dict(
            existing_by_external_id,
        )
        filtered_records: list[JSONObject] = []
        entries_to_upsert: list[SourceRecordLedgerEntry] = []
        new_records = 0
        updated_records = 0
        unchanged_records = 0

        for record, external_id, payload_hash in record_pairs:
            existing_entry = current_entries.get(external_id)
            if existing_entry is None:
                new_records += 1
                filtered_records.append(record)
                new_entry = SourceRecordLedgerEntry(
                    source_id=source.id,
                    external_record_id=external_id,
                    payload_hash=payload_hash,
                    source_updated_at=self._extract_source_updated_at(record),
                    first_seen_job_id=context.ingestion_job_id,
                    last_seen_job_id=context.ingestion_job_id,
                    last_changed_job_id=context.ingestion_job_id,
                    last_processed_at=now,
                    created_at=now,
                    updated_at=now,
                )
                entries_to_upsert.append(new_entry)
                current_entries[external_id] = new_entry
                continue

            updated_entry = existing_entry.mark_seen(
                payload_hash=payload_hash,
                seen_job_id=context.ingestion_job_id,
                source_updated_at=self._extract_source_updated_at(record),
                seen_at=now,
            )
            entries_to_upsert.append(updated_entry)
            current_entries[external_id] = updated_entry
            payload_changed = existing_entry.payload_hash != payload_hash
            force_process = external_id in forced_external_ids
            if not payload_changed and not force_process:
                unchanged_records += 1
                continue
            updated_records += 1
            filtered_records.append(record)

        return _LedgerDedupOutcome(
            filtered_records=filtered_records,
            entries_to_upsert=entries_to_upsert,
            new_records=new_records,
            updated_records=updated_records,
            unchanged_records=unchanged_records,
        )

    @staticmethod
    def _extract_external_record_id(record: JSONObject) -> str:
        for key in ("pmid", "pubmed_id", "doi"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                normalized = value.strip()
                if key == "doi":
                    normalized = normalized.lower()
                return f"pubmed:{key}:{normalized}"
            if isinstance(value, int):
                return f"pubmed:{key}:{value}"

        payload_hash = PubMedIngestionServiceHelpers._compute_payload_hash(record)
        return f"pubmed:hash:{payload_hash}"

    @staticmethod
    def _compute_payload_hash(record: JSONObject) -> str:
        serialized = json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_source_updated_at(record: JSONObject) -> datetime | None:
        for key in ("fetched_at", "updated_at", "last_updated"):
            value = record.get(key)
            if isinstance(value, str):
                try:
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=UTC)
                return parsed
        return None

    @staticmethod
    def _build_query_signature(
        *,
        source_type: user_data_source.SourceType,
        metadata: object,
    ) -> str:
        canonical_payload = json.dumps(
            {
                "source_type": source_type.value,
                "metadata": metadata,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()

    async def _persist_raw_records(
        self: PubMedIngestionService,
        records: list[JSONObject],
        source: user_data_source.UserDataSource,
    ) -> str | None:
        if not self._storage_service:
            return None

        backend = self._storage_service.resolve_backend_for_use_case(
            StorageUseCase.RAW_SOURCE,
        )
        if not backend:
            return None

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(records, tmp, default=str)
            tmp_path = Path(tmp.name)

        try:
            timestamp = source.updated_at.strftime("%Y%m%d_%H%M%S")
            key = f"pubmed/{source.id}/raw/{timestamp}_{uuid4().hex[:8]}.json"

            operation = await self._storage_service.record_store_operation(
                configuration=backend,
                key=key,
                file_path=tmp_path,
                content_type="application/json",
                user_id=source.owner_id,
                metadata={
                    "source_id": str(source.id),
                    "record_count": len(records),
                },
            )
            return operation.key
        finally:
            tmp_path.unlink(missing_ok=True)

    def _upsert_source_documents(
        self: PubMedIngestionService,
        *,
        records: list[JSONObject],
        source: user_data_source.UserDataSource,
        context: IngestionRunContext | None,
        raw_storage_key: str | None,
    ) -> None:
        if self._source_document_repository is None or not records:
            return
        seen_external_ids: set[str] = set()
        documents: list[source_document.SourceDocument] = []
        now = datetime.now(UTC)
        for record in records:
            external_record_id = self._extract_external_record_id(record)
            if external_record_id in seen_external_ids:
                continue
            seen_external_ids.add(external_record_id)
            metadata_payload: JSONObject = {
                "raw_record": dict(record),
            }
            documents.append(
                source_document.SourceDocument(
                    id=uuid4(),
                    research_space_id=source.research_space_id,
                    source_id=source.id,
                    ingestion_job_id=context.ingestion_job_id if context else None,
                    external_record_id=external_record_id,
                    source_type=source.source_type,
                    document_format=source_document.DocumentFormat.MEDLINE_XML,
                    raw_storage_key=raw_storage_key,
                    enrichment_status=source_document.EnrichmentStatus.PENDING,
                    extraction_status=(
                        source_document.DocumentExtractionStatus.PENDING
                    ),
                    metadata=metadata_payload,
                    created_at=now,
                    updated_at=now,
                ),
            )
        if documents:
            self._source_document_repository.upsert_many(documents)
