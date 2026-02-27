"""Pipeline and source/read-model loading helpers for workflow monitor."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from sqlalchemy import desc, select

from src.models.database.extraction_queue import ExtractionQueueItemModel
from src.models.database.ingestion_job import IngestionJobModel
from src.models.database.publication_extraction import PublicationExtractionModel
from src.models.database.source_document import SourceDocumentModel
from src.models.database.user_data_source import UserDataSourceModel

from ._source_workflow_monitor_shared import (
    PipelineRunRecord,
    coerce_json_object,
    normalize_optional_string,
    safe_int,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject
else:
    JSONObject = dict[str, object]  # Runtime type stub


class SourceWorkflowMonitorPipelineMixin:
    """Data loading and shaping helpers for source workflow monitoring."""

    _session: Session
    _RUN_SCOPED_PREFETCH_MULTIPLIER = 10
    _RUN_SCOPED_PREFETCH_FLOOR = 500
    _MONITOR_PREFETCH_HARD_CAP = 2_000
    _PIPELINE_RUN_SCAN_MULTIPLIER = 6
    _PIPELINE_RUN_SCAN_HARD_CAP = 5_000

    @classmethod
    def _resolve_prefetch_limit(
        cls,
        *,
        limit: int,
        run_scoped: bool,
    ) -> int:
        requested_limit = max(limit, 1)
        if run_scoped:
            requested_limit = max(
                requested_limit * cls._RUN_SCOPED_PREFETCH_MULTIPLIER,
                cls._RUN_SCOPED_PREFETCH_FLOOR,
            )
        return min(requested_limit, cls._MONITOR_PREFETCH_HARD_CAP)

    def _require_source(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
    ) -> UserDataSourceModel:
        statement = (
            select(UserDataSourceModel)
            .where(UserDataSourceModel.id == str(source_id))
            .where(UserDataSourceModel.research_space_id == str(space_id))
            .limit(1)
        )
        source = self._session.execute(statement).scalar_one_or_none()
        if source is None:
            msg = "Data source not found in this research space"
            raise LookupError(msg)
        return source

    def _load_pipeline_runs(
        self,
        *,
        source_id: UUID,
        limit: int,
    ) -> list[PipelineRunRecord]:
        fetch_limit = min(
            max(limit, 1) * self._PIPELINE_RUN_SCAN_MULTIPLIER,
            self._PIPELINE_RUN_SCAN_HARD_CAP,
        )
        statement = (
            select(IngestionJobModel)
            .where(IngestionJobModel.source_id == str(source_id))
            .order_by(desc(IngestionJobModel.triggered_at))
            .limit(fetch_limit)
        )
        rows = self._session.execute(statement).scalars().all()

        run_records: list[PipelineRunRecord] = []
        for row in rows:
            metadata = coerce_json_object(row.job_metadata)
            pipeline_payload = coerce_json_object(metadata.get("pipeline_run"))
            run_id = normalize_optional_string(pipeline_payload.get("run_id"))
            if run_id is None:
                continue
            payload = self._build_pipeline_run_payload(
                row=row,
                pipeline_payload=pipeline_payload,
            )
            run_records.append(
                PipelineRunRecord(
                    payload=payload,
                    run_id=run_id,
                    job_id=str(row.id),
                ),
            )
            if len(run_records) >= limit:
                break
        return run_records

    @staticmethod
    def _select_run_record(
        run_records: list[PipelineRunRecord],
        requested_run_id: str | None,
    ) -> PipelineRunRecord | None:
        if not run_records:
            if requested_run_id is not None and requested_run_id.strip():
                msg = f"Pipeline run '{requested_run_id.strip()}' not found for this source"
                raise ValueError(msg)
            return None
        if requested_run_id is None or not requested_run_id.strip():
            return run_records[0]
        normalized = requested_run_id.strip()
        for record in run_records:
            if record.run_id == normalized:
                return record
        msg = f"Pipeline run '{normalized}' not found for this source"
        raise ValueError(msg)

    def _build_pipeline_run_payload(
        self,
        *,
        row: IngestionJobModel,
        pipeline_payload: JSONObject,
    ) -> JSONObject:
        checkpoints = coerce_json_object(pipeline_payload.get("checkpoints"))
        stage_statuses, stage_errors = self._parse_stage_details(checkpoints)

        metrics = coerce_json_object(row.metrics)
        metadata = coerce_json_object(row.job_metadata)
        extraction_queue_meta = coerce_json_object(metadata.get("extraction_queue"))
        extraction_run_meta = coerce_json_object(metadata.get("extraction_run"))
        stage_counters: JSONObject = {
            "records_processed": safe_int(metrics.get("records_processed")),
            "records_failed": safe_int(metrics.get("records_failed")),
            "records_skipped": safe_int(metrics.get("records_skipped")),
            "queued_for_extraction": safe_int(extraction_queue_meta.get("queued")),
            "extraction_processed": safe_int(extraction_run_meta.get("processed")),
            "extraction_completed": safe_int(extraction_run_meta.get("completed")),
            "extraction_failed": safe_int(extraction_run_meta.get("failed")),
        }

        source_snapshot = coerce_json_object(row.source_config_snapshot)
        source_metadata = coerce_json_object(source_snapshot.get("metadata"))
        executed_query = normalize_optional_string(metadata.get("executed_query"))
        if executed_query is None:
            executed_query = normalize_optional_string(source_metadata.get("query"))

        return {
            "job_id": str(row.id),
            "run_id": str(pipeline_payload.get("run_id")),
            "status": normalize_optional_string(pipeline_payload.get("status"))
            or str(row.status.value),
            "triggered_at": row.triggered_at,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "resume_from_stage": normalize_optional_string(
                pipeline_payload.get("resume_from_stage"),
            ),
            "executed_query": executed_query,
            "stage_statuses": stage_statuses,
            "stage_errors": stage_errors,
            "stage_checkpoints": checkpoints,
            "stage_counters": stage_counters,
        }

    @staticmethod
    def _parse_stage_details(
        checkpoints: JSONObject,
    ) -> tuple[dict[str, str], dict[str, str]]:
        statuses: dict[str, str] = {}
        errors: dict[str, str] = {}
        for stage_name, raw_value in checkpoints.items():
            checkpoint = coerce_json_object(raw_value)
            status = normalize_optional_string(checkpoint.get("status"))
            if status is not None:
                statuses[str(stage_name)] = status
            stage_error = normalize_optional_string(checkpoint.get("error"))
            if stage_error is not None:
                errors[str(stage_name)] = stage_error
        return statuses, errors

    def _build_source_snapshot(self, source: UserDataSourceModel) -> JSONObject:
        configuration = coerce_json_object(source.configuration)
        metadata = coerce_json_object(configuration.get("metadata"))
        agent_config = coerce_json_object(metadata.get("agent_config"))

        return {
            "source_id": str(source.id),
            "name": source.name,
            "source_type": source.source_type.value,
            "status": source.status.value,
            "schedule": coerce_json_object(source.ingestion_schedule),
            "query": normalize_optional_string(metadata.get("query"))
            or normalize_optional_string(configuration.get("query")),
            "model_id": normalize_optional_string(agent_config.get("model_id")),
            "open_access_only": metadata.get("open_access_only"),
            "max_results": metadata.get("max_results"),
            "agent_prompt": normalize_optional_string(
                agent_config.get("agent_prompt"),
            ),
            "use_research_space_context": agent_config.get(
                "use_research_space_context",
            ),
            "is_ai_managed": agent_config.get("is_ai_managed"),
        }

    def _load_source_documents(
        self,
        *,
        source_id: UUID,
        run_id: str | None,
        ingestion_job_id: str | None,
        limit: int,
    ) -> list[JSONObject]:
        normalized_run_id = (
            run_id.strip() if isinstance(run_id, str) and run_id.strip() else None
        )
        normalized_ingestion_job_id = (
            ingestion_job_id.strip()
            if isinstance(ingestion_job_id, str) and ingestion_job_id.strip()
            else None
        )
        fetch_limit = self._resolve_prefetch_limit(
            limit=limit,
            run_scoped=(
                normalized_run_id is not None or normalized_ingestion_job_id is not None
            ),
        )
        statement = (
            select(SourceDocumentModel)
            .where(SourceDocumentModel.source_id == str(source_id))
            .order_by(desc(SourceDocumentModel.created_at))
            .limit(fetch_limit)
        )
        rows = self._session.execute(statement).scalars().all()

        documents: list[JSONObject] = []
        for row in rows:
            row_ingestion_job_id = normalize_optional_string(row.ingestion_job_id)
            if (
                normalized_ingestion_job_id is not None
                and row_ingestion_job_id != normalized_ingestion_job_id
            ):
                continue
            metadata = coerce_json_object(row.metadata_payload)
            row_run_id = normalize_optional_string(metadata.get("pipeline_run_id"))
            if (
                normalized_run_id is not None
                and row_run_id is not None
                and row_run_id != normalized_run_id
            ):
                continue
            documents.append(
                {
                    "id": str(row.id),
                    "external_record_id": row.external_record_id,
                    "source_type": row.source_type,
                    "document_format": row.document_format,
                    "enrichment_status": row.enrichment_status,
                    "enrichment_agent_run_id": row.enrichment_agent_run_id,
                    "extraction_status": row.extraction_status,
                    "extraction_agent_run_id": row.extraction_agent_run_id,
                    "ingestion_job_id": row.ingestion_job_id,
                    "content_length_chars": row.content_length_chars,
                    "metadata": metadata,
                    "created_at": row.created_at.isoformat(),
                    "updated_at": row.updated_at.isoformat(),
                },
            )
            if len(documents) >= limit:
                break
        return documents

    def _load_extraction_queue(  # noqa: PLR0913 - explicit monitor filters are intentional
        self,
        *,
        source_id: UUID,
        run_id: str | None,
        ingestion_job_id: str | None,
        external_record_ids: set[str],
        limit: int,
    ) -> list[JSONObject]:
        normalized_run_id = (
            run_id.strip() if isinstance(run_id, str) and run_id.strip() else None
        )
        normalized_ingestion_job_id = (
            ingestion_job_id.strip()
            if isinstance(ingestion_job_id, str) and ingestion_job_id.strip()
            else None
        )
        fetch_limit = self._resolve_prefetch_limit(
            limit=limit,
            run_scoped=(
                normalized_run_id is not None or normalized_ingestion_job_id is not None
            ),
        )
        statement = (
            select(ExtractionQueueItemModel)
            .where(ExtractionQueueItemModel.source_id == str(source_id))
            .order_by(desc(ExtractionQueueItemModel.queued_at))
            .limit(fetch_limit)
        )
        rows = self._session.execute(statement).scalars().all()

        queue_rows: list[JSONObject] = []
        for row in rows:
            row_ingestion_job_id = normalize_optional_string(row.ingestion_job_id)
            if (
                normalized_ingestion_job_id is not None
                and row_ingestion_job_id != normalized_ingestion_job_id
            ):
                continue
            metadata = coerce_json_object(row.metadata_payload)
            if normalized_run_id is not None and (
                (
                    normalize_optional_string(metadata.get("pipeline_run_id"))
                    not in {None, normalized_run_id}
                )
                or row.source_record_id not in external_record_ids
            ):
                continue
            queue_rows.append(
                {
                    "id": str(row.id),
                    "source_record_id": row.source_record_id,
                    "pubmed_id": row.pubmed_id,
                    "status": row.status.value,
                    "attempts": row.attempts,
                    "last_error": row.last_error,
                    "ingestion_job_id": row.ingestion_job_id,
                    "queued_at": row.queued_at.isoformat(),
                    "started_at": (
                        row.started_at.isoformat() if row.started_at else None
                    ),
                    "completed_at": (
                        row.completed_at.isoformat() if row.completed_at else None
                    ),
                    "metadata": metadata,
                },
            )
            if len(queue_rows) >= limit:
                break
        return queue_rows

    def _load_publication_extractions(  # noqa: PLR0913 - explicit monitor filters are intentional
        self,
        *,
        source_id: UUID,
        run_id: str | None,
        ingestion_job_id: str | None,
        queue_item_ids: set[str],
        limit: int,
    ) -> list[JSONObject]:
        normalized_run_id = (
            run_id.strip() if isinstance(run_id, str) and run_id.strip() else None
        )
        normalized_ingestion_job_id = (
            ingestion_job_id.strip()
            if isinstance(ingestion_job_id, str) and ingestion_job_id.strip()
            else None
        )
        fetch_limit = self._resolve_prefetch_limit(
            limit=limit,
            run_scoped=(
                normalized_run_id is not None or normalized_ingestion_job_id is not None
            ),
        )
        statement = (
            select(PublicationExtractionModel)
            .where(PublicationExtractionModel.source_id == str(source_id))
            .order_by(desc(PublicationExtractionModel.extracted_at))
            .limit(fetch_limit)
        )
        rows = self._session.execute(statement).scalars().all()

        extraction_rows: list[JSONObject] = []
        for row in rows:
            row_ingestion_job_id = normalize_optional_string(row.ingestion_job_id)
            if (
                normalized_ingestion_job_id is not None
                and row_ingestion_job_id != normalized_ingestion_job_id
            ):
                continue
            metadata = coerce_json_object(row.metadata_payload)
            if normalized_run_id is not None and (
                (
                    normalize_optional_string(metadata.get("pipeline_run_id"))
                    not in {None, normalized_run_id}
                )
                or str(row.queue_item_id) not in queue_item_ids
            ):
                continue
            extraction_rows.append(
                {
                    "id": str(row.id),
                    "queue_item_id": str(row.queue_item_id),
                    "status": row.status.value,
                    "text_source": row.text_source,
                    "processor_name": row.processor_name,
                    "processor_version": row.processor_version,
                    "facts_count": len(row.facts or []),
                    "metadata": metadata,
                    "extracted_at": row.extracted_at.isoformat(),
                },
            )
            if len(extraction_rows) >= limit:
                break
        return extraction_rows

    @staticmethod
    def _count_statuses(
        *,
        records: list[JSONObject],
        key: str,
    ) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for record in records:
            normalized = normalize_optional_string(record.get(key)) or "unknown"
            counter[normalized] += 1
        return dict(counter)


__all__ = ["SourceWorkflowMonitorPipelineMixin"]
