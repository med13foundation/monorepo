"""Application service for orchestrating ClinVar ingestion per data source."""

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

from src.domain.entities import data_source_configs, user_data_source
from src.domain.entities.source_record_ledger import SourceRecordLedgerEntry
from src.domain.entities.source_sync_state import CheckpointKind
from src.domain.services.clinvar_ingestion import (
    ClinVarGateway,
    ClinVarGatewayFetchResult,
    ClinVarIncrementalGateway,
    ClinVarIngestionSummary,
)
from src.type_definitions.ingestion import RawRecord as IngestionRawRecord
from src.type_definitions.json_utils import to_json_value
from src.type_definitions.storage import StorageUseCase

if TYPE_CHECKING:
    from src.application.services.ports.ingestion_pipeline_port import (
        IngestionPipelinePort,
    )
    from src.application.services.storage_configuration_service import (
        StorageConfigurationService,
    )
    from src.domain.services.ingestion import IngestionRunContext
    from src.type_definitions.common import JSONObject, RawRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _LedgerDedupOutcome:
    """Result of applying record-ledger deduplication to fetched records."""

    filtered_records: list[JSONObject]
    entries_to_upsert: list[SourceRecordLedgerEntry]
    new_records: int
    updated_records: int
    unchanged_records: int


class ClinVarIngestionService:
    """Coordinate fetching, transforming, and persisting ClinVar data per source."""

    def __init__(
        self,
        gateway: ClinVarGateway,
        pipeline: IngestionPipelinePort,
        storage_service: StorageConfigurationService | None = None,
    ) -> None:
        self._gateway = gateway
        self._pipeline = pipeline
        self._storage_service = storage_service

    async def ingest(
        self,
        source: user_data_source.UserDataSource,
        context: IngestionRunContext | None = None,
    ) -> ClinVarIngestionSummary:
        """Execute ingestion for a ClinVar data source."""
        self._assert_source_type(source)
        config = self._build_config(source.configuration)
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

        if self._storage_service:
            await self._persist_raw_records(filtered_records, source)

        raw_records = self._to_pipeline_records(
            filtered_records,
            original_source_id=str(source.id),
        )

        observations_created = 0
        if source.research_space_id is not None:
            result = self._pipeline.run(
                raw_records,
                research_space_id=str(source.research_space_id),
            )
            observations_created = result.observations_created
        else:
            logger.warning(
                "ClinVar source %s has no research_space_id; skipping kernel pipeline",
                source.id,
            )

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

        return ClinVarIngestionSummary(
            source_id=source.id,
            fetched_records=fetch_result.fetched_records,
            parsed_publications=len(raw_records),
            created_publications=observations_created,
            updated_publications=0,
            created_publication_ids=(),
            updated_publication_ids=(),
            executed_query=config.query,
            query_signature=query_signature,
            checkpoint_before=checkpoint_before,
            checkpoint_after=checkpoint_after_payload,
            checkpoint_kind=fetch_result.checkpoint_kind.value,
            new_records=dedup_outcome.new_records,
            updated_records=dedup_outcome.updated_records,
            unchanged_records=dedup_outcome.unchanged_records,
            skipped_records=dedup_outcome.unchanged_records,
        )

    async def _fetch_records_with_checkpoint(
        self,
        *,
        config: data_source_configs.ClinVarQueryConfig,
        checkpoint_before: JSONObject | None,
    ) -> ClinVarGatewayFetchResult:
        if isinstance(self._gateway, ClinVarIncrementalGateway):
            return await self._gateway.fetch_records_incremental(
                config,
                checkpoint=checkpoint_before,
            )

        records = await self._gateway.fetch_records(config)
        return ClinVarGatewayFetchResult(
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
        """Adapt ClinVar JSON records into the kernel ingestion pipeline format."""
        raw_records: list[IngestionRawRecord] = []
        for record in records:
            clinvar_id = record.get("clinvar_id")
            record_id = (
                clinvar_id
                if isinstance(clinvar_id, str) and clinvar_id.strip()
                else str(uuid4())
            )
            payload = self._extract_pipeline_payload(record)

            raw_records.append(
                IngestionRawRecord(
                    source_id=record_id,
                    data=payload,
                    metadata={
                        "original_source_id": original_source_id,
                        "type": "clinvar",
                        "entity_type": "VARIANT",
                        "clinvar_id": payload.get("clinvar_id"),
                        "gene_symbol": payload.get("gene_symbol"),
                        "clinical_significance": payload.get(
                            "clinical_significance",
                        ),
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
        for key in ("clinvar_id", "variation_id", "accession"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return f"clinvar:{key}:{value.strip()}"
            if isinstance(value, int):
                return f"clinvar:{key}:{value}"

        parsed_data_raw = record.get("parsed_data")
        if isinstance(parsed_data_raw, dict):
            for key in ("clinvar_id", "variation_id", "accession"):
                value = parsed_data_raw.get(key)
                if isinstance(value, str) and value.strip():
                    return f"clinvar:{key}:{value.strip()}"
                if isinstance(value, int):
                    return f"clinvar:{key}:{value}"

        payload_hash = ClinVarIngestionService._compute_payload_hash(record)
        return f"clinvar:hash:{payload_hash}"

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

    @staticmethod
    def _extract_pipeline_payload(record: JSONObject) -> JSONObject:
        payload: JSONObject = {}
        parsed_data = record.get("parsed_data")
        if isinstance(parsed_data, dict):
            for key, value in parsed_data.items():
                payload[str(key)] = to_json_value(value)

        for key in (
            "clinvar_id",
            "source",
            "fetched_at",
            "gene_symbol",
            "variant_type",
            "clinical_significance",
            "review_status",
        ):
            value = record.get(key)
            if value is not None:
                payload[key] = to_json_value(value)

        if payload:
            return payload

        for key, value in record.items():
            payload[str(key)] = to_json_value(value)
        return payload

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

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(list(records), tmp, default=str)
            tmp_path = Path(tmp.name)

        try:
            timestamp = source.updated_at.strftime("%Y%m%d_%H%M%S")
            key = f"clinvar/{source.id}/raw/{timestamp}_{uuid4().hex[:8]}.json"

            await self._storage_service.record_store_operation(
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
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    @staticmethod
    def _build_config(
        source_config: user_data_source.SourceConfiguration,
    ) -> data_source_configs.ClinVarQueryConfig:
        metadata = source_config.metadata or {}
        return data_source_configs.ClinVarQueryConfig.model_validate(metadata)

    @staticmethod
    def _assert_source_type(source: user_data_source.UserDataSource) -> None:
        if source.source_type != user_data_source.SourceType.CLINVAR:
            msg = (
                "ClinVar ingestion can only run for ClinVar sources "
                f"(got {source.source_type.value})"
            )
            raise ValueError(msg)
