"""Read-only workflow monitoring service for source pipeline visibility."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._source_workflow_monitor_events import SourceWorkflowMonitorEventsMixin
from ._source_workflow_monitor_progress import SourceWorkflowMonitorProgressMixin
from ._source_workflow_monitor_relations import SourceWorkflowMonitorRelationsMixin
from ._source_workflow_monitor_shared import (
    coerce_json_list,
    coerce_json_object,
    normalize_optional_string,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.application.services.ports.run_progress_port import RunProgressPort
    from src.type_definitions.common import JSONObject
else:
    JSONObject = dict[str, object]  # Runtime type stub


class SourceWorkflowMonitorService(
    SourceWorkflowMonitorEventsMixin,
    SourceWorkflowMonitorRelationsMixin,
    SourceWorkflowMonitorProgressMixin,
):
    """Aggregate workflow read models for one source inside one research space."""

    def __init__(
        self,
        session: Session,
        *,
        run_progress: RunProgressPort | None = None,
    ) -> None:
        self._session = session
        self._run_progress = run_progress

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
        selected_run_job_id = selected_run.job_id if selected_run is not None else None
        selected_run_payload = (
            coerce_json_object(selected_run.payload) if selected_run is not None else {}
        )
        selected_run_ingestion_job_id = normalize_optional_string(
            selected_run_payload.get("ingestion_job_id"),
        )
        run_scoped_ingestion_job_id = (
            selected_run_ingestion_job_id
            if selected_run_ingestion_job_id is not None
            else (None if selected_run_id is not None else selected_run_job_id)
        )

        documents = self._load_source_documents(
            source_id=source_id,
            run_id=selected_run_id,
            ingestion_job_id=run_scoped_ingestion_job_id,
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
            ingestion_job_id=run_scoped_ingestion_job_id,
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
            ingestion_job_id=run_scoped_ingestion_job_id,
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
        relation_rows = [
            coerce_json_object(item)
            for item in coerce_json_list(
                relation_review_payload.get("persisted_relation_rows"),
            )
        ]
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
            selected_run_id=selected_run_id,
            selected_ingestion_job_id=run_scoped_ingestion_job_id,
        )
        artana_progress = self._build_artana_progress(
            selected_run_id=selected_run_id,
            selected_run_payload=(
                selected_run.payload if selected_run is not None else None
            ),
            documents=documents,
            extraction_rows=extraction_rows,
            relation_rows=relation_rows,
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
            "artana_progress": artana_progress,
            "warnings": warnings,
        }


__all__ = ["SourceWorkflowMonitorService"]
