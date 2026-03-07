"""Developer-facing Artana observability read models."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import Select, select, text
from sqlalchemy.exc import SQLAlchemyError

from src.application.services._artana_observability_support import (
    _append_unique,
    _coerce_datetime,
    _document_matches_run,
    _event_to_payload,
    _has_drift_alert,
    _matches_query,
    _metadata_contains_run,
    _normalize_effective_status,
    _normalize_snapshot_status_filter,
    _parse_uuid,
    _require_run_id,
    _safe_int,
    _serialize_datetime,
    _string_list,
    _summary_to_payload,
    _unique_string_values,
)
from src.application.services._source_workflow_monitor_shared import (
    coerce_json_object,
    normalize_optional_string,
)
from src.models.database.ingestion_job import IngestionJobKindEnum, IngestionJobModel
from src.models.database.kernel.provenance import ProvenanceModel
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel
from src.models.database.publication_extraction import PublicationExtractionModel
from src.models.database.source_document import SourceDocumentModel
from src.models.database.user_data_source import UserDataSourceModel
from src.type_definitions.json_utils import (
    as_float,
    as_object,
    to_json_value,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.engine import RowMapping
    from sqlalchemy.orm import Session

    from src.application.services.ports.agent_run_state_port import AgentRunStatePort
    from src.application.services.ports.artana_run_trace_port import (
        ArtanaRunTraceEventRecord,
        ArtanaRunTracePort,
        ArtanaRunTraceRecord,
    )
    from src.type_definitions.common import JSONObject
    from src.type_definitions.data_sources import AgentRunTableSummary
else:
    Session = object
    JSONObject = dict[str, object]

logger = logging.getLogger(__name__)
alert_logger = logging.getLogger("med13.alerts.artana")

_TRACE_EVENT_LIMIT = 50
_STUCK_RUN_AGE = timedelta(minutes=10)
_UNKNOWN_OUTCOME_AGE = timedelta(minutes=5)
_BUDGET_WARNING_THRESHOLD = 0.8
_NON_TERMINAL_STATUSES = frozenset({"running", "paused"})
_TERMINAL_STATUSES = frozenset({"completed", "failed"})
_ARTANA_SUMMARY_TYPES_OF_INTEREST: tuple[str, ...] = (
    "trace::state_transition",
    "trace::cost",
    "trace::cost_snapshot",
    "trace::drift",
    "trace::tool_validation",
    "med13::stage_transition",
    "med13::document_outcome",
    "med13::persistence_outcome",
    "agent_model_step",
    "agent_verify_step",
    "agent_acceptance_gate",
    "agent_tool_step",
)
_DOCUMENT_METADATA_RUN_KEYS: tuple[str, ...] = (
    "content_enrichment_agent_run_id",
    "entity_recognition_run_id",
    "extraction_stage_run_id",
    "extraction_run_id",
    "graph_agent_run_id",
    "graph_connection_run_id",
    "graph_run_id",
)
_EXTRACTION_METADATA_RUN_KEYS: tuple[str, ...] = (
    "agent_run_id",
    "extraction_run_id",
    "graph_agent_run_id",
    "graph_connection_run_id",
    "graph_run_id",
)
_COST_KEYS: tuple[str, ...] = (
    "total_cost",
    "cost_usd",
    "total_cost_usd",
    "model_cost",
)
_BUDGET_KEYS: tuple[str, ...] = (
    "budget_usd_limit",
    "budget_limit_usd",
    "budget_limit",
    "tenant_budget_usd_limit",
    "run_budget_usd_limit",
)

_SNAPSHOT_LIST_QUERY = text(
    """
    SELECT
        run_id,
        tenant_id,
        last_event_seq,
        last_event_type,
        updated_at,
        status,
        blocked_on,
        failure_reason,
        error_category,
        diagnostics_json,
        last_step_key,
        drift_count,
        last_stage,
        last_tool,
        model_cost_total,
        open_pause_count,
        explain_status,
        explain_failure_reason,
        explain_failure_step
    FROM artana.run_state_snapshots
    WHERE (:run_id IS NULL OR run_id = :run_id)
      AND (:tenant_id IS NULL OR tenant_id = :tenant_id)
      AND (:status IS NULL OR status = :status)
      AND (:updated_since IS NULL OR updated_at >= :updated_since)
    ORDER BY updated_at DESC
    """,
)


@dataclass(frozen=True, slots=True)
class _RunSnapshotRow:
    run_id: str
    tenant_id: str
    last_event_seq: int
    last_event_type: str | None
    updated_at: datetime | None
    status: str
    blocked_on: str | None
    failure_reason: str | None
    error_category: str | None
    diagnostics_json: str | None
    last_step_key: str | None
    drift_count: int
    last_stage: str | None
    last_tool: str | None
    model_cost_total: float
    open_pause_count: int
    explain_status: str | None
    explain_failure_reason: str | None
    explain_failure_step: str | None


class ArtanaObservabilityService:
    """Compose run traces, linked MED13 records, and alert derivation."""

    def __init__(
        self,
        session: Session,
        *,
        run_trace: ArtanaRunTracePort | None = None,
        raw_state: AgentRunStatePort | None = None,
    ) -> None:
        self._session = session
        self._run_trace = run_trace
        self._raw_state = raw_state

    def get_admin_run_trace(self, *, run_id: str) -> JSONObject:
        normalized_run_id = _require_run_id(run_id)
        snapshot = self._get_snapshot_row(run_id=normalized_run_id)
        if snapshot is None:
            msg = f"Artana run '{normalized_run_id}' not found."
            raise LookupError(msg)
        trace = self._require_trace(
            run_id=normalized_run_id,
            tenant_id=snapshot.tenant_id,
        )
        linked_records = self._load_linked_records(
            run_id=trace.run_id,
            research_space_id=snapshot.tenant_id,
        )
        alerts = self._build_alerts(
            trace=trace,
            fallback_snapshot=snapshot,
            now=datetime.now(UTC),
        )
        self._emit_alert_logs(
            run_id=trace.run_id,
            space_id=snapshot.tenant_id,
            alerts=alerts,
            linked_records=linked_records,
        )
        raw_tables = (
            self._raw_state.get_run_table_summaries(trace.run_id)
            if self._raw_state is not None
            else []
        )
        return self._build_trace_payload(
            requested_run_id=normalized_run_id,
            trace=trace,
            candidate_run_ids=[trace.run_id],
            alerts=alerts,
            linked_records=linked_records,
            raw_tables=raw_tables,
        )

    def get_space_run_trace(
        self,
        *,
        space_id: UUID,
        run_id: str,
    ) -> JSONObject:
        normalized_run_id = _require_run_id(run_id)
        requested_space_id = str(space_id)
        resolution = self._resolve_space_run(
            research_space_id=requested_space_id,
            requested_run_id=normalized_run_id,
        )
        if resolution is None:
            msg = (
                f"Artana run or pipeline run '{normalized_run_id}' not found in this "
                "research space."
            )
            raise LookupError(msg)
        trace = self._require_trace(
            run_id=resolution.resolved_run_id,
            tenant_id=requested_space_id,
        )
        linked_records = self._load_linked_records(
            run_id=trace.run_id,
            research_space_id=requested_space_id,
        )
        alerts = self._build_alerts(
            trace=trace,
            fallback_snapshot=resolution.snapshot,
            now=datetime.now(UTC),
        )
        self._emit_alert_logs(
            run_id=trace.run_id,
            space_id=requested_space_id,
            alerts=alerts,
            linked_records=linked_records,
        )
        return self._build_trace_payload(
            requested_run_id=normalized_run_id,
            trace=trace,
            candidate_run_ids=resolution.candidate_run_ids,
            alerts=alerts,
            linked_records=linked_records,
            raw_tables=None,
        )

    def list_admin_runs(  # noqa: PLR0913 - explicit filters are intentional
        self,
        *,
        q: str | None,
        status: str | None,
        space_id: str | None,
        source_type: str | None,
        alert_code: str | None,
        since_hours: int | None,
        page: int,
        per_page: int,
    ) -> JSONObject:
        normalized_space_id = normalize_optional_string(space_id)
        normalized_status = _normalize_snapshot_status_filter(status)
        updated_since = (
            datetime.now(UTC) - timedelta(hours=since_hours)
            if isinstance(since_hours, int) and since_hours > 0
            else None
        )
        snapshot_rows = self._list_snapshot_rows(
            run_id=None,
            tenant_id=normalized_space_id,
            status=normalized_status,
            updated_since=updated_since,
        )
        items: list[JSONObject] = []
        now = datetime.now(UTC)
        normalized_query = (q or "").strip().lower()
        normalized_source_type = (source_type or "").strip().lower()
        normalized_alert_code = normalize_optional_string(alert_code)

        for snapshot in snapshot_rows:
            trace = (
                self._require_trace(
                    run_id=snapshot.run_id,
                    tenant_id=snapshot.tenant_id,
                )
                if self._run_trace is not None
                else None
            )
            linked_records = self._load_linked_records(
                run_id=snapshot.run_id,
                research_space_id=snapshot.tenant_id,
            )
            alerts = self._build_alerts(
                trace=trace,
                fallback_snapshot=snapshot,
                now=now,
            )
            item = self._build_list_item(
                snapshot=snapshot,
                trace=trace,
                linked_records=linked_records,
                alerts=alerts,
            )
            if normalized_source_type and (
                item.get("source_type") != normalized_source_type
            ):
                continue
            alert_codes = _string_list(item.get("alert_codes"))
            if normalized_alert_code and normalized_alert_code not in alert_codes:
                continue
            if normalized_query and not _matches_query(
                item=item,
                query=normalized_query,
            ):
                continue
            items.append(item)

        counters = self._build_list_counters(items)
        total = len(items)
        page_value = max(page, 1)
        per_page_value = max(per_page, 1)
        offset = (page_value - 1) * per_page_value
        return {
            "runs": items[offset : offset + per_page_value],
            "total": total,
            "page": page_value,
            "per_page": per_page_value,
            "counters": counters,
        }

    def _require_trace(
        self,
        *,
        run_id: str,
        tenant_id: str,
    ) -> ArtanaRunTraceRecord:
        if self._run_trace is None:
            msg = "Artana observability reader is unavailable in this environment."
            raise RuntimeError(msg)
        trace = self._run_trace.get_run_trace(
            run_id=run_id,
            tenant_id=tenant_id,
        )
        if trace is None:
            msg = f"Artana trace '{run_id}' not found."
            raise LookupError(msg)
        return trace

    def _get_snapshot_row(self, *, run_id: str) -> _RunSnapshotRow | None:
        rows = self._list_snapshot_rows(
            run_id=run_id,
            tenant_id=None,
            status=None,
            updated_since=None,
        )
        return rows[0] if rows else None

    def _list_snapshot_rows(
        self,
        *,
        run_id: str | None,
        tenant_id: str | None,
        status: str | None,
        updated_since: datetime | None,
    ) -> list[_RunSnapshotRow]:
        try:
            rows = (
                self._session.execute(
                    _SNAPSHOT_LIST_QUERY,
                    {
                        "run_id": run_id,
                        "tenant_id": tenant_id,
                        "status": status,
                        "updated_since": updated_since,
                    },
                )
                .mappings()
                .all()
            )
        except SQLAlchemyError as exc:
            logger.debug(
                "Artana run_state_snapshots not available; returning no snapshots. %s",
                exc,
            )
            return []
        return [_snapshot_from_row(row) for row in rows]

    def _resolve_space_run(
        self,
        *,
        research_space_id: str,
        requested_run_id: str,
    ) -> _RunResolution | None:
        direct_snapshot = next(
            iter(
                self._list_snapshot_rows(
                    run_id=requested_run_id,
                    tenant_id=research_space_id,
                    status=None,
                    updated_since=None,
                ),
            ),
            None,
        )
        if direct_snapshot is not None:
            return _RunResolution(
                resolved_run_id=requested_run_id,
                candidate_run_ids=[requested_run_id],
                snapshot=direct_snapshot,
            )

        candidate_run_ids = self._resolve_candidate_run_ids_for_pipeline(
            research_space_id=research_space_id,
            pipeline_run_id=requested_run_id,
        )
        if not candidate_run_ids:
            return None

        snapshots_by_run_id = {
            snapshot.run_id: snapshot
            for snapshot in self._list_snapshot_rows(
                run_id=None,
                tenant_id=research_space_id,
                status=None,
                updated_since=None,
            )
            if snapshot.run_id in candidate_run_ids
        }

        def _candidate_updated_at(candidate: str) -> datetime:
            snapshot = snapshots_by_run_id.get(candidate)
            if snapshot is None or snapshot.updated_at is None:
                return datetime.min.replace(tzinfo=UTC)
            return snapshot.updated_at

        sorted_candidates = sorted(
            candidate_run_ids,
            key=_candidate_updated_at,
            reverse=True,
        )
        resolved_run_id = sorted_candidates[0]
        return _RunResolution(
            resolved_run_id=resolved_run_id,
            candidate_run_ids=sorted_candidates,
            snapshot=snapshots_by_run_id.get(resolved_run_id),
        )

    def _resolve_candidate_run_ids_for_pipeline(  # noqa: C901 - explicit resolution rules
        self,
        *,
        research_space_id: str,
        pipeline_run_id: str,
    ) -> list[str]:
        candidates: list[str] = []

        pipeline_jobs = (
            self._session.execute(
                select(IngestionJobModel)
                .join(
                    UserDataSourceModel,
                    UserDataSourceModel.id == IngestionJobModel.source_id,
                )
                .where(UserDataSourceModel.research_space_id == research_space_id)
                .where(
                    IngestionJobModel.job_kind
                    == IngestionJobKindEnum.PIPELINE_ORCHESTRATION,
                ),
            )
            .scalars()
            .all()
        )
        for job in pipeline_jobs:
            metadata = coerce_json_object(job.job_metadata)
            pipeline_payload = coerce_json_object(metadata.get("pipeline_run"))
            if (
                normalize_optional_string(pipeline_payload.get("run_id"))
                != pipeline_run_id
            ):
                continue
            query_generation = coerce_json_object(metadata.get("query_generation"))
            _append_unique(candidates, query_generation.get("run_id"))

        documents = (
            self._session.execute(
                select(SourceDocumentModel).where(
                    SourceDocumentModel.research_space_id == research_space_id,
                ),
            )
            .scalars()
            .all()
        )
        pipeline_document_ids: list[str] = []
        for document in documents:
            metadata = coerce_json_object(document.metadata_payload)
            if (
                normalize_optional_string(metadata.get("pipeline_run_id"))
                != pipeline_run_id
            ):
                continue
            pipeline_document_ids.append(str(document.id))
            _append_unique(candidates, document.enrichment_agent_run_id)
            _append_unique(candidates, document.extraction_agent_run_id)
            for key in _DOCUMENT_METADATA_RUN_KEYS:
                _append_unique(candidates, metadata.get(key))

        publication_extractions = (
            self._session.execute(
                select(PublicationExtractionModel)
                .join(
                    UserDataSourceModel,
                    UserDataSourceModel.id == PublicationExtractionModel.source_id,
                )
                .where(UserDataSourceModel.research_space_id == research_space_id),
            )
            .scalars()
            .all()
        )
        for extraction in publication_extractions:
            metadata = coerce_json_object(extraction.metadata_payload)
            if (
                normalize_optional_string(metadata.get("pipeline_run_id"))
                != pipeline_run_id
            ):
                continue
            for key in _EXTRACTION_METADATA_RUN_KEYS:
                _append_unique(candidates, metadata.get(key))

        if pipeline_document_ids:
            relation_rows = (
                self._session.execute(
                    select(RelationEvidenceModel).where(
                        RelationEvidenceModel.source_document_id.in_(
                            pipeline_document_ids,
                        ),
                    ),
                )
                .scalars()
                .all()
            )
            for relation_row in relation_rows:
                _append_unique(candidates, relation_row.agent_run_id)

        return candidates

    def _load_linked_records(
        self,
        *,
        run_id: str,
        research_space_id: str | None,
    ) -> list[JSONObject]:
        linked_records: list[JSONObject] = []
        linked_records.extend(
            self._load_linked_source_documents(
                run_id=run_id,
                research_space_id=research_space_id,
            ),
        )
        linked_records.extend(
            self._load_linked_publication_extractions(
                run_id=run_id,
                research_space_id=research_space_id,
            ),
        )
        linked_records.extend(
            self._load_linked_relation_evidence(
                run_id=run_id,
                research_space_id=research_space_id,
            ),
        )
        linked_records.extend(
            self._load_linked_provenance(
                run_id=run_id,
                research_space_id=research_space_id,
            ),
        )
        return linked_records

    def _load_linked_source_documents(
        self,
        *,
        run_id: str,
        research_space_id: str | None,
    ) -> list[JSONObject]:
        statement: Select[tuple[SourceDocumentModel]] = select(SourceDocumentModel)
        if research_space_id is not None:
            statement = statement.where(
                SourceDocumentModel.research_space_id == research_space_id,
            )
        rows = self._session.execute(statement).scalars().all()
        records: list[JSONObject] = []
        for row in rows:
            metadata = coerce_json_object(row.metadata_payload)
            if not _document_matches_run(
                row=row,
                metadata=metadata,
                run_id=run_id,
                candidate_keys=_DOCUMENT_METADATA_RUN_KEYS,
            ):
                continue
            records.append(
                {
                    "record_type": "source_document",
                    "record_id": str(row.id),
                    "research_space_id": (
                        str(row.research_space_id) if row.research_space_id else None
                    ),
                    "source_id": str(row.source_id),
                    "document_id": str(row.id),
                    "source_type": row.source_type,
                    "status": row.extraction_status,
                    "label": row.external_record_id,
                    "created_at": _serialize_datetime(row.created_at),
                    "updated_at": _serialize_datetime(row.updated_at),
                    "metadata": {
                        "external_record_id": row.external_record_id,
                        "document_format": row.document_format,
                        "enrichment_status": row.enrichment_status,
                        "enrichment_agent_run_id": row.enrichment_agent_run_id,
                        "extraction_agent_run_id": row.extraction_agent_run_id,
                        "pipeline_run_id": metadata.get("pipeline_run_id"),
                    },
                },
            )
        return records

    def _load_linked_publication_extractions(
        self,
        *,
        run_id: str,
        research_space_id: str | None,
    ) -> list[JSONObject]:
        statement = select(PublicationExtractionModel, UserDataSourceModel).join(
            UserDataSourceModel,
            UserDataSourceModel.id == PublicationExtractionModel.source_id,
        )
        if research_space_id is not None:
            statement = statement.where(
                UserDataSourceModel.research_space_id == research_space_id,
            )
        rows = self._session.execute(statement).all()
        records: list[JSONObject] = []
        for extraction, source in rows:
            metadata = coerce_json_object(extraction.metadata_payload)
            if not _metadata_contains_run(
                metadata=metadata,
                run_id=run_id,
                candidate_keys=_EXTRACTION_METADATA_RUN_KEYS,
            ):
                continue
            records.append(
                {
                    "record_type": "publication_extraction",
                    "record_id": str(extraction.id),
                    "research_space_id": (
                        str(source.research_space_id)
                        if source.research_space_id is not None
                        else None
                    ),
                    "source_id": str(extraction.source_id),
                    "document_id": None,
                    "source_type": source.source_type.value,
                    "status": extraction.status.value,
                    "label": str(extraction.pubmed_id or extraction.id),
                    "created_at": _serialize_datetime(extraction.created_at),
                    "updated_at": _serialize_datetime(extraction.updated_at),
                    "metadata": {
                        "queue_item_id": str(extraction.queue_item_id),
                        "processor_name": extraction.processor_name,
                        "processor_version": extraction.processor_version,
                        "text_source": extraction.text_source,
                        "pipeline_run_id": metadata.get("pipeline_run_id"),
                    },
                },
            )
        return records

    def _load_linked_relation_evidence(
        self,
        *,
        run_id: str,
        research_space_id: str | None,
    ) -> list[JSONObject]:
        statement = select(RelationEvidenceModel, RelationModel).join(
            RelationModel,
            RelationModel.id == RelationEvidenceModel.relation_id,
        )
        statement = statement.where(RelationEvidenceModel.agent_run_id == run_id)
        parsed_space_id = _parse_uuid(research_space_id)
        if parsed_space_id is not None:
            statement = statement.where(
                RelationModel.research_space_id == parsed_space_id,
            )
        rows = self._session.execute(statement).all()
        records: list[JSONObject] = []
        for evidence, relation in rows:
            records.append(
                {
                    "record_type": "relation_evidence",
                    "record_id": str(evidence.id),
                    "research_space_id": str(relation.research_space_id),
                    "source_id": None,
                    "document_id": (
                        str(evidence.source_document_id)
                        if evidence.source_document_id is not None
                        else None
                    ),
                    "source_type": None,
                    "status": relation.curation_status,
                    "label": relation.relation_type,
                    "created_at": _serialize_datetime(evidence.created_at),
                    "updated_at": _serialize_datetime(relation.updated_at),
                    "metadata": {
                        "relation_id": str(relation.id),
                        "relation_type": relation.relation_type,
                        "source_entity_id": str(relation.source_id),
                        "target_entity_id": str(relation.target_id),
                        "evidence_tier": evidence.evidence_tier,
                    },
                },
            )
        return records

    def _load_linked_provenance(
        self,
        *,
        run_id: str,
        research_space_id: str | None,
    ) -> list[JSONObject]:
        statement: Select[tuple[ProvenanceModel]] = select(ProvenanceModel).where(
            ProvenanceModel.extraction_run_id == run_id,
        )
        parsed_space_id = _parse_uuid(research_space_id)
        if parsed_space_id is not None:
            statement = statement.where(
                ProvenanceModel.research_space_id == parsed_space_id,
            )
        rows = self._session.execute(statement).scalars().all()
        return [
            {
                "record_type": "provenance",
                "record_id": str(row.id),
                "research_space_id": str(row.research_space_id),
                "source_id": None,
                "document_id": None,
                "source_type": row.source_type,
                "status": row.mapping_method,
                "label": row.source_ref,
                "created_at": _serialize_datetime(row.created_at),
                "updated_at": _serialize_datetime(row.created_at),
                "metadata": {
                    "mapping_confidence": row.mapping_confidence,
                    "agent_model": row.agent_model,
                    "source_ref": row.source_ref,
                },
            }
            for row in rows
        ]

    def _build_trace_payload(  # noqa: PLR0913 - explicit response shape is intentional
        self,
        *,
        requested_run_id: str,
        trace: ArtanaRunTraceRecord,
        candidate_run_ids: list[str],
        alerts: list[JSONObject],
        linked_records: list[JSONObject],
        raw_tables: list[AgentRunTableSummary] | None,
    ) -> JSONObject:
        source_ids = _unique_string_values(
            record.get("source_id") for record in linked_records
        )
        source_types = _unique_string_values(
            record.get("source_type") for record in linked_records
        )
        events = [
            _event_to_payload(event) for event in trace.events[-_TRACE_EVENT_LIMIT:]
        ]
        summaries = [
            _summary_to_payload(summary)
            for summary in trace.summaries
            if summary.summary_type in _ARTANA_SUMMARY_TYPES_OF_INTEREST
        ]
        if not summaries:
            summaries = [_summary_to_payload(summary) for summary in trace.summaries]
        payload: JSONObject = {
            "requested_run_id": requested_run_id,
            "run_id": trace.run_id,
            "candidate_run_ids": candidate_run_ids,
            "space_id": trace.tenant_id,
            "source_ids": source_ids,
            "source_types": source_types,
            "status": trace.status,
            "last_event_seq": trace.last_event_seq,
            "last_event_type": trace.last_event_type,
            "progress_percent": trace.progress_percent,
            "current_stage": trace.current_stage,
            "completed_stages": list(trace.completed_stages),
            "started_at": _serialize_datetime(trace.started_at),
            "updated_at": _serialize_datetime(trace.updated_at),
            "eta_seconds": trace.eta_seconds,
            "blocked_on": trace.blocked_on,
            "failure_reason": trace.failure_reason,
            "error_category": trace.error_category,
            "explain": trace.explain,
            "alerts": alerts,
            "events": events,
            "summaries": summaries,
            "linked_records": linked_records,
        }
        if raw_tables is not None:
            payload["raw_tables"] = [
                {
                    "table_name": table.table_name,
                    "row_count": table.row_count,
                    "latest_created_at": _serialize_datetime(table.latest_created_at),
                    "sample_rows": table.sample_rows,
                }
                for table in raw_tables
            ]
        return payload

    def _build_alerts(
        self,
        *,
        trace: ArtanaRunTraceRecord | None,
        fallback_snapshot: _RunSnapshotRow | None,
        now: datetime,
    ) -> list[JSONObject]:
        alerts: list[JSONObject] = []
        effective_status = (
            _normalize_effective_status(trace.status)
            if trace is not None
            else _normalize_effective_status(
                fallback_snapshot.status if fallback_snapshot is not None else None,
            )
        )
        updated_at = (
            trace.updated_at
            if trace is not None and trace.updated_at is not None
            else (
                fallback_snapshot.updated_at if fallback_snapshot is not None else None
            )
        )
        if effective_status == "failed":
            alerts.append(
                {
                    "code": "failed_run",
                    "severity": "error",
                    "title": "Run failed",
                    "description": (
                        trace.failure_reason
                        if trace is not None and trace.failure_reason is not None
                        else (
                            fallback_snapshot.failure_reason
                            if fallback_snapshot is not None
                            else "Run entered a terminal failure state."
                        )
                    ),
                    "triggered_at": _serialize_datetime(updated_at),
                    "metadata": {},
                },
            )
        if (
            effective_status in _NON_TERMINAL_STATUSES
            and updated_at is not None
            and now - updated_at >= _STUCK_RUN_AGE
        ):
            alerts.append(
                {
                    "code": "stuck_run",
                    "severity": "warning",
                    "title": "Run may be stuck",
                    "description": "Run is non-terminal and has not emitted a recent update.",
                    "triggered_at": _serialize_datetime(updated_at),
                    "metadata": {"updated_at": updated_at.isoformat()},
                },
            )
        unknown_outcome = (
            _resolve_unknown_outcome_alert(trace.events, now=now)
            if trace is not None
            else None
        )
        if unknown_outcome is not None:
            alerts.append(
                {
                    "code": "tool_unknown_outcome",
                    "severity": "warning",
                    "title": "Tool or model outcome is unknown",
                    "description": unknown_outcome["description"],
                    "triggered_at": unknown_outcome["triggered_at"],
                    "metadata": unknown_outcome["metadata"],
                },
            )
        if _has_drift_alert(trace=trace, fallback_snapshot=fallback_snapshot):
            alerts.append(
                {
                    "code": "drift_detected",
                    "severity": "warning",
                    "title": "Prompt or replay drift detected",
                    "description": "Run recorded drift or forked replay metadata.",
                    "triggered_at": _serialize_datetime(updated_at),
                    "metadata": {},
                },
            )
        budget_warning = _resolve_budget_warning(trace=trace)
        if budget_warning is not None:
            alerts.append(
                {
                    "code": "budget_warning",
                    "severity": "warning",
                    "title": "Run spend is nearing budget",
                    "description": budget_warning["description"],
                    "triggered_at": budget_warning["triggered_at"],
                    "metadata": budget_warning["metadata"],
                },
            )
        return alerts

    def _emit_alert_logs(
        self,
        *,
        run_id: str,
        space_id: str,
        alerts: list[JSONObject],
        linked_records: list[JSONObject],
    ) -> None:
        if not alerts:
            return
        source_ids = _unique_string_values(
            record.get("source_id") for record in linked_records
        )
        document_ids = _unique_string_values(
            record.get("document_id") for record in linked_records
        )
        for alert in alerts:
            payload = {
                "alert_code": alert.get("code"),
                "severity": alert.get("severity"),
                "run_id": run_id,
                "space_id": space_id,
                "source_ids": source_ids,
                "document_ids": document_ids,
                "metadata": as_object(to_json_value(alert.get("metadata"))),
            }
            message = json.dumps(payload, sort_keys=True)
            if alert.get("severity") == "error":
                alert_logger.error(message)
            else:
                alert_logger.warning(message)

    def _build_list_item(
        self,
        *,
        snapshot: _RunSnapshotRow,
        trace: ArtanaRunTraceRecord | None,
        linked_records: list[JSONObject],
        alerts: list[JSONObject],
    ) -> JSONObject:
        source_ids = _unique_string_values(
            record.get("source_id") for record in linked_records
        )
        source_types = _unique_string_values(
            record.get("source_type") for record in linked_records
        )
        alert_codes = [
            str(alert.get("code"))
            for alert in alerts
            if isinstance(alert.get("code"), str)
        ]
        return {
            "run_id": snapshot.run_id,
            "space_id": snapshot.tenant_id,
            "source_ids": source_ids,
            "source_type": source_types[0] if source_types else None,
            "status": (
                trace.status
                if trace is not None
                else _normalize_effective_status(snapshot.status)
            ),
            "current_stage": (
                trace.current_stage
                if trace is not None and trace.current_stage is not None
                else snapshot.last_stage
            ),
            "updated_at": _serialize_datetime(
                trace.updated_at if trace is not None else snapshot.updated_at,
            ),
            "started_at": _serialize_datetime(
                trace.started_at if trace is not None else None,
            ),
            "last_event_type": (
                trace.last_event_type
                if trace is not None and trace.last_event_type is not None
                else snapshot.last_event_type
            ),
            "alert_count": len(alert_codes),
            "alert_codes": alert_codes,
        }

    @staticmethod
    def _build_list_counters(items: list[JSONObject]) -> dict[str, int]:
        counters: dict[str, int] = {
            "running": 0,
            "failed": 0,
            "stuck": 0,
            "drift_detected": 0,
            "budget_warning": 0,
            "tool_unknown_outcome": 0,
        }
        for item in items:
            status = normalize_optional_string(item.get("status"))
            if status == "running":
                counters["running"] += 1
            if status == "failed":
                counters["failed"] += 1
            alert_codes = set(_string_list(item.get("alert_codes")))
            if "stuck_run" in alert_codes:
                counters["stuck"] += 1
            if "drift_detected" in alert_codes:
                counters["drift_detected"] += 1
            if "budget_warning" in alert_codes:
                counters["budget_warning"] += 1
            if "tool_unknown_outcome" in alert_codes:
                counters["tool_unknown_outcome"] += 1
        return counters


@dataclass(frozen=True, slots=True)
class _RunResolution:
    resolved_run_id: str
    candidate_run_ids: list[str]
    snapshot: _RunSnapshotRow | None


def _snapshot_from_row(row: RowMapping) -> _RunSnapshotRow:
    return _RunSnapshotRow(
        run_id=str(row["run_id"]),
        tenant_id=str(row["tenant_id"]),
        last_event_seq=_safe_int(row["last_event_seq"]),
        last_event_type=normalize_optional_string(row["last_event_type"]),
        updated_at=_coerce_datetime(row["updated_at"]),
        status=_normalize_effective_status(row["status"]) or "unknown",
        blocked_on=normalize_optional_string(row["blocked_on"]),
        failure_reason=normalize_optional_string(row["failure_reason"]),
        error_category=normalize_optional_string(row["error_category"]),
        diagnostics_json=normalize_optional_string(row["diagnostics_json"]),
        last_step_key=normalize_optional_string(row["last_step_key"]),
        drift_count=_safe_int(row["drift_count"]),
        last_stage=normalize_optional_string(row["last_stage"]),
        last_tool=normalize_optional_string(row["last_tool"]),
        model_cost_total=as_float(to_json_value(row["model_cost_total"])) or 0.0,
        open_pause_count=_safe_int(row["open_pause_count"]),
        explain_status=normalize_optional_string(row["explain_status"]),
        explain_failure_reason=normalize_optional_string(row["explain_failure_reason"]),
        explain_failure_step=normalize_optional_string(row["explain_failure_step"]),
    )


def _resolve_unknown_outcome_alert(  # noqa: C901 - pending request tracking is explicit
    events: tuple[ArtanaRunTraceEventRecord, ...],
    *,
    now: datetime,
) -> JSONObject | None:
    pending_requests: dict[str, ArtanaRunTraceEventRecord] = {}
    for event in events:
        if event.event_type == "tool_requested":
            pending_requests[event.event_id] = event
            continue
        if event.event_type == "tool_completed":
            request_id = normalize_optional_string(event.payload.get("request_id"))
            if request_id is not None:
                pending_requests.pop(request_id, None)
            continue
        if event.event_type == "model_requested":
            pending_requests[event.event_id] = event
            continue
        if event.event_type == "model_terminal":
            request_id = normalize_optional_string(
                event.payload.get("source_model_requested_event_id"),
            )
            if request_id is not None:
                pending_requests.pop(request_id, None)

    oldest_pending: ArtanaRunTraceEventRecord | None = None
    for pending in pending_requests.values():
        if now - pending.timestamp < _UNKNOWN_OUTCOME_AGE:
            continue
        if oldest_pending is None or pending.timestamp < oldest_pending.timestamp:
            oldest_pending = pending
    if oldest_pending is None:
        return None
    pending_label = oldest_pending.tool_name or oldest_pending.event_type
    return {
        "description": (
            f"Pending {pending_label} request has no terminal outcome after five minutes."
        ),
        "triggered_at": _serialize_datetime(oldest_pending.timestamp),
        "metadata": {
            "pending_event_id": oldest_pending.event_id,
            "pending_event_type": oldest_pending.event_type,
            "pending_tool_name": oldest_pending.tool_name,
        },
    }


def _resolve_budget_warning(
    *,
    trace: ArtanaRunTraceRecord | None,
) -> JSONObject | None:
    if trace is None:
        return None
    summary = next(
        (
            item
            for item in trace.summaries
            if item.summary_type in {"trace::cost", "trace::cost_snapshot"}
        ),
        None,
    )
    if summary is None:
        return None
    payload = as_object(to_json_value(summary.payload))
    cost_value = next(
        (
            as_float(payload.get(key))
            for key in _COST_KEYS
            if payload.get(key) is not None
        ),
        None,
    )
    budget_value = next(
        (
            as_float(payload.get(key))
            for key in _BUDGET_KEYS
            if payload.get(key) is not None
        ),
        None,
    )
    if cost_value is None or budget_value is None or budget_value <= 0:
        return None
    ratio = cost_value / budget_value
    if ratio < _BUDGET_WARNING_THRESHOLD:
        return None
    return {
        "description": (
            f"Run cost is {cost_value:.4f} USD against a {budget_value:.4f} USD budget."
        ),
        "triggered_at": _serialize_datetime(summary.timestamp),
        "metadata": {
            "cost_usd": cost_value,
            "budget_usd_limit": budget_value,
            "budget_ratio": ratio,
        },
    }


__all__ = ["ArtanaObservabilityService"]
