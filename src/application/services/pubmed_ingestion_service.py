"""Application service for orchestrating PubMed ingestion per data source."""

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

from src.domain.entities import data_source_configs, publication, user_data_source
from src.domain.entities.source_record_ledger import SourceRecordLedgerEntry
from src.domain.entities.source_sync_state import CheckpointKind
from src.domain.services.pubmed_ingestion import (
    PubMedGateway,
    PubMedGatewayFetchResult,
    PubMedIncrementalGateway,
    PubMedIngestionSummary,
)
from src.domain.transform.transformers.pubmed_record_transformer import (
    PubMedRecordTransformer,
)
from src.type_definitions.ingestion import RawRecord as IngestionRawRecord
from src.type_definitions.storage import StorageUseCase

# Confidence threshold below which queries are logged as warnings
LOW_CONFIDENCE_THRESHOLD = 0.5

if TYPE_CHECKING:
    from src.application.services.ports.ingestion_pipeline_port import (
        IngestionPipelinePort,
    )
    from src.application.services.storage_configuration_service import (
        StorageConfigurationService,
    )
    from src.domain.agents.ports.query_agent_port import QueryAgentPort
    from src.domain.repositories import PublicationRepository, ResearchSpaceRepository
    from src.domain.services.ingestion import IngestionRunContext
    from src.type_definitions.common import (
        JSONObject,
        PublicationUpdate,
        RawRecord,
        SourceMetadata,
    )

logger = logging.getLogger(__name__)


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


