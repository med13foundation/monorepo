"""Run or reuse a one-paper PubMed workflow and emit a detailed MED13 report."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import desc, func, inspect, or_, select
from sqlalchemy.orm import aliased

from src.database.session import SessionLocal, set_session_rls_context
from src.models.database.extraction_queue import ExtractionQueueItemModel
from src.models.database.ingestion_job import IngestionJobModel
from src.models.database.kernel.dictionary import (
    DictionaryChangelogModel,
    DictionaryEntityTypeModel,
    DictionaryRelationTypeModel,
    RelationConstraintModel,
    ValueSetItemModel,
    ValueSetModel,
    VariableDefinitionModel,
    VariableSynonymModel,
)
from src.models.database.kernel.entities import EntityIdentifierModel, EntityModel
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel
from src.models.database.publication import PublicationModel
from src.models.database.publication_extraction import PublicationExtractionModel
from src.models.database.source_document import SourceDocumentModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject, JSONValue

logger = logging.getLogger(__name__)
_DEFAULT_ONE_PAPER = 1
_DEFAULT_GRAPH_DEPTH = 2
_MAX_EDGE_ROWS = 200
_WINDOW_PADDING_MINUTES = 1
_DICTIONARY_SCAN_LIMIT = 300
_MAX_TRIMMED_LIST_ITEMS = 10
_MAX_TRIMMED_TEXT_CHARS = 500
_YEAR_PREFIX_LENGTH = 4


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a transparent one-paper MED13 report from PubMed workflow output."
        ),
    )
    parser.add_argument(
        "--source-id",
        type=UUID,
        default=None,
        help="Optional source id. If omitted, workflow resolver selects an active PubMed source.",
    )
    parser.add_argument(
        "--space-id",
        type=UUID,
        default=None,
        help="Optional research space id (must match source when source is provided).",
    )
    parser.add_argument(
        "--source-type",
        choices=("pubmed", "clinvar"),
        default="pubmed",
        help="Connector source type for workflow execution. Default: pubmed.",
    )
    parser.add_argument(
        "--pmid",
        type=str,
        default=None,
        help=(
            "Optional PubMed ID strict filter for deterministic one-paper tests. "
            "Applies only for pubmed runs."
        ),
    )
    parser.add_argument(
        "--workflow-log",
        type=Path,
        default=None,
        help=(
            "Reuse an existing minimal workflow JSON log. "
            "When provided, skips new pipeline execution."
        ),
    )
    parser.add_argument(
        "--max-ingestion-results",
        type=int,
        default=_DEFAULT_ONE_PAPER,
        help="Cap ingestion results for the workflow run (default: 1).",
    )
    parser.add_argument(
        "--enrichment-limit",
        type=int,
        default=_DEFAULT_ONE_PAPER,
        help="Enrichment limit for the workflow run (default: 1).",
    )
    parser.add_argument(
        "--extraction-limit",
        type=int,
        default=_DEFAULT_ONE_PAPER,
        help="Extraction limit for the workflow run (default: 1).",
    )
    parser.add_argument(
        "--graph-max-depth",
        type=int,
        default=_DEFAULT_GRAPH_DEPTH,
        help="Graph stage max depth for the workflow run (default: 2).",
    )
    parser.add_argument(
        "--shadow-mode",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Force orchestration shadow mode on/off (default: false).",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=None,
        help="Final detailed JSON report output path.",
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=None,
        help="Final detailed Markdown report output path.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--low-call-mode",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Reduce AI graph-call budgets for smoke tests while keeping AI enabled.",
    )
    parser.add_argument(
        "--require-smoke-pass",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Fail when neither a relation edge is persisted nor explicit rejected "
            "relation reasons/details are present."
        ),
    )
    return parser.parse_args()


def _configure_logging(*, verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def _default_output_paths() -> tuple[Path, Path]:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = Path("logs") / f"med13_one_paper_report_{timestamp}"
    return (base.with_suffix(".json"), base.with_suffix(".md"))


def _to_json_compatible(value: object) -> JSONValue:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): _to_json_compatible(item_value)
            for key, item_value in value.items()
        }
    if isinstance(value, list | tuple):
        return [_to_json_compatible(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _parse_iso_datetime(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_pmid(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    if not normalized.isdigit():
        msg = f"Invalid PMID value: {raw_value!r}. Expected digits only."
        raise ValueError(msg)
    return normalized


def _run_minimal_workflow_and_load_log(args: argparse.Namespace) -> JSONObject:
    if args.workflow_log is not None:
        logger.info("Reusing existing workflow log: %s", args.workflow_log)
        return _load_json_file(args.workflow_log)

    workflow_log_path = Path("logs") / (
        f"minimal_full_workflow_med13_one_paper_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    workflow_script = Path(__file__).with_name("run_minimal_full_workflow.py")
    command: list[str] = [
        sys.executable,
        str(workflow_script),
        "--source-type",
        str(args.source_type),
        "--max-ingestion-results",
        str(args.max_ingestion_results),
        "--enrichment-limit",
        str(args.enrichment_limit),
        "--extraction-limit",
        str(args.extraction_limit),
        "--graph-max-depth",
        str(args.graph_max_depth),
        "--log-file",
        str(workflow_log_path),
        "--disable-post-ingestion-hook",
    ]
    if args.source_id is not None:
        command.extend(["--source-id", str(args.source_id)])
    if args.space_id is not None:
        command.extend(["--space-id", str(args.space_id)])
    if args.pmid is not None:
        command.extend(["--pmid", str(args.pmid)])
    command.append("--low-call-mode" if args.low_call_mode else "--no-low-call-mode")
    command.append("--shadow-mode" if args.shadow_mode else "--no-shadow-mode")
    command.append("--require-graph-success")
    if args.verbose:
        command.append("--verbose")

    logger.info("Executing one-paper workflow command.")
    subprocess.run(command, check=True)  # noqa: S603
    logger.info("Workflow log written to: %s", workflow_log_path)
    return _load_json_file(workflow_log_path)


def _load_json_file(path: Path) -> JSONObject:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"Expected JSON object in {path}, found {type(payload).__name__}."
        raise TypeError(msg)
    return {str(key): value for key, value in payload.items()}


def _select_source_document(
    session: Session,
    *,
    source_id: UUID,
    pipeline_run_id: str | None,
) -> SourceDocumentModel | None:
    documents = (
        session.execute(
            select(SourceDocumentModel)
            .where(SourceDocumentModel.source_id == str(source_id))
            .order_by(desc(SourceDocumentModel.updated_at))
            .limit(100),
        )
        .scalars()
        .all()
    )
    if not documents:
        return None
    if pipeline_run_id:
        for document in documents:
            metadata_payload = document.metadata_payload
            if (
                isinstance(metadata_payload, dict)
                and metadata_payload.get("pipeline_run_id") == pipeline_run_id
            ):
                return document
    return documents[0]


def _select_ingestion_job_for_run_window(
    session: Session,
    *,
    source_id: UUID,
    started_at: datetime | None,
    completed_at: datetime | None,
) -> IngestionJobModel | None:
    rows = (
        session.execute(
            select(IngestionJobModel)
            .where(IngestionJobModel.source_id == str(source_id))
            .order_by(desc(IngestionJobModel.triggered_at))
            .limit(_DICTIONARY_SCAN_LIMIT),
        )
        .scalars()
        .all()
    )
    if not rows:
        return None

    completed_rows = [
        row for row in rows if str(row.status).lower().endswith("completed")
    ]
    candidates = completed_rows if completed_rows else rows
    if started_at is None or completed_at is None:
        return candidates[0]

    window_start = started_at - timedelta(minutes=_WINDOW_PADDING_MINUTES)
    window_end = completed_at + timedelta(minutes=_WINDOW_PADDING_MINUTES)

    for row in candidates:
        job_times = (
            _parse_iso_datetime(row.triggered_at),
            _parse_iso_datetime(row.started_at),
            _parse_iso_datetime(row.completed_at),
        )
        for job_time in job_times:
            if job_time is None:
                continue
            if window_start <= job_time <= window_end:
                return row
    return candidates[0]


def _select_source_document_for_ingestion_job(
    session: Session,
    *,
    source_id: UUID,
    ingestion_job_id: str | None,
) -> SourceDocumentModel | None:
    if not ingestion_job_id:
        return None
    return session.execute(
        select(SourceDocumentModel)
        .where(SourceDocumentModel.source_id == str(source_id))
        .where(SourceDocumentModel.ingestion_job_id == ingestion_job_id)
        .order_by(desc(SourceDocumentModel.updated_at))
        .limit(1),
    ).scalar_one_or_none()


def _select_queue_item(
    session: Session,
    *,
    source_id: UUID,
    external_record_id: str,
) -> ExtractionQueueItemModel | None:
    return session.execute(
        select(ExtractionQueueItemModel)
        .where(ExtractionQueueItemModel.source_id == str(source_id))
        .where(ExtractionQueueItemModel.source_record_id == external_record_id)
        .order_by(desc(ExtractionQueueItemModel.updated_at))
        .limit(1),
    ).scalar_one_or_none()


def _select_queue_item_for_ingestion_job(
    session: Session,
    *,
    source_id: UUID,
    ingestion_job_id: str | None,
    external_record_id: str | None = None,
) -> ExtractionQueueItemModel | None:
    if not ingestion_job_id:
        return None
    stmt = (
        select(ExtractionQueueItemModel)
        .where(ExtractionQueueItemModel.source_id == str(source_id))
        .where(ExtractionQueueItemModel.ingestion_job_id == ingestion_job_id)
    )
    if isinstance(external_record_id, str) and external_record_id.strip():
        stmt = stmt.where(
            ExtractionQueueItemModel.source_record_id == external_record_id,
        )
    return session.execute(
        stmt.order_by(desc(ExtractionQueueItemModel.updated_at)).limit(1),
    ).scalar_one_or_none()


def _select_queue_item_for_run_window(
    session: Session,
    *,
    source_id: UUID,
    started_at: datetime | None,
    completed_at: datetime | None,
) -> ExtractionQueueItemModel | None:
    rows = (
        session.execute(
            select(ExtractionQueueItemModel)
            .where(ExtractionQueueItemModel.source_id == str(source_id))
            .order_by(desc(ExtractionQueueItemModel.updated_at))
            .limit(_DICTIONARY_SCAN_LIMIT),
        )
        .scalars()
        .all()
    )
    if not rows:
        return None

    completed_rows = [
        row for row in rows if str(row.status).lower().endswith("completed")
    ]
    if started_at is None or completed_at is None:
        return completed_rows[0] if completed_rows else rows[0]

    window_start = started_at - timedelta(minutes=_WINDOW_PADDING_MINUTES)
    window_end = completed_at + timedelta(minutes=_WINDOW_PADDING_MINUTES)
    for row in completed_rows:
        updated_at = _as_utc(row.updated_at)
        if window_start <= updated_at <= window_end:
            return row
    return completed_rows[0] if completed_rows else rows[0]


def _select_source_document_for_queue_item(
    session: Session,
    *,
    source_id: UUID,
    queue_item: ExtractionQueueItemModel | None,
) -> SourceDocumentModel | None:
    if queue_item is None:
        return None
    return session.execute(
        select(SourceDocumentModel)
        .where(SourceDocumentModel.source_id == str(source_id))
        .where(SourceDocumentModel.external_record_id == queue_item.source_record_id)
        .order_by(desc(SourceDocumentModel.updated_at))
        .limit(1),
    ).scalar_one_or_none()


def _select_publication_extraction(
    session: Session,
    *,
    queue_item_id: str | None,
) -> PublicationExtractionModel | None:
    if queue_item_id is None:
        return None
    return session.execute(
        select(PublicationExtractionModel)
        .where(PublicationExtractionModel.queue_item_id == queue_item_id)
        .order_by(desc(PublicationExtractionModel.extracted_at))
        .limit(1),
    ).scalar_one_or_none()


def _extract_pubmed_id(
    *,
    queue_item: ExtractionQueueItemModel | None,
    source_document: SourceDocumentModel | None,
) -> str | None:
    if queue_item is not None and queue_item.pubmed_id:
        return queue_item.pubmed_id.strip()
    if source_document is None:
        return None
    metadata_payload = source_document.metadata_payload
    if isinstance(metadata_payload, dict):
        raw_record = metadata_payload.get("raw_record")
        if isinstance(raw_record, dict):
            value = raw_record.get("pubmed_id")
            if isinstance(value, str) and value.strip():
                return value.strip()
    parts = source_document.external_record_id.split(":")
    if parts:
        candidate = parts[-1].strip()
        if candidate.isdigit():
            return candidate
    return None


def _select_publication(
    session: Session,
    *,
    pubmed_id: str | None,
) -> PublicationModel | None:
    if pubmed_id is None or not _table_exists(session, "publications"):
        return None
    return session.execute(
        select(PublicationModel)
        .where(PublicationModel.pubmed_id == pubmed_id)
        .limit(1),
    ).scalar_one_or_none()


def _table_exists(session: Session, table_name: str) -> bool:
    bind = session.get_bind()
    return bool(inspect(bind).has_table(table_name))


def _safe_uuid(raw_value: str | None) -> UUID | None:
    if raw_value is None:
        return None
    try:
        return UUID(raw_value)
    except ValueError:
        return None


def _serialize_edge_row(  # noqa: PLR0913
    relation: RelationModel,
    *,
    source_label: str | None,
    source_type: str,
    target_label: str | None,
    target_type: str,
    evidence_items: list[JSONObject],
) -> JSONObject:
    return {
        "relation_id": str(relation.id),
        "relation_type": relation.relation_type,
        "curation_status": relation.curation_status,
        "aggregate_confidence": relation.aggregate_confidence,
        "source": {
            "id": str(relation.source_id),
            "label": source_label,
            "entity_type": source_type,
        },
        "target": {
            "id": str(relation.target_id),
            "label": target_label,
            "entity_type": target_type,
        },
        "evidence": evidence_items,
    }


def _load_relation_evidence_map(
    session: Session,
    *,
    relation_ids: list[UUID],
) -> dict[UUID, list[JSONObject]]:
    if not relation_ids:
        return {}
    evidence_rows = (
        session.execute(
            select(RelationEvidenceModel).where(
                RelationEvidenceModel.relation_id.in_(relation_ids),
            ),
        )
        .scalars()
        .all()
    )
    evidence_map: dict[UUID, list[JSONObject]] = {}
    for evidence in evidence_rows:
        relation_key = evidence.relation_id
        evidence_map.setdefault(relation_key, []).append(
            {
                "id": str(evidence.id),
                "confidence": evidence.confidence,
                "evidence_tier": evidence.evidence_tier,
                "summary": evidence.evidence_summary,
                "source_document_id": (
                    str(evidence.source_document_id)
                    if evidence.source_document_id is not None
                    else None
                ),
                "agent_run_id": (
                    str(evidence.agent_run_id)
                    if evidence.agent_run_id is not None
                    else None
                ),
                "created_at": evidence.created_at.isoformat(),
            },
        )
    return evidence_map


def _collect_document_relation_edges(
    session: Session,
    *,
    research_space_id: UUID,
    source_document_id: str | None,
) -> list[JSONObject]:
    document_uuid = _safe_uuid(source_document_id)
    if document_uuid is None:
        return []
    evidence_rows = session.execute(
        select(RelationEvidenceModel.relation_id).where(
            RelationEvidenceModel.source_document_id == document_uuid,
        ),
    ).all()
    relation_ids = [row[0] for row in evidence_rows if isinstance(row[0], UUID)]
    if not relation_ids:
        return []

    src_entity = aliased(EntityModel)
    tgt_entity = aliased(EntityModel)
    relation_rows = session.execute(
        select(RelationModel, src_entity, tgt_entity)
        .join(src_entity, RelationModel.source_id == src_entity.id)
        .join(tgt_entity, RelationModel.target_id == tgt_entity.id)
        .where(RelationModel.research_space_id == research_space_id)
        .where(RelationModel.id.in_(relation_ids))
        .order_by(desc(RelationModel.updated_at)),
    ).all()
    evidence_map = _load_relation_evidence_map(session, relation_ids=relation_ids)

    edges: list[JSONObject] = []
    for relation, source, target in relation_rows:
        edges.append(
            _serialize_edge_row(
                relation,
                source_label=source.display_label,
                source_type=source.entity_type,
                target_label=target.display_label,
                target_type=target.entity_type,
                evidence_items=evidence_map.get(relation.id, []),
            ),
        )
    return edges


def _collect_med13_graph(
    session: Session,
    *,
    research_space_id: UUID,
) -> JSONObject:
    label_candidates = (
        session.execute(
            select(EntityModel)
            .where(EntityModel.research_space_id == research_space_id)
            .where(
                func.lower(func.coalesce(EntityModel.display_label, "")).like(
                    "%med13%",
                ),
            ),
        )
        .scalars()
        .all()
    )
    identifier_candidates = (
        session.execute(
            select(EntityModel)
            .join(
                EntityIdentifierModel,
                EntityIdentifierModel.entity_id == EntityModel.id,
            )
            .where(EntityModel.research_space_id == research_space_id)
            .where(func.lower(EntityIdentifierModel.identifier_value).like("med13%")),
        )
        .scalars()
        .all()
    )
    anchors_by_id: dict[UUID, EntityModel] = {}
    for entity in [*label_candidates, *identifier_candidates]:
        anchors_by_id[entity.id] = entity
    anchor_ids = list(anchors_by_id.keys())

    if not anchor_ids:
        return {
            "anchor_entities": [],
            "edge_count": 0,
            "edges": [],
        }

    src_entity = aliased(EntityModel)
    tgt_entity = aliased(EntityModel)
    rows = session.execute(
        select(RelationModel, src_entity, tgt_entity)
        .join(src_entity, RelationModel.source_id == src_entity.id)
        .join(tgt_entity, RelationModel.target_id == tgt_entity.id)
        .where(RelationModel.research_space_id == research_space_id)
        .where(
            or_(
                RelationModel.source_id.in_(anchor_ids),
                RelationModel.target_id.in_(anchor_ids),
            ),
        )
        .order_by(desc(RelationModel.updated_at))
        .limit(_MAX_EDGE_ROWS),
    ).all()
    relation_ids = [row[0].id for row in rows]
    evidence_map = _load_relation_evidence_map(session, relation_ids=relation_ids)

    edges: list[JSONObject] = []
    for relation, source, target in rows:
        edges.append(
            _serialize_edge_row(
                relation,
                source_label=source.display_label,
                source_type=source.entity_type,
                target_label=target.display_label,
                target_type=target.entity_type,
                evidence_items=evidence_map.get(relation.id, []),
            ),
        )

    anchor_entities = [
        {
            "id": str(entity.id),
            "label": entity.display_label,
            "entity_type": entity.entity_type,
        }
        for entity in anchors_by_id.values()
    ]
    return {
        "anchor_entities": anchor_entities,
        "edge_count": len(edges),
        "edges": edges,
    }


def _collect_full_graph_snapshot(
    session: Session,
    *,
    research_space_id: UUID,
) -> JSONObject:
    node_count = int(
        session.execute(
            select(func.count(EntityModel.id)).where(
                EntityModel.research_space_id == research_space_id,
            ),
        ).scalar_one(),
    )
    edge_count = int(
        session.execute(
            select(func.count(RelationModel.id)).where(
                RelationModel.research_space_id == research_space_id,
            ),
        ).scalar_one(),
    )

    src_entity = aliased(EntityModel)
    tgt_entity = aliased(EntityModel)
    edge_rows = session.execute(
        select(RelationModel, src_entity, tgt_entity)
        .join(src_entity, RelationModel.source_id == src_entity.id)
        .join(tgt_entity, RelationModel.target_id == tgt_entity.id)
        .where(RelationModel.research_space_id == research_space_id)
        .order_by(desc(RelationModel.updated_at))
        .limit(_MAX_EDGE_ROWS),
    ).all()
    relation_ids = [row[0].id for row in edge_rows]
    evidence_map = _load_relation_evidence_map(session, relation_ids=relation_ids)
    edges = [
        _serialize_edge_row(
            relation,
            source_label=source.display_label,
            source_type=source.entity_type,
            target_label=target.display_label,
            target_type=target.entity_type,
            evidence_items=evidence_map.get(relation.id, []),
        )
        for relation, source, target in edge_rows
    ]
    return {
        "node_count": node_count,
        "edge_count": edge_count,
        "edges_sampled": len(edges),
        "edges_truncated": edge_count > len(edges),
        "edges": edges,
    }


def _filter_rows_in_window[
    T
](
    rows: list[T],
    *,
    started_at: datetime | None,
    completed_at: datetime | None,
    datetime_getter: callable[[T], datetime],
) -> list[T]:
    if started_at is None or completed_at is None:
        return rows
    window_start = started_at - timedelta(minutes=_WINDOW_PADDING_MINUTES)
    window_end = completed_at + timedelta(minutes=_WINDOW_PADDING_MINUTES)
    filtered: list[T] = []
    for row in rows:
        row_time = _as_utc(datetime_getter(row))
        if window_start <= row_time <= window_end:
            filtered.append(row)
    return filtered


def _collect_dictionary_changes(
    session: Session,
    *,
    started_at: datetime | None,
    completed_at: datetime | None,
    source_document_id: str | None,
) -> list[JSONObject]:
    rows = (
        session.execute(
            select(DictionaryChangelogModel)
            .order_by(desc(DictionaryChangelogModel.created_at))
            .limit(_DICTIONARY_SCAN_LIMIT),
        )
        .scalars()
        .all()
    )
    filtered_rows = _filter_rows_in_window(
        rows,
        started_at=started_at,
        completed_at=completed_at,
        datetime_getter=lambda row: row.created_at,
    )
    if source_document_id is not None:
        filtered_rows = [
            row
            for row in filtered_rows
            if _source_ref_matches_document(
                source_ref=row.source_ref,
                source_document_id=source_document_id,
            )
        ]
    filtered_rows.sort(key=lambda row: row.created_at)
    return [
        {
            "id": row.id,
            "created_at": row.created_at.isoformat(),
            "table_name": row.table_name,
            "record_id": row.record_id,
            "action": row.action,
            "changed_by": row.changed_by,
            "source_ref": row.source_ref,
            "before_snapshot": _trim_large_json_payload(row.before_snapshot),
            "after_snapshot": _trim_large_json_payload(row.after_snapshot),
        }
        for row in filtered_rows
    ]


def _collect_dictionary_entries_created(
    session: Session,
    *,
    started_at: datetime | None,
    completed_at: datetime | None,
    source_document_id: str | None,
) -> dict[str, list[JSONObject]]:
    model_specs: list[tuple[str, object, str]] = [
        ("variable_definitions", VariableDefinitionModel, "id"),
        ("variable_synonyms", VariableSynonymModel, "id"),
        ("dictionary_entity_types", DictionaryEntityTypeModel, "id"),
        ("dictionary_relation_types", DictionaryRelationTypeModel, "id"),
        ("value_sets", ValueSetModel, "id"),
        ("value_set_items", ValueSetItemModel, "id"),
        ("relation_constraints", RelationConstraintModel, "id"),
    ]
    output: dict[str, list[JSONObject]] = {}
    for table_name, model, id_field in model_specs:
        rows = (
            session.execute(
                select(model)
                .order_by(desc(model.created_at))
                .limit(_DICTIONARY_SCAN_LIMIT),
            )
            .scalars()
            .all()
        )
        filtered_rows = _filter_rows_in_window(
            rows,
            started_at=started_at,
            completed_at=completed_at,
            datetime_getter=lambda row: row.created_at,
        )
        table_entries: list[JSONObject] = []
        for row in filtered_rows:
            created_by = getattr(row, "created_by", None)
            if not (
                isinstance(created_by, str) and created_by.strip().startswith("agent:")
            ):
                continue
            if not _source_ref_matches_document(
                source_ref=getattr(row, "source_ref", None),
                source_document_id=source_document_id,
            ):
                continue
            table_entries.append(
                {
                    "id": str(getattr(row, id_field)),
                    "created_at": row.created_at.isoformat(),
                    "created_by": created_by,
                    "review_status": getattr(row, "review_status", None),
                },
            )
        output[table_name] = table_entries
    return output


def _trim_large_json_payload(value: object) -> JSONValue:
    if isinstance(value, dict):
        output: JSONObject = {}
        for key, nested in value.items():
            if str(key).endswith("_embedding"):
                output[str(key)] = "[omitted_embedding]"
            else:
                output[str(key)] = _trim_large_json_payload(nested)
        return output
    if isinstance(value, list):
        trimmed = [
            _trim_large_json_payload(item) for item in value[:_MAX_TRIMMED_LIST_ITEMS]
        ]
        if len(value) > _MAX_TRIMMED_LIST_ITEMS:
            trimmed.append(
                f"... ({len(value) - _MAX_TRIMMED_LIST_ITEMS} more items)",
            )
        return trimmed
    if isinstance(value, str):
        if len(value) > _MAX_TRIMMED_TEXT_CHARS:
            return f"{value[:_MAX_TRIMMED_TEXT_CHARS]}... [truncated]"
        return value
    if isinstance(value, int | float | bool) or value is None:
        return value
    return str(value)


def _source_ref_matches_document(
    *,
    source_ref: object,
    source_document_id: str | None,
) -> bool:
    if source_document_id is None:
        return True
    if not isinstance(source_ref, str):
        return False
    return source_document_id in source_ref


def _normalize_journal_value(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, dict):
        title = value.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
        iso = value.get("iso_abbreviation")
        if isinstance(iso, str) and iso.strip():
            return iso.strip()
    return None


def _resolve_publication_year(
    *,
    publication: PublicationModel | None,
    raw_record: JSONObject,
) -> int | None:
    if publication is not None:
        return publication.publication_year
    publication_date = raw_record.get("publication_date")
    if (
        isinstance(publication_date, str)
        and len(publication_date) >= _YEAR_PREFIX_LENGTH
    ):
        year_prefix = publication_date[:_YEAR_PREFIX_LENGTH]
        if year_prefix.isdigit():
            return int(year_prefix)
    return None


def _build_markdown_report(report: JSONObject) -> str:  # noqa: PLR0915
    target = report.get("target")
    paper = report.get("paper")
    analysis = report.get("analysis")
    dictionary = report.get("dictionary")
    graph = report.get("graph")
    workflow = report.get("workflow")
    smoke = workflow.get("smoke_check", {})

    lines: list[str] = []
    lines.append("# MED13 One-Paper Full Workflow Report")
    lines.append("")
    lines.append(f"- Generated at: `{report.get('generated_at')}`")
    lines.append(
        f"- Source: `{target.get('source_name')}` ({target.get('source_type')})",
    )
    lines.append(
        f"- Research space: `{target.get('research_space_name')}` (`{target.get('research_space_id')}`)",
    )
    lines.append(f"- Workflow run id: `{workflow.get('pipeline_run_id')}`")
    lines.append(f"- Smoke pass: `{smoke.get('passed')}` ({smoke.get('reason')})")
    lines.append("")

    lines.append("## 1. Paper Selected")
    lines.append("")
    lines.append(f"- PubMed ID: `{paper.get('pubmed_id')}`")
    lines.append(f"- Title: {paper.get('title')}")
    lines.append(f"- Journal: {paper.get('journal')}")
    lines.append(f"- Year: `{paper.get('publication_year')}`")
    lines.append(f"- External record id: `{paper.get('external_record_id')}`")
    lines.append("")

    lines.append("## 2. Content Analyzed")
    lines.append("")
    lines.append(f"- Text source used by extraction: `{analysis.get('text_source')}`")
    lines.append(f"- Content length (chars): `{analysis.get('content_length_chars')}`")
    lines.append(f"- Full text available in payload: `{analysis.get('has_full_text')}`")
    lines.append(f"- Enriched storage key: `{analysis.get('enriched_storage_key')}`")
    lines.append("")
    lines.append("### Title")
    lines.append("")
    lines.append(str(analysis.get("title") or "N/A"))
    lines.append("")
    lines.append("### Abstract / Text Preview")
    lines.append("")
    lines.append("```text")
    lines.append(str(analysis.get("text_preview") or "N/A"))
    lines.append("```")
    lines.append("")

    lines.append("## 3. Extraction and Relation Outcomes")
    lines.append("")
    lines.append(f"- Extracted facts count: `{analysis.get('extracted_facts_count')}`")
    lines.append(
        f"- Entity-recognition decision: `{analysis.get('entity_recognition_decision')}`",
    )
    lines.append(
        f"- Entity-recognition governance reason: `{analysis.get('entity_recognition_governance_reason')}`",
    )
    lines.append(
        f"- Extraction stage status: `{analysis.get('extraction_stage_status')}`",
    )
    lines.append(
        f"- Extraction stage reason: `{analysis.get('extraction_stage_reason')}`",
    )
    lines.append(
        f"- Extraction relations extracted: `{analysis.get('extraction_stage_relations_extracted')}`",
    )
    lines.append(
        f"- Extraction rejected relation reasons: `{analysis.get('extraction_stage_rejected_relation_reasons')}`",
    )
    lines.append(
        f"- Document relation edges persisted: `{analysis.get('document_relation_edges_count')}`",
    )
    lines.append(
        f"- Smoke check pass condition: `{smoke.get('criterion')}`",
    )
    lines.append("")
    lines.append("### Extracted Facts")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(analysis.get("extracted_facts"), indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("### Relation Edges Linked to This Document")
    lines.append("")
    lines.append("```json")
    lines.append(
        json.dumps(
            analysis.get("document_relation_edges"),
            indent=2,
            sort_keys=True,
        ),
    )
    lines.append("```")
    lines.append("")

    lines.append("## 4. Dictionary Entries")
    lines.append("")
    lines.append(
        f"- Dictionary changelog entries in run window: `{dictionary.get('changelog_count')}`",
    )
    lines.append(
        f"- Entity types created counter: `{analysis.get('entity_recognition_dictionary_entity_types_created')}`",
    )
    lines.append(
        f"- Synonyms created counter: `{analysis.get('entity_recognition_dictionary_synonyms_created')}`",
    )
    lines.append(
        f"- Variables created counter: `{analysis.get('entity_recognition_dictionary_variables_created')}`",
    )
    lines.append("")
    lines.append("### Changelog Entries")
    lines.append("")
    lines.append("```json")
    lines.append(
        json.dumps(
            dictionary.get("changelog_entries"),
            indent=2,
            sort_keys=True,
        ),
    )
    lines.append("```")
    lines.append("")

    lines.append("## 5. MED13-Centered Graph")
    lines.append("")
    med13_graph = graph.get("med13_centered")
    lines.append(
        f"- MED13 anchor entities: `{len(med13_graph.get('anchor_entities', []))}`",
    )
    lines.append(f"- MED13-centered edge count: `{med13_graph.get('edge_count')}`")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(med13_graph, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")

    lines.append("## 6. Full Graph Snapshot (Current Space)")
    lines.append("")
    full_graph = graph.get("full_space_snapshot")
    lines.append(f"- Nodes: `{full_graph.get('node_count')}`")
    lines.append(f"- Edges: `{full_graph.get('edge_count')}`")
    lines.append(f"- Sampled edges returned: `{full_graph.get('edges_sampled')}`")
    lines.append(f"- Edges truncated: `{full_graph.get('edges_truncated')}`")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(full_graph, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def _write_json(path: Path, payload: JSONObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_to_json_compatible(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _relation_rejections_are_explicit(analysis: JSONObject) -> bool:
    rejected_details = analysis.get("extraction_stage_rejected_relation_details")
    if isinstance(rejected_details, list) and rejected_details:
        return all(
            isinstance(item, dict)
            and isinstance(item.get("reason"), str)
            and item.get("reason", "").strip()
            for item in rejected_details
        )

    rejected_reasons = analysis.get("extraction_stage_rejected_relation_reasons")
    if isinstance(rejected_reasons, list) and rejected_reasons:
        return all(
            isinstance(reason, str) and reason.strip() for reason in rejected_reasons
        )
    return False


def _evaluate_smoke_pass(analysis: JSONObject) -> tuple[bool, str, str]:
    persisted_edges_raw = analysis.get("document_relation_edges_count")
    persisted_edges = (
        int(persisted_edges_raw) if isinstance(persisted_edges_raw, int | float) else 0
    )
    if persisted_edges > 0:
        return (
            True,
            "relation_edges_persisted",
            "persisted_relation_edges>0 OR explicit_rejected_relation_reasons",
        )

    if _relation_rejections_are_explicit(analysis):
        return (
            True,
            "all_candidates_rejected_with_explicit_reasons",
            "persisted_relation_edges>0 OR explicit_rejected_relation_reasons",
        )

    return (
        False,
        "no_persisted_edges_and_no_explicit_rejection_reasons",
        "persisted_relation_edges>0 OR explicit_rejected_relation_reasons",
    )


def main() -> None:  # noqa: PLR0912, PLR0915
    args = _parse_args()
    _configure_logging(verbose=args.verbose)
    normalized_pmid = _normalize_pmid(args.pmid)
    args.pmid = normalized_pmid
    report_json_path, report_md_path = _default_output_paths()
    if args.report_json is not None:
        report_json_path = args.report_json
    if args.report_md is not None:
        report_md_path = args.report_md

    workflow_payload = _run_minimal_workflow_and_load_log(args)
    target_payload = workflow_payload.get("target")
    summary_payload = workflow_payload.get("pipeline_summary")
    if not isinstance(target_payload, dict) or not isinstance(summary_payload, dict):
        msg = "Workflow log is missing target/pipeline_summary sections."
        raise SystemExit(msg)

    source_id = UUID(str(target_payload["source_id"]))
    research_space_id = UUID(str(target_payload["research_space_id"]))
    pipeline_run_id_raw = summary_payload.get("run_id")
    pipeline_run_id = (
        str(pipeline_run_id_raw)
        if isinstance(pipeline_run_id_raw, str) and pipeline_run_id_raw.strip()
        else None
    )
    started_at = _parse_iso_datetime(summary_payload.get("started_at"))
    completed_at = _parse_iso_datetime(summary_payload.get("completed_at"))

    session = SessionLocal()
    try:
        set_session_rls_context(session, bypass_rls=True)
        ingestion_job = _select_ingestion_job_for_run_window(
            session,
            source_id=source_id,
            started_at=started_at,
            completed_at=completed_at,
        )
        ingestion_job_id = ingestion_job.id if ingestion_job is not None else None

        source_document = _select_source_document_for_ingestion_job(
            session,
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
        )
        queue_item = _select_queue_item_for_ingestion_job(
            session,
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
            external_record_id=(
                source_document.external_record_id
                if source_document is not None
                else None
            ),
        )

        if source_document is None:
            queue_item = _select_queue_item_for_run_window(
                session,
                source_id=source_id,
                started_at=started_at,
                completed_at=completed_at,
            )
            source_document = _select_source_document_for_queue_item(
                session,
                source_id=source_id,
                queue_item=queue_item,
            )
            if source_document is None:
                source_document = _select_source_document(
                    session,
                    source_id=source_id,
                    pipeline_run_id=pipeline_run_id,
                )
        if queue_item is None and source_document is not None:
            queue_item = _select_queue_item(
                session,
                source_id=source_id,
                external_record_id=source_document.external_record_id,
            )

        if source_document is None and queue_item is not None:
            source_document = _select_source_document_for_queue_item(
                session,
                source_id=source_id,
                queue_item=queue_item,
            )
        if source_document is None:
            source_document = _select_source_document(
                session,
                source_id=source_id,
                pipeline_run_id=pipeline_run_id,
            )

        if source_document is None:
            msg = (
                "No source document found for selected source after workflow run. "
                "Cannot build one-paper report."
            )
            raise SystemExit(msg)

        if queue_item is None:
            queue_item = _select_queue_item(
                session,
                source_id=source_id,
                external_record_id=source_document.external_record_id,
            )
        extraction = _select_publication_extraction(
            session,
            queue_item_id=queue_item.id if queue_item is not None else None,
        )
        pubmed_id = _extract_pubmed_id(
            queue_item=queue_item,
            source_document=source_document,
        )
        publication = _select_publication(session, pubmed_id=pubmed_id)

        metadata_payload: JSONObject = {}
        raw_record: JSONObject = {}
        if source_document is not None and isinstance(
            source_document.metadata_payload,
            dict,
        ):
            metadata_payload = {
                str(key): value
                for key, value in source_document.metadata_payload.items()
            }
            raw_record_value = metadata_payload.get("raw_record")
            if isinstance(raw_record_value, dict):
                raw_record = {
                    str(key): value for key, value in raw_record_value.items()
                }

        text_value = raw_record.get("full_text")
        if not isinstance(text_value, str) or not text_value.strip():
            text_value = raw_record.get("text")
        if not isinstance(text_value, str) or not text_value.strip():
            text_value = raw_record.get("abstract")
        text_preview = text_value[:4000] if isinstance(text_value, str) else None

        document_relation_edges = _collect_document_relation_edges(
            session,
            research_space_id=research_space_id,
            source_document_id=(
                source_document.id if source_document is not None else None
            ),
        )
        med13_graph = _collect_med13_graph(session, research_space_id=research_space_id)
        full_graph = _collect_full_graph_snapshot(
            session,
            research_space_id=research_space_id,
        )
        dictionary_changelog = _collect_dictionary_changes(
            session,
            started_at=started_at,
            completed_at=completed_at,
            source_document_id=(
                source_document.id if source_document is not None else None
            ),
        )
        dictionary_entries_created = _collect_dictionary_entries_created(
            session,
            started_at=started_at,
            completed_at=completed_at,
            source_document_id=(
                source_document.id if source_document is not None else None
            ),
        )

        report: JSONObject = {
            "generated_at": datetime.now(UTC).isoformat(),
            "workflow": {
                "pipeline_run_id": pipeline_run_id,
                "ingestion_job_id": ingestion_job_id,
                "requested_pmid": normalized_pmid,
                "started_at": (
                    started_at.isoformat() if started_at is not None else None
                ),
                "completed_at": (
                    completed_at.isoformat() if completed_at is not None else None
                ),
                "source_workflow_log": (
                    str(args.workflow_log) if args.workflow_log else None
                ),
                "workflow_payload": workflow_payload,
            },
            "target": {
                "source_id": str(source_id),
                "source_name": str(target_payload.get("source_name", "")),
                "source_type": str(target_payload.get("source_type", "")),
                "research_space_id": str(research_space_id),
                "research_space_name": str(
                    target_payload.get("research_space_name", ""),
                ),
                "requested_pmid": normalized_pmid,
            },
            "paper": {
                "source_document_id": source_document.id if source_document else None,
                "external_record_id": (
                    source_document.external_record_id if source_document else None
                ),
                "pubmed_id": pubmed_id,
                "title": (
                    raw_record.get("title")
                    if isinstance(raw_record.get("title"), str)
                    else (publication.title if publication is not None else None)
                ),
                "journal": _normalize_journal_value(
                    (
                        publication.journal
                        if publication is not None
                        else raw_record.get("journal")
                    ),
                ),
                "publication_year": _resolve_publication_year(
                    publication=publication,
                    raw_record=raw_record,
                ),
                "doi": (
                    publication.doi
                    if publication is not None
                    else raw_record.get("doi")
                ),
            },
            "analysis": {
                "text_source": (
                    extraction.text_source if extraction is not None else None
                ),
                "has_full_text": bool(
                    isinstance(raw_record.get("full_text"), str)
                    and raw_record.get("full_text", "").strip(),
                ),
                "content_length_chars": metadata_payload.get(
                    "content_enrichment_content_length_chars",
                ),
                "enriched_storage_key": (
                    source_document.enriched_storage_key if source_document else None
                ),
                "title": raw_record.get("title"),
                "text_preview": text_preview,
                "raw_record": raw_record,
                "metadata_payload": metadata_payload,
                "extracted_facts_count": (
                    len(extraction.facts) if extraction is not None else 0
                ),
                "extracted_facts": extraction.facts if extraction is not None else [],
                "entity_recognition_decision": metadata_payload.get(
                    "entity_recognition_decision",
                ),
                "entity_recognition_governance_reason": metadata_payload.get(
                    "entity_recognition_governance_reason",
                ),
                "extraction_stage_status": metadata_payload.get(
                    "extraction_stage_status",
                ),
                "extraction_stage_reason": metadata_payload.get(
                    "extraction_stage_reason",
                ),
                "extraction_stage_relations_extracted": metadata_payload.get(
                    "extraction_stage_relations_extracted",
                ),
                "extraction_stage_rejected_relation_reasons": (
                    metadata_payload.get("extraction_stage_rejected_relation_reasons")
                    if isinstance(
                        metadata_payload.get(
                            "extraction_stage_rejected_relation_reasons",
                        ),
                        list,
                    )
                    else []
                ),
                "extraction_stage_rejected_relation_details": (
                    metadata_payload.get("extraction_stage_rejected_relation_details")
                    if isinstance(
                        metadata_payload.get(
                            "extraction_stage_rejected_relation_details",
                        ),
                        list,
                    )
                    else []
                ),
                "entity_recognition_dictionary_entity_types_created": metadata_payload.get(
                    "entity_recognition_dictionary_entity_types_created",
                ),
                "entity_recognition_dictionary_synonyms_created": metadata_payload.get(
                    "entity_recognition_dictionary_synonyms_created",
                ),
                "entity_recognition_dictionary_variables_created": metadata_payload.get(
                    "entity_recognition_dictionary_variables_created",
                ),
                "document_relation_edges_count": len(document_relation_edges),
                "document_relation_edges": document_relation_edges,
            },
            "dictionary": {
                "changelog_count": len(dictionary_changelog),
                "changelog_entries": dictionary_changelog,
                "created_entries_by_table": dictionary_entries_created,
            },
            "graph": {
                "med13_centered": med13_graph,
                "full_space_snapshot": full_graph,
            },
        }
        smoke_passed, smoke_reason, smoke_criterion = _evaluate_smoke_pass(
            report["analysis"],
        )
        report["workflow"]["smoke_check"] = {
            "passed": smoke_passed,
            "reason": smoke_reason,
            "criterion": smoke_criterion,
        }
    finally:
        session.close()

    markdown = _build_markdown_report(report)
    _write_json(report_json_path, report)
    _write_text(report_md_path, markdown)
    logger.info("Detailed JSON report: %s", report_json_path)
    logger.info("Detailed Markdown report: %s", report_md_path)
    smoke_payload = report.get("workflow", {}).get("smoke_check", {})
    if args.require_smoke_pass and not bool(smoke_payload.get("passed")):
        msg = (
            "Smoke pass criteria not met: "
            f"{smoke_payload.get('reason')}. "
            f"Criterion={smoke_payload.get('criterion')}"
        )
        raise SystemExit(msg)


if __name__ == "__main__":
    main()
