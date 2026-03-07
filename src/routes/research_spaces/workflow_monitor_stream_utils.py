"""Shared helpers for workflow monitor SSE stream routes."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.database.user_data_source import SourceStatusEnum, UserDataSourceModel

STREAM_TICK_SECONDS = 2.0
STREAM_HEARTBEAT_SECONDS = 15.0
STREAM_EVENTS_LIMIT = 6
STREAM_MONITOR_LIMIT = 5
STREAM_SOURCE_MONITOR_LIMIT = 50
_WORKFLOW_SSE_ENABLED_ENV = "MED13_ENABLE_WORKFLOW_SSE"
_WORKFLOW_SSE_TRUE_VALUES = {"1", "true", "yes", "on"}


def is_workflow_sse_enabled() -> bool:
    raw_value = os.getenv(_WORKFLOW_SSE_ENABLED_ENV, "true")
    return raw_value.strip().lower() in _WORKFLOW_SSE_TRUE_VALUES


def parse_requested_source_ids(raw_source_ids: str | None) -> list[str]:
    if raw_source_ids is None:
        return []
    normalized_tokens = [
        token.strip() for token in raw_source_ids.split(",") if token.strip()
    ]
    unique_ids: list[str] = []
    for token in normalized_tokens:
        try:
            normalized_uuid = str(UUID(token))
        except ValueError as exc:
            msg = f"Invalid source id in source_ids: {token}"
            raise ValueError(msg) from exc
        if normalized_uuid not in unique_ids:
            unique_ids.append(normalized_uuid)
    return unique_ids


def _json_default(raw_value: object) -> object:
    if isinstance(raw_value, datetime):
        return raw_value.isoformat()
    return str(raw_value)


def encode_sse_data(payload: object) -> str:
    return json.dumps(payload, default=_json_default, separators=(",", ":"))


def hash_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        default=_json_default,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def sse_event_payload(*, event: str, sequence: int, data: object) -> str:
    encoded_data = encode_sse_data(data).replace("\n", "\\n")
    return f"event: {event}\nid: {sequence}\ndata: {encoded_data}\n\n"


def extract_latest_occurred_at(events: list[object]) -> str | None:
    latest: datetime | None = None
    latest_raw: str | None = None
    for item in events:
        if not isinstance(item, dict):
            continue
        occurred_at = item.get("occurred_at")
        if not isinstance(occurred_at, str) or not occurred_at.strip():
            continue
        normalized = occurred_at.strip()
        candidate = (
            normalized[:-1] + "+00:00" if normalized.endswith("Z") else normalized
        )
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        parsed_with_tz = (
            parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        )
        if latest is None or parsed_with_tz > latest:
            latest = parsed_with_tz
            latest_raw = parsed_with_tz.isoformat()
    return latest_raw


def derive_last_failed_stage(last_run_payload: object) -> str | None:
    if not isinstance(last_run_payload, dict):
        return None
    run_status = last_run_payload.get("status")
    if not isinstance(run_status, str) or run_status.strip() != "failed":
        return None

    ordered_stages: tuple[str, ...] = ("ingestion", "enrichment", "extraction", "graph")
    raw_stage_statuses = last_run_payload.get("stage_statuses")
    stage_statuses_raw: dict[object, object]
    if isinstance(raw_stage_statuses, dict):
        stage_statuses_raw = raw_stage_statuses
    else:
        stage_statuses_raw = {}
    stage_statuses: Mapping[str, object] = {
        str(key): value for key, value in stage_statuses_raw.items()
    }
    for stage in ordered_stages:
        if stage_statuses.get(stage) == "failed":
            return stage

    raw_stage_errors = last_run_payload.get("stage_errors")
    stage_errors_raw: dict[object, object] = (
        raw_stage_errors if isinstance(raw_stage_errors, dict) else {}
    )
    stage_errors: Mapping[str, object] = {
        str(key): value for key, value in stage_errors_raw.items()
    }
    for stage in ordered_stages:
        stage_error = stage_errors.get(stage)
        if isinstance(stage_error, str) and stage_error.strip():
            return stage
    return "ingestion"


def _coerce_card_count(raw_value: object) -> int:
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value)
    if isinstance(raw_value, str):
        try:
            return int(raw_value)
        except ValueError:
            return 0
    return 0


def _resolve_active_pipeline_run_id(
    monitor_payload: Mapping[str, object],
) -> str | None:
    last_run_raw = monitor_payload.get("last_run")
    if not isinstance(last_run_raw, dict):
        return None

    run_status = last_run_raw.get("status")
    if not isinstance(run_status, str) or run_status not in {
        "queued",
        "retrying",
        "running",
    }:
        return None

    run_id = last_run_raw.get("run_id")
    if not isinstance(run_id, str):
        return None
    normalized_run_id = run_id.strip()
    return normalized_run_id or None


def build_workflow_card_status(
    monitor_payload: Mapping[str, object],
) -> dict[str, object]:
    counters_raw = monitor_payload.get("operational_counters")
    counters = counters_raw if isinstance(counters_raw, dict) else {}
    return {
        "active_pipeline_run_id": _resolve_active_pipeline_run_id(monitor_payload),
        "last_pipeline_status": (
            counters.get("last_pipeline_status")
            if isinstance(counters.get("last_pipeline_status"), str)
            else None
        ),
        "last_failed_stage": derive_last_failed_stage(monitor_payload.get("last_run")),
        "pending_paper_count": _coerce_card_count(counters.get("pending_paper_count")),
        "pending_relation_review_count": _coerce_card_count(
            counters.get("pending_relation_review_count"),
        ),
        "extraction_extracted_count": _coerce_card_count(
            counters.get("extraction_extracted_count"),
        ),
        "extraction_failed_count": _coerce_card_count(
            counters.get("extraction_failed_count"),
        ),
        "extraction_skipped_count": _coerce_card_count(
            counters.get("extraction_skipped_count"),
        ),
        "extraction_timeout_failed_count": _coerce_card_count(
            counters.get("extraction_timeout_failed_count"),
        ),
        "graph_edges_delta_last_run": _coerce_card_count(
            counters.get("graph_edges_delta_last_run"),
        ),
        "graph_edges_total": _coerce_card_count(counters.get("graph_edges_total")),
        "artana_progress": (
            monitor_payload.get("artana_progress")
            if isinstance(monitor_payload.get("artana_progress"), dict)
            else None
        ),
    }


def resolve_space_source_ids(
    *,
    session: Session,
    space_id: UUID,
    include_inactive: bool,
    requested_source_ids: list[str],
) -> list[str]:
    statement = select(UserDataSourceModel.id).where(
        UserDataSourceModel.research_space_id == str(space_id),
    )
    if not include_inactive:
        statement = statement.where(
            UserDataSourceModel.status == SourceStatusEnum.ACTIVE,
        )
    if requested_source_ids:
        statement = statement.where(UserDataSourceModel.id.in_(requested_source_ids))
    statement = statement.order_by(UserDataSourceModel.id.asc())
    rows = session.execute(statement).scalars().all()
    return [str(item) for item in rows]


__all__ = [
    "STREAM_EVENTS_LIMIT",
    "STREAM_HEARTBEAT_SECONDS",
    "STREAM_MONITOR_LIMIT",
    "STREAM_SOURCE_MONITOR_LIMIT",
    "STREAM_TICK_SECONDS",
    "build_workflow_card_status",
    "derive_last_failed_stage",
    "encode_sse_data",
    "extract_latest_occurred_at",
    "hash_payload",
    "is_workflow_sse_enabled",
    "now_iso",
    "parse_requested_source_ids",
    "resolve_space_source_ids",
    "sse_event_payload",
]
