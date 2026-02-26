"""Read-only workflow monitoring service for source pipeline visibility."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ._source_workflow_monitor_pipeline import SourceWorkflowMonitorPipelineMixin
from ._source_workflow_monitor_relations import SourceWorkflowMonitorRelationsMixin
from ._source_workflow_monitor_shared import (
    coerce_json_list,
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


class SourceWorkflowMonitorService(
    SourceWorkflowMonitorPipelineMixin,
    SourceWorkflowMonitorRelationsMixin,
):
    """Aggregate workflow read models for one source inside one research space."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_pipeline_runs(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        limit: int,
    ) -> list[JSONObject]:
        self._require_source(space_id=space_id, source_id=source_id)
        return [
            record.payload
            for record in self._load_pipeline_runs(source_id=source_id, limit=limit)
        ]

    def list_workflow_events(  # noqa: C901, PLR0912, PLR0915 - explicit event shaping is intentional
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        run_id: str | None,
        limit: int,
        since: str | None,
    ) -> JSONObject:
        self._require_source(space_id=space_id, source_id=source_id)
        source_id_str = str(source_id)
        since_timestamp = _parse_timestamp(since) if since is not None else None
        if since is not None and since_timestamp is None:
            msg = "since must be a valid ISO-8601 datetime"
            raise ValueError(msg)

        load_limit = max(limit * 8, 300)
        run_records = self._load_pipeline_runs(source_id=source_id, limit=load_limit)
        selected_run = self._select_run_record(run_records, run_id)
        selected_run_id = selected_run.run_id if selected_run is not None else None

        events: list[tuple[datetime, JSONObject]] = []
        if selected_run is not None:
            run_payload = coerce_json_object(selected_run.payload)
            run_status = normalize_optional_string(run_payload.get("status"))
            run_event_time = (
                _parse_timestamp(run_payload.get("completed_at"))
                or _parse_timestamp(run_payload.get("started_at"))
                or _parse_timestamp(run_payload.get("triggered_at"))
            )
            if run_event_time is not None:
                events.append(
                    (
                        run_event_time,
                        {
                            "event_id": f"run:{selected_run.run_id}:{run_event_time.isoformat()}",
                            "source_id": source_id_str,
                            "run_id": selected_run.run_id,
                            "occurred_at": run_event_time.isoformat(),
                            "category": "run",
                            "stage": None,
                            "status": run_status,
                            "message": (
                                f"Pipeline run status: {run_status}"
                                if run_status is not None
                                else "Pipeline run status updated."
                            ),
                            "payload": {
                                "stage_statuses": coerce_json_object(
                                    run_payload.get("stage_statuses"),
                                ),
                                "stage_errors": coerce_json_object(
                                    run_payload.get("stage_errors"),
                                ),
                                "stage_counters": coerce_json_object(
                                    run_payload.get("stage_counters"),
                                ),
                            },
                        },
                    ),
                )

            stage_checkpoints = coerce_json_object(run_payload.get("stage_checkpoints"))
            for stage_name, raw_checkpoint in stage_checkpoints.items():
                checkpoint = coerce_json_object(raw_checkpoint)
                checkpoint_time = _parse_timestamp(checkpoint.get("updated_at"))
                if checkpoint_time is None:
                    continue
                stage_status = normalize_optional_string(checkpoint.get("status"))
                stage_error = normalize_optional_string(checkpoint.get("error"))
                stage_label = str(stage_name)
                status_label = stage_status or "updated"
                message = (
                    f"{stage_label} stage {status_label}: {stage_error}"
                    if stage_error is not None
                    else f"{stage_label} stage {status_label}."
                )
                events.append(
                    (
                        checkpoint_time,
                        {
                            "event_id": (
                                f"stage:{selected_run.run_id}:{stage_label}:"
                                f"{checkpoint_time.isoformat()}"
                            ),
                            "source_id": source_id_str,
                            "run_id": selected_run.run_id,
                            "occurred_at": checkpoint_time.isoformat(),
                            "category": "stage",
                            "stage": stage_label,
                            "status": stage_status,
                            "message": message,
                            "payload": checkpoint,
                        },
                    ),
                )

        documents = self._load_source_documents(
            source_id=source_id,
            run_id=selected_run_id,
            limit=load_limit,
        )
        external_record_to_document_id = {
            str(item["external_record_id"]): str(item["id"])
            for item in documents
            if isinstance(item.get("external_record_id"), str)
            and isinstance(item.get("id"), str)
        }
        for document in documents:
            updated_at = _parse_timestamp(document.get("updated_at"))
            if updated_at is None:
                continue
            document_id = normalize_optional_string(document.get("id")) or "unknown"
            external_record_id = (
                normalize_optional_string(document.get("external_record_id"))
                or document_id
            )
            enrichment_status = (
                normalize_optional_string(document.get("enrichment_status"))
                or "unknown"
            )
            extraction_status = (
                normalize_optional_string(document.get("extraction_status"))
                or "unknown"
            )
            stage = (
                "enrichment"
                if enrichment_status in {"pending", "in_progress", "failed", "skipped"}
                else "extraction"
            )
            events.append(
                (
                    updated_at,
                    {
                        "event_id": f"document:{document_id}:{updated_at.isoformat()}",
                        "source_id": source_id_str,
                        "run_id": selected_run_id,
                        "occurred_at": updated_at.isoformat(),
                        "category": "document",
                        "stage": stage,
                        "status": extraction_status,
                        "message": (
                            f"Document {external_record_id}: "
                            f"enrichment={enrichment_status}, extraction={extraction_status}."
                        ),
                        "payload": {
                            "document_id": document_id,
                            "external_record_id": external_record_id,
                            "enrichment_status": enrichment_status,
                            "extraction_status": extraction_status,
                        },
                    },
                ),
            )

        queue_rows = self._load_extraction_queue(
            source_id=source_id,
            run_id=selected_run_id,
            external_record_ids=set(external_record_to_document_id.keys()),
            limit=load_limit,
        )
        queue_id_to_document_id = {
            str(item["id"]): external_record_to_document_id[
                str(item["source_record_id"])
            ]
            for item in queue_rows
            if isinstance(item.get("id"), str)
            and isinstance(item.get("source_record_id"), str)
            and str(item["source_record_id"]) in external_record_to_document_id
        }
        for queue_item in queue_rows:
            event_time = (
                _parse_timestamp(queue_item.get("completed_at"))
                or _parse_timestamp(queue_item.get("started_at"))
                or _parse_timestamp(queue_item.get("queued_at"))
            )
            if event_time is None:
                continue
            queue_id = normalize_optional_string(queue_item.get("id")) or "unknown"
            queue_status = (
                normalize_optional_string(queue_item.get("status")) or "unknown"
            )
            source_record_id = (
                normalize_optional_string(queue_item.get("source_record_id"))
                or queue_id
            )
            queue_error = normalize_optional_string(queue_item.get("last_error"))
            message = (
                f"Queue item {source_record_id}: {queue_status} ({queue_error})."
                if queue_error is not None
                else f"Queue item {source_record_id}: {queue_status}."
            )
            events.append(
                (
                    event_time,
                    {
                        "event_id": f"queue:{queue_id}:{event_time.isoformat()}",
                        "source_id": source_id_str,
                        "run_id": selected_run_id,
                        "occurred_at": event_time.isoformat(),
                        "category": "queue",
                        "stage": "extraction",
                        "status": queue_status,
                        "message": message,
                        "payload": {
                            "queue_item_id": queue_id,
                            "source_record_id": source_record_id,
                            "attempts": safe_int(queue_item.get("attempts")),
                            "last_error": queue_error,
                        },
                    },
                ),
            )

        extraction_rows = self._load_publication_extractions(
            source_id=source_id,
            run_id=selected_run_id,
            queue_item_ids=set(queue_id_to_document_id.keys()),
            limit=load_limit,
        )
        for extraction in extraction_rows:
            extracted_at = _parse_timestamp(extraction.get("extracted_at"))
            if extracted_at is None:
                continue
            extraction_id = normalize_optional_string(extraction.get("id")) or "unknown"
            extraction_status = (
                normalize_optional_string(extraction.get("status")) or "unknown"
            )
            text_source = normalize_optional_string(extraction.get("text_source"))
            facts_count = safe_int(extraction.get("facts_count"))
            source_label = text_source if text_source is not None else "unknown"
            events.append(
                (
                    extracted_at,
                    {
                        "event_id": f"extraction:{extraction_id}:{extracted_at.isoformat()}",
                        "source_id": source_id_str,
                        "run_id": selected_run_id,
                        "occurred_at": extracted_at.isoformat(),
                        "category": "extraction",
                        "stage": "extraction",
                        "status": extraction_status,
                        "message": (
                            f"Extraction {extraction_status}: "
                            f"{facts_count} fact(s), text_source={source_label}."
                        ),
                        "payload": {
                            "extraction_id": extraction_id,
                            "queue_item_id": normalize_optional_string(
                                extraction.get("queue_item_id"),
                            ),
                            "facts_count": facts_count,
                            "text_source": text_source,
                            "processor_name": normalize_optional_string(
                                extraction.get("processor_name"),
                            ),
                            "processor_version": normalize_optional_string(
                                extraction.get("processor_version"),
                            ),
                        },
                    },
                ),
            )

        events.sort(key=lambda entry: entry[0], reverse=True)
        if since_timestamp is None:
            filtered_events = [event for _, event in events]
        else:
            filtered_events = [
                event for event_time, event in events if event_time > since_timestamp
            ]
        total = len(filtered_events)
        returned_events = filtered_events[: max(limit, 1)]
        return {
            "source_id": source_id_str,
            "run_id": selected_run_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "events": returned_events,
            "total": total,
            "has_more": total > len(returned_events),
        }

    def get_source_workflow_monitor(  # noqa: PLR0913, PLR0915 - explicit read model fields are intentional
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        run_id: str | None,
        limit: int,
        include_graph: bool,
    ) -> JSONObject:
        source = self._require_source(space_id=space_id, source_id=source_id)
        run_records = self._load_pipeline_runs(
            source_id=source_id,
            limit=max(limit * 4, 50),
        )
        selected_run = self._select_run_record(run_records, run_id)
        selected_run_id = selected_run.run_id if selected_run is not None else None

        documents = self._load_source_documents(
            source_id=source_id,
            run_id=selected_run_id,
            limit=limit,
        )
        document_status_counts = self._count_statuses(
            records=documents,
            key="extraction_status",
        )
        document_ids = {
            str(item["id"]) for item in documents if isinstance(item.get("id"), str)
        }
        external_record_to_document_id = {
            str(item["external_record_id"]): str(item["id"])
            for item in documents
            if isinstance(item.get("external_record_id"), str)
            and isinstance(item.get("id"), str)
        }

        queue_rows = self._load_extraction_queue(
            source_id=source_id,
            run_id=selected_run_id,
            external_record_ids=set(external_record_to_document_id.keys()),
            limit=limit,
        )
        queue_status_counts = self._count_statuses(records=queue_rows, key="status")
        queue_id_to_document_id = {
            str(item["id"]): external_record_to_document_id[
                str(item["source_record_id"])
            ]
            for item in queue_rows
            if isinstance(item.get("id"), str)
            and isinstance(item.get("source_record_id"), str)
            and str(item["source_record_id"]) in external_record_to_document_id
        }

        extraction_rows = self._load_publication_extractions(
            source_id=source_id,
            run_id=selected_run_id,
            queue_item_ids=set(queue_id_to_document_id.keys()),
            limit=limit,
        )
        extraction_status_counts = self._count_statuses(
            records=extraction_rows,
            key="status",
        )

        relation_review_payload = self._build_relation_review_payload(
            space_id=space_id,
            document_ids=document_ids,
            document_external_record_id_by_id={
                str(item["id"]): str(item["external_record_id"])
                for item in documents
                if isinstance(item.get("id"), str)
                and isinstance(item.get("external_record_id"), str)
            },
            queue_id_to_document_id=queue_id_to_document_id,
            extraction_rows=extraction_rows,
            limit=limit,
        )
        relation_rows = coerce_json_list(
            relation_review_payload.get("persisted_relation_rows"),
        )
        relation_edge_delta = len(
            {
                str(coerce_json_object(item).get("relation_id"))
                for item in relation_rows
                if normalize_optional_string(
                    coerce_json_object(item).get("relation_id"),
                )
                is not None
            },
        )

        graph_summary = (
            self._build_graph_summary(space_id=space_id, source_id=source_id)
            if include_graph
            else None
        )
        warnings = self._build_warnings(extraction_rows=extraction_rows)
        operational_counters = self._build_operational_counters(
            space_id=space_id,
            source_id=source_id,
            selected_run=selected_run,
            graph_summary=graph_summary,
            relation_edge_delta=relation_edge_delta,
        )

        return {
            "source_snapshot": self._build_source_snapshot(source),
            "last_run": selected_run.payload if selected_run is not None else None,
            "pipeline_runs": [record.payload for record in run_records[:limit]],
            "documents": documents,
            "document_status_counts": document_status_counts,
            "extraction_queue": queue_rows,
            "extraction_queue_status_counts": queue_status_counts,
            "publication_extractions": extraction_rows,
            "publication_extraction_status_counts": extraction_status_counts,
            "relation_review": relation_review_payload,
            "graph_summary": graph_summary,
            "operational_counters": operational_counters,
            "warnings": warnings,
        }


def _parse_timestamp(raw_value: object) -> datetime | None:
    if isinstance(raw_value, datetime):
        return (
            raw_value if raw_value.tzinfo is not None else raw_value.replace(tzinfo=UTC)
        )
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    candidate = normalized[:-1] + "+00:00" if normalized.endswith("Z") else normalized
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


__all__ = ["SourceWorkflowMonitorService"]
