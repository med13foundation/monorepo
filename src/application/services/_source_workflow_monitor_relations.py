"""Relation/graph/review helpers for source workflow monitor."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from sqlalchemy import desc, func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import aliased

from src.models.database.extraction_queue import (
    ExtractionQueueItemModel,
    ExtractionStatusEnum,
)
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel
from src.models.database.review import ReviewRecord
from src.models.database.source_document import SourceDocumentModel

from ._source_workflow_monitor_shared import (
    PENDING_DOCUMENT_STATUSES,
    PENDING_RELATION_STATUSES,
    PipelineRunRecord,
    coerce_json_list,
    coerce_json_object,
    normalize_optional_string,
    parse_uuid_runtime,
    safe_int,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject
else:
    JSONObject = dict[str, object]  # Runtime type stub

_PENDING_QUEUE_STATUSES: tuple[ExtractionStatusEnum, ...] = (
    ExtractionStatusEnum.PENDING,
    ExtractionStatusEnum.PROCESSING,
)


class SourceWorkflowMonitorRelationsMixin:
    """Relation and graph summarization helpers for workflow monitor."""

    _session: Session

    def _build_relation_review_payload(  # noqa: PLR0913 - explicit inputs improve readability
        self,
        *,
        space_id: UUID,
        document_ids: set[str],
        document_external_record_id_by_id: dict[str, str],
        queue_id_to_document_id: dict[str, str],
        extraction_rows: list[JSONObject],
        limit: int,
    ) -> JSONObject:
        persisted = self._load_document_relations(
            space_id=space_id,
            document_ids=document_ids,
            document_external_record_id_by_id=document_external_record_id_by_id,
            limit=limit,
        )
        pending_relation_ids = {
            str(item["relation_id"])
            for item in persisted
            if isinstance(item.get("relation_id"), str)
            and str(item.get("curation_status")) in PENDING_RELATION_STATUSES
        }
        pending_relations = [
            item
            for item in persisted
            if item.get("relation_id") in pending_relation_ids
        ]
        rejected_by_document, rejected_reason_counts = (
            self._extract_rejected_relation_details(
                extraction_rows=extraction_rows,
                queue_id_to_document_id=queue_id_to_document_id,
            )
        )
        review_queue = self._load_relation_review_queue(space_id=space_id, limit=limit)
        return {
            "persisted_relation_rows": persisted,
            "pending_review_relation_rows": pending_relations,
            "pending_review_relation_count": len(pending_relation_ids),
            "review_queue_rows": review_queue,
            "rejected_relation_rows": rejected_by_document,
            "rejected_reason_counts": rejected_reason_counts,
        }

    def _load_document_relations(
        self,
        *,
        space_id: UUID,
        document_ids: set[str],
        document_external_record_id_by_id: dict[str, str],
        limit: int,
    ) -> list[JSONObject]:
        if not document_ids:
            return []
        document_uuid_to_id = {
            parsed_uuid: document_id
            for document_id in document_ids
            if (parsed_uuid := parse_uuid_runtime(document_id)) is not None
        }
        if not document_uuid_to_id:
            return []

        source_entity = aliased(EntityModel)
        target_entity = aliased(EntityModel)
        statement = (
            select(
                RelationEvidenceModel.source_document_id,
                RelationModel.id,
                RelationModel.relation_type,
                RelationModel.curation_status,
                RelationModel.aggregate_confidence,
                RelationModel.source_id,
                RelationModel.target_id,
                RelationEvidenceModel.id,
                RelationEvidenceModel.confidence,
                RelationEvidenceModel.evidence_summary,
                RelationEvidenceModel.agent_run_id,
                source_entity.display_label,
                target_entity.display_label,
            )
            .join(
                RelationModel,
                RelationModel.id == RelationEvidenceModel.relation_id,
            )
            .outerjoin(source_entity, source_entity.id == RelationModel.source_id)
            .outerjoin(target_entity, target_entity.id == RelationModel.target_id)
            .where(RelationEvidenceModel.source_document_id.in_(document_uuid_to_id))
            .where(RelationModel.research_space_id == space_id)
            .order_by(desc(RelationEvidenceModel.created_at))
            .limit(max(limit, 1) * 20)
        )
        rows = self._session.execute(statement).all()
        return [
            {
                "document_id": document_uuid_to_id.get(row[0], str(row[0])),
                "external_record_id": document_external_record_id_by_id.get(
                    document_uuid_to_id.get(row[0], str(row[0])),
                ),
                "relation_id": str(row[1]),
                "relation_type": row[2],
                "curation_status": row[3],
                "aggregate_confidence": float(row[4] or 0.0),
                "source_entity_id": str(row[5]),
                "target_entity_id": str(row[6]),
                "evidence_id": str(row[7]),
                "evidence_confidence": float(row[8] or 0.0),
                "evidence_summary": row[9],
                "agent_run_id": row[10],
                "source_entity_label": row[11],
                "target_entity_label": row[12],
            }
            for row in rows
        ]

    def _extract_rejected_relation_details(
        self,
        *,
        extraction_rows: list[JSONObject],
        queue_id_to_document_id: dict[str, str],
    ) -> tuple[list[JSONObject], dict[str, int]]:
        rows: list[JSONObject] = []
        reason_counter: Counter[str] = Counter()
        for extraction in extraction_rows:
            extraction_metadata = coerce_json_object(extraction.get("metadata"))
            rejected_details = coerce_json_list(
                extraction_metadata.get("extraction_stage_rejected_relation_details"),
            )
            queue_item_id = normalize_optional_string(extraction.get("queue_item_id"))
            document_id = (
                queue_id_to_document_id.get(queue_item_id)
                if queue_item_id is not None
                else None
            )
            for detail in rejected_details:
                detail_payload = coerce_json_object(detail)
                reason = (
                    normalize_optional_string(detail_payload.get("reason")) or "unknown"
                )
                reason_counter[reason] += 1
                rows.append(
                    {
                        "document_id": document_id,
                        "queue_item_id": queue_item_id,
                        "extraction_id": extraction.get("id"),
                        "reason": reason,
                        "status": normalize_optional_string(
                            detail_payload.get("status"),
                        ),
                        "payload": coerce_json_object(detail_payload.get("payload")),
                    },
                )
        return rows, dict(reason_counter)

    def _load_relation_review_queue(
        self,
        *,
        space_id: UUID,
        limit: int,
    ) -> list[JSONObject]:
        statement = (
            select(ReviewRecord)
            .where(ReviewRecord.research_space_id == str(space_id))
            .where(ReviewRecord.status == "pending")
            .order_by(desc(ReviewRecord.last_updated))
            .limit(max(limit, 1) * 3)
        )
        try:
            rows = self._session.execute(statement).scalars().all()
        except (OperationalError, ProgrammingError):
            self._session.rollback()
            return []

        payload: list[JSONObject] = []
        for row in rows:
            if "relation" not in row.entity_type.lower():
                continue
            payload.append(
                {
                    "id": int(row.id),
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "priority": row.priority,
                    "status": row.status,
                    "issues": int(row.issues),
                    "quality_score": row.quality_score,
                    "last_updated": row.last_updated.isoformat(),
                },
            )
        return payload

    def _build_graph_summary(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
    ) -> JSONObject:
        node_count_stmt = (
            select(func.count())
            .select_from(EntityModel)
            .where(EntityModel.research_space_id == space_id)
        )
        edge_count_stmt = (
            select(func.count())
            .select_from(RelationModel)
            .where(RelationModel.research_space_id == space_id)
        )
        top_types_stmt = (
            select(RelationModel.relation_type, func.count(RelationModel.id))
            .where(RelationModel.research_space_id == space_id)
            .group_by(RelationModel.relation_type)
            .order_by(desc(func.count(RelationModel.id)))
            .limit(10)
        )

        node_count = int(self._session.execute(node_count_stmt).scalar_one() or 0)
        edge_count = int(self._session.execute(edge_count_stmt).scalar_one() or 0)
        source_document_ids = self._load_source_document_uuid_ids(source_id=source_id)
        if source_document_ids:
            source_edge_stmt = (
                select(func.count(func.distinct(RelationModel.id)))
                .select_from(RelationModel)
                .join(
                    RelationEvidenceModel,
                    RelationEvidenceModel.relation_id == RelationModel.id,
                )
                .where(RelationModel.research_space_id == space_id)
                .where(
                    RelationEvidenceModel.source_document_id.in_(source_document_ids),
                )
            )
            source_edge_count = int(
                self._session.execute(source_edge_stmt).scalar_one() or 0,
            )
        else:
            source_edge_count = 0
        top_relation_types = [
            {"relation_type": relation_type, "count": int(count)}
            for relation_type, count in self._session.execute(top_types_stmt).all()
        ]
        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "source_edge_count": source_edge_count,
            "top_relation_types": top_relation_types,
        }

    def _build_operational_counters(  # noqa: PLR0913 - explicit counters are intentional
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        selected_run: PipelineRunRecord | None,
        graph_summary: JSONObject | None,
        relation_edge_delta: int,
    ) -> JSONObject:
        pending_documents = self._count_pending_documents(source_id=source_id)
        pending_queue = self._count_pending_queue_items(source_id=source_id)
        pending_relation_reviews = self._count_pending_relation_reviews(
            space_id=space_id,
            source_id=source_id,
        )
        graph_edges_total = (
            safe_int(graph_summary.get("edge_count"))
            if graph_summary is not None
            else 0
        )
        graph_edges_for_source = (
            safe_int(graph_summary.get("source_edge_count"))
            if graph_summary is not None
            else 0
        )
        stage_counters = (
            coerce_json_object(selected_run.payload.get("stage_counters"))
            if selected_run is not None
            else {}
        )
        return {
            "last_pipeline_status": (
                normalize_optional_string(selected_run.payload.get("status"))
                if selected_run is not None
                else None
            ),
            "pending_paper_count": pending_documents + pending_queue,
            "pending_document_count": pending_documents,
            "pending_queue_count": pending_queue,
            "pending_relation_review_count": pending_relation_reviews,
            "graph_edges_total": graph_edges_total,
            "graph_edges_for_source": graph_edges_for_source,
            "graph_edges_delta_last_run": max(relation_edge_delta, 0),
            "stage_counters": stage_counters,
        }

    def _build_warnings(self, *, extraction_rows: list[JSONObject]) -> list[str]:
        warnings: list[str] = []
        no_full_text_count = 0
        all_rejected_count = 0

        for extraction in extraction_rows:
            text_source = normalize_optional_string(extraction.get("text_source"))
            if text_source == "abstract":
                no_full_text_count += 1
            metadata = coerce_json_object(extraction.get("metadata"))
            funnel = coerce_json_object(metadata.get("extraction_stage_funnel"))
            generated = safe_int(funnel.get("relation_candidates_generated"))
            persisted = safe_int(funnel.get("relation_candidates_persisted"))
            if generated > 0 and persisted == 0:
                all_rejected_count += 1

        if no_full_text_count > 0:
            warnings.append(
                (
                    f"{no_full_text_count} extraction(s) used abstract-only text because "
                    "full text was unavailable."
                ),
            )
        if all_rejected_count > 0:
            warnings.append(
                (
                    f"{all_rejected_count} extraction(s) generated relation candidates "
                    "but persisted zero relations."
                ),
            )
        return warnings

    def _count_pending_documents(self, *, source_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(SourceDocumentModel)
            .where(SourceDocumentModel.source_id == str(source_id))
            .where(
                SourceDocumentModel.extraction_status.in_(PENDING_DOCUMENT_STATUSES),
            )
        )
        return int(self._session.execute(statement).scalar_one() or 0)

    def _count_pending_queue_items(self, *, source_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(ExtractionQueueItemModel)
            .where(ExtractionQueueItemModel.source_id == str(source_id))
            .where(
                ExtractionQueueItemModel.status.in_(_PENDING_QUEUE_STATUSES),
            )
        )
        return int(self._session.execute(statement).scalar_one() or 0)

    def _count_pending_relation_reviews(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
    ) -> int:
        source_document_ids = self._load_source_document_uuid_ids(source_id=source_id)
        if not source_document_ids:
            return 0
        statement = (
            select(func.count(func.distinct(RelationModel.id)))
            .select_from(RelationModel)
            .join(
                RelationEvidenceModel,
                RelationEvidenceModel.relation_id == RelationModel.id,
            )
            .where(RelationModel.research_space_id == space_id)
            .where(RelationModel.curation_status.in_(PENDING_RELATION_STATUSES))
            .where(RelationEvidenceModel.source_document_id.in_(source_document_ids))
        )
        return int(self._session.execute(statement).scalar_one() or 0)

    def _load_source_document_uuid_ids(self, *, source_id: UUID) -> list[UUID]:
        statement = select(SourceDocumentModel.id).where(
            SourceDocumentModel.source_id == str(source_id),
        )
        raw_ids = self._session.execute(statement).scalars().all()
        return [
            parsed_uuid
            for raw_id in raw_ids
            if (parsed_uuid := parse_uuid_runtime(raw_id)) is not None
        ]


__all__ = ["SourceWorkflowMonitorRelationsMixin"]