class PubMedIngestionService:
    """Coordinate fetching, transforming, and persisting PubMed data per source."""

    def __init__(  # noqa: PLR0913
        self,
        gateway: PubMedGateway,
        pipeline: IngestionPipelinePort,
        publication_repository: (
            PublicationRepository | None
        ) = None,  # Optional/Deprecated
        transformer: PubMedRecordTransformer | None = None,  # Optional/Deprecated
        storage_service: StorageConfigurationService | None = None,
        query_agent: QueryAgentPort | None = None,
        research_space_repository: ResearchSpaceRepository | None = None,
    ) -> None:
        self._gateway = gateway
        self._pipeline = pipeline
        self._publication_repository = publication_repository
        self._transformer = transformer or PubMedRecordTransformer()
        self._storage_service = storage_service
        self._query_agent = query_agent
        self._research_space_repository = research_space_repository

    async def ingest(
        self,
        source: user_data_source.UserDataSource,
        context: IngestionRunContext | None = None,
    ) -> PubMedIngestionSummary:
        """Execute ingestion for a PubMed data source."""
        self._assert_source_type(source)
        config = self._build_config(source.configuration)
        query_resolution = await self._resolve_query_configuration(
            source=source,
            config=config,
        )
        config = query_resolution.config
        query_generation_decision = query_resolution.query_generation_decision
        query_generation_confidence = query_resolution.query_generation_confidence
        query_generation_run_id = query_resolution.query_generation_run_id
        checkpoint_before = (
            dict(context.source_sync_state.checkpoint_payload)
            if context is not None
            else None
        )
        query_signature = (
            context.query_signature
            if context is not None and context.query_signature.strip()
            else self._build_query_signature(
                source_type=source.source_type,
                metadata=config.model_dump(mode="json"),
            )
        )

        fetch_result = await self._fetch_records_with_checkpoint(
            config=config,
            checkpoint_before=checkpoint_before,
        )
        raw_records_data = fetch_result.records
        dedup_outcome = self._build_ledger_dedup_outcome(
            source=source,
            records=raw_records_data,
            context=context,
        )
        filtered_records = dedup_outcome.filtered_records

        # Persist raw records if a storage backend is configured (Preserved)
        if self._storage_service:
            await self._persist_raw_records(filtered_records, source)

        # Convert gateway JSON records to pipeline RawRecord contracts.
        raw_records = self._to_pipeline_records(
            filtered_records,
            original_source_id=str(source.id),
        )

        observations_created = 0

        # Run kernel pipeline only when the source is scoped to a research space.
        # Some legacy workflows still create PubMed sources without a space.
        if source.research_space_id is not None:
            result = self._pipeline.run(
                raw_records,
                research_space_id=str(source.research_space_id),
            )
            observations_created = result.observations_created
        else:
            logger.warning(
                "PubMed source %s has no research_space_id; skipping kernel pipeline",
                source.id,
            )

        # Map IngestResult to PubMedIngestionSummary
        # Note: PubMedIngestionSummary expects created_publication_ids (ints)
        # But pipeline works with UUIDs.
        # We might need to adjust the Summary or return simplified summary.
        # For now, we return placeholder counts.

        if (
            context is not None
            and context.source_record_ledger_repository is not None
            and dedup_outcome.entries_to_upsert
        ):
            context.source_record_ledger_repository.upsert_entries(
                dedup_outcome.entries_to_upsert,
            )

        checkpoint_after_raw = fetch_result.checkpoint_after
        if isinstance(checkpoint_after_raw, dict):
            checkpoint_after_payload: JSONObject = dict(checkpoint_after_raw)
        else:
            checkpoint_after_payload = self._build_fallback_checkpoint(
                fetched_records=fetch_result.fetched_records,
                processed_records=len(filtered_records),
            )

        return PubMedIngestionSummary(
            source_id=source.id,
            fetched_records=fetch_result.fetched_records,
            parsed_publications=len(raw_records),
            created_publications=observations_created,  # kernel observations created
            updated_publications=0,
            created_publication_ids=(),  # Pipeline uses UUIDs, Summary expects ints?
            updated_publication_ids=(),
            executed_query=config.query,
            query_generation_run_id=query_generation_run_id,
            query_generation_model=config.agent_config.model_id,
            query_generation_decision=query_generation_decision,
            query_generation_confidence=query_generation_confidence,
            query_signature=query_signature,
            checkpoint_before=checkpoint_before,
            checkpoint_after=checkpoint_after_payload,
            checkpoint_kind=fetch_result.checkpoint_kind.value,
            new_records=dedup_outcome.new_records,
            updated_records=dedup_outcome.updated_records,
            unchanged_records=dedup_outcome.unchanged_records,
            skipped_records=dedup_outcome.unchanged_records,
        )

    async def _resolve_query_configuration(
        self,
        *,
        source: user_data_source.UserDataSource,
        config: data_source_configs.PubMedQueryConfig,
    ) -> _QueryResolution:
        """Resolve AI-managed query overrides and associated metadata."""
        query_generation_decision = "skipped"
        query_generation_confidence = 0.0
        query_generation_run_id: str | None = None

        if (
            not config.agent_config.is_ai_managed
            or self._query_agent is None
            or self._research_space_repository is None
        ):
            return _QueryResolution(
                config=config,
                query_generation_decision=query_generation_decision,
                query_generation_confidence=query_generation_confidence,
                query_generation_run_id=query_generation_run_id,
            )

        research_space_description = ""
        if config.agent_config.use_research_space_context and source.research_space_id:
            space = self._research_space_repository.find_by_id(source.research_space_id)
            if space:
                research_space_description = space.description

        contract = await self._query_agent.generate_query(
            research_space_description=research_space_description,
            user_instructions=config.agent_config.agent_prompt,
            source_type="pubmed",
            model_id=config.agent_config.model_id,
        )
        query_generation_decision = contract.decision
        query_generation_confidence = contract.confidence_score
        query_generation_run_id = self._extract_query_generation_run_id()

        resolved_config = config
        if contract.decision == "generated" and contract.query:
            resolved_config = config.model_copy(update={"query": contract.query})
        elif contract.decision == "escalate":
            logger.warning(
                "AI query generation escalated: %s (confidence=%.2f)",
                contract.rationale,
                contract.confidence_score,
            )
        elif contract.confidence_score < LOW_CONFIDENCE_THRESHOLD:
            logger.warning(
                "Low confidence AI query (%.2f): %s",
                contract.confidence_score,
                contract.rationale,
            )

        return _QueryResolution(
            config=resolved_config,
            query_generation_decision=query_generation_decision,
            query_generation_confidence=query_generation_confidence,
            query_generation_run_id=query_generation_run_id,
        )

    async def _fetch_records_with_checkpoint(
        self,
        *,
        config: data_source_configs.PubMedQueryConfig,
        checkpoint_before: JSONObject | None,
    ) -> PubMedGatewayFetchResult:
        if isinstance(self._gateway, PubMedIncrementalGateway):
            return await self._gateway.fetch_records_incremental(
                config,
                checkpoint=checkpoint_before,
            )

        records = await self._gateway.fetch_records(config)
        return PubMedGatewayFetchResult(
            records=records,
            fetched_records=len(records),
            checkpoint_after=None,
            checkpoint_kind=CheckpointKind.NONE,
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
        self,
        records: list[JSONObject],
        *,
        original_source_id: str,
    ) -> list[IngestionRawRecord]:
        """
        Adapt PubMed JSON records into the kernel ingestion pipeline record format.

        This lives in the application layer (not infrastructure) because it is a
        coordination concern: converting a gateway response into a pipeline input.
        """
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
        self,
        *,
        source: user_data_source.UserDataSource,
        records: list[JSONObject],
        context: IngestionRunContext | None,
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
            if existing_entry.payload_hash == payload_hash:
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

        payload_hash = PubMedIngestionService._compute_payload_hash(record)
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
        self,
        records: list[RawRecord],
        source: user_data_source.UserDataSource,
    ) -> None:
        """Persist raw records to storage if backend is available."""
        if not self._storage_service:
            return

        backend = self._storage_service.resolve_backend_for_use_case(
            StorageUseCase.RAW_SOURCE,
        )
        if not backend:
            return

        # Create a temporary file to store the raw records
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(list(records), tmp, default=str)
            tmp_path = Path(tmp.name)

        try:
            # Generate a unique key for this ingestion run
            timestamp = source.updated_at.strftime("%Y%m%d_%H%M%S")
            key = f"pubmed/{source.id}/raw/{timestamp}_{uuid4().hex[:8]}.json"

            await self._storage_service.record_store_operation(
                configuration=backend,
                key=key,
                file_path=tmp_path,
                content_type="application/json",
                user_id=source.owner_id,
                metadata={
                    "source_id": str(source.id),
                    "record_count": len(list(records)),
                },
            )
        finally:
            # clean up temp file
            if tmp_path.exists():
                tmp_path.unlink()

    def _transform_records(
        self,
        records: list[RawRecord],
    ) -> list[publication.Publication]:
        transformed: list[publication.Publication] = []
        for record in records:
            try:
                publication = self._transformer.to_publication(record)
            except ValueError:
                continue
            transformed.append(publication)
        return transformed

    def _persist_publications(
        self,
        publications: list[publication.Publication],
    ) -> tuple[int, int, tuple[int, ...], tuple[int, ...]]:
        created = 0
        updated = 0
        created_ids: list[int] = []
        updated_ids: list[int] = []

        if not self._publication_repository:
            logger.warning(
                "Publication repository not configured, skipping persistence.",
            )
            return created, updated, tuple(created_ids), tuple(updated_ids)

        for publication_record in publications:
            pmid = publication_record.identifier.pubmed_id
            if pmid and (existing := self._publication_repository.find_by_pmid(pmid)):
                if existing.id is None:
                    continue
                updates = self._build_update_payload(publication_record)
                updated_entity = self._publication_repository.update_publication(
                    existing.id,
                    updates,
                )
                if updated_entity.id is not None:
                    updated_ids.append(updated_entity.id)
                updated += 1
            else:
                created_entity = self._publication_repository.create(publication_record)
                if created_entity.id is not None:
                    created_ids.append(created_entity.id)
                created += 1
        return created, updated, tuple(created_ids), tuple(updated_ids)

    def _extract_query_generation_run_id(self) -> str | None:
        """Extract the latest query-generation run id from the query agent."""
        if self._query_agent is None:
            return None
        provider = getattr(self._query_agent, "get_last_run_id", None)
        if callable(provider):
            run_id = provider()
            return run_id if isinstance(run_id, str) and run_id.strip() else None
        return None

    @staticmethod
    def _build_update_payload(
        publication: publication.Publication,
    ) -> PublicationUpdate:
        return {
            "title": publication.title,
            "authors": list(publication.authors),
            "journal": publication.journal,
            "publication_year": publication.publication_year,
            "abstract": publication.abstract,
            "doi": publication.identifier.doi,
            "pmid": publication.identifier.pubmed_id,
        }

    @staticmethod
    def _build_config(
        configuration: user_data_source.SourceConfiguration,
    ) -> data_source_configs.PubMedQueryConfig:
        metadata: SourceMetadata = dict(configuration.metadata or {})
        if configuration.query:
            metadata["query"] = configuration.query
        return data_source_configs.PubMedQueryConfig.model_validate(metadata)

    @staticmethod
    def _assert_source_type(source: user_data_source.UserDataSource) -> None:
        if source.source_type != user_data_source.SourceType.PUBMED:
            message = (
                f"PubMed ingestion can only be executed for PubMed sources "
                f"(got {source.source_type.value})"
            )
            raise ValueError(message)
