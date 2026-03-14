"""Artana-kernel-backed lifecycle and artifact adapters for graph-harness."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select

from src.models.database import HarnessRunModel

from .artifact_store import (
    HarnessArtifactRecord,
    HarnessArtifactStore,
    HarnessWorkspaceRecord,
)
from .run_registry import (
    HarnessRunEventRecord,
    HarnessRunProgressRecord,
    HarnessRunRecord,
    HarnessRunRegistry,
    _default_message_for_status,
    _default_phase_for_status,
    _default_progress_percent,
)

if TYPE_CHECKING:
    from uuid import UUID

    from artana.events import KernelEvent, RunSummaryPayload
    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject

    from .composition import GraphHarnessKernelRuntime


_RUN_STATE_SUMMARY = "harness::run_state"
_PROGRESS_SUMMARY = "harness::progress"
_WORKSPACE_SUMMARY = "harness::workspace"
_ARTIFACT_PREFIX = "artifact::"
_EVENT_PREFIX = "event::"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _summary_payload(summary: RunSummaryPayload | None) -> JSONObject | None:
    if summary is None:
        return None
    try:
        payload = json.loads(summary.summary_json)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _payload_string(
    payload: JSONObject,
    key: str,
    *,
    default: str,
) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else default


def _payload_float(
    payload: JSONObject,
    key: str,
    *,
    default: float,
) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    return float(value)


def _payload_int(
    payload: JSONObject,
    key: str,
    *,
    default: int,
) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def _payload_optional_int(payload: JSONObject, key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _payload_json_object(payload: JSONObject, key: str) -> JSONObject:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _payload_optional_string(payload: JSONObject, key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _event_payload(event: KernelEvent) -> JSONObject:
    payload = event.payload.model_dump(mode="json")
    return payload if isinstance(payload, dict) else {}


def _pause_context_payload(payload: JSONObject) -> JSONObject:
    context_json = payload.get("context_json")
    if not isinstance(context_json, str) or context_json.strip() == "":
        return {}
    try:
        decoded = json.loads(context_json)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _kernel_event_record(
    *,
    run: HarnessRunRecord,
    event: KernelEvent,
) -> HarnessRunEventRecord:
    payload = _event_payload(event)
    event_type = event.event_type.value
    enriched_payload: JSONObject = dict(payload)
    message = event_type.replace("_", " ")
    progress_percent: float | None = None

    if event_type == "tool_requested":
        tool_name = payload.get("tool_name")
        if isinstance(tool_name, str):
            enriched_payload["decision_source"] = "tool"
            enriched_payload["tool_name"] = tool_name
            enriched_payload["status"] = "pending"
            enriched_payload["started_at"] = event.timestamp.isoformat()
            message = f"Tool '{tool_name}' requested."
    elif event_type == "tool_completed":
        tool_name = payload.get("tool_name")
        outcome = payload.get("outcome")
        if isinstance(tool_name, str):
            enriched_payload["decision_source"] = "tool"
            enriched_payload["tool_name"] = tool_name
            enriched_payload["status"] = "success" if outcome == "success" else "failed"
            enriched_payload["completed_at"] = event.timestamp.isoformat()
            message = f"Tool '{tool_name}' completed."
    elif event_type == "pause_requested":
        pause_context = _pause_context_payload(payload)
        approval_key = pause_context.get("approval_key")
        tool_name = pause_context.get("tool_name")
        if isinstance(tool_name, str):
            enriched_payload["decision_source"] = "tool"
            enriched_payload["tool_name"] = tool_name
            enriched_payload["status"] = "paused"
            message = f"Tool '{tool_name}' paused pending approval."
        if isinstance(approval_key, str):
            enriched_payload["approval_id"] = approval_key

    return HarnessRunEventRecord(
        id=event.event_id,
        space_id=run.space_id,
        run_id=run.id,
        event_type=event_type,
        status=run.status,
        message=message,
        progress_percent=progress_percent,
        payload=enriched_payload,
        created_at=event.timestamp,
        updated_at=event.timestamp,
    )


def _summary_event_payload(event: KernelEvent) -> tuple[str, JSONObject] | None:
    payload = _event_payload(event)
    summary_type = payload.get("summary_type")
    summary_json = payload.get("summary_json")
    if not isinstance(summary_type, str) or not isinstance(summary_json, str):
        return None
    try:
        decoded = json.loads(summary_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict):
        return None
    return summary_type, decoded


def _step_key(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _run_record_from_model(
    *,
    model: HarnessRunModel,
    status: str,
    updated_at: datetime,
) -> HarnessRunRecord:
    return HarnessRunRecord(
        id=model.id,
        space_id=model.space_id,
        harness_id=model.harness_id,
        title=model.title,
        status=status,
        input_payload=(
            model.input_payload if isinstance(model.input_payload, dict) else {}
        ),
        graph_service_status=model.graph_service_status,
        graph_service_version=model.graph_service_version,
        created_at=model.created_at,
        updated_at=updated_at,
    )


def _default_progress_record(run: HarnessRunRecord) -> HarnessRunProgressRecord:
    return HarnessRunProgressRecord(
        space_id=run.space_id,
        run_id=run.id,
        status=run.status,
        phase="queued",
        message="Run created and queued.",
        progress_percent=0.0,
        completed_steps=0,
        total_steps=None,
        resume_point=None,
        metadata={},
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


class ArtanaBackedHarnessRunRegistry(HarnessRunRegistry):
    """Store harness lifecycle state in Artana summaries and events."""

    def __init__(
        self,
        *,
        session: Session,
        runtime: GraphHarnessKernelRuntime,
    ) -> None:
        self._session = session
        self._runtime = runtime

    def _get_run_model(self, *, run_id: UUID | str) -> HarnessRunModel | None:
        return self._session.get(HarnessRunModel, str(run_id))

    def _latest_run_state(self, *, space_id: str, run_id: str) -> JSONObject | None:
        return _summary_payload(
            self._runtime.get_latest_run_summary(
                run_id=run_id,
                tenant_id=space_id,
                summary_type=_RUN_STATE_SUMMARY,
            ),
        )

    def _latest_progress(self, *, space_id: str, run_id: str) -> JSONObject | None:
        return _summary_payload(
            self._runtime.get_latest_run_summary(
                run_id=run_id,
                tenant_id=space_id,
                summary_type=_PROGRESS_SUMMARY,
            ),
        )

    def _hydrate_run(self, *, model: HarnessRunModel) -> HarnessRunRecord:
        state_payload = self._latest_run_state(space_id=model.space_id, run_id=model.id)
        progress_payload = self._latest_progress(
            space_id=model.space_id,
            run_id=model.id,
        )
        status = (
            progress_payload.get("status")
            if isinstance(progress_payload, dict)
            else None
        )
        if not isinstance(status, str):
            status = (
                state_payload.get("status")
                if isinstance(state_payload, dict)
                else model.status
            )
        updated_at = (
            _parse_timestamp(
                (
                    progress_payload.get("updated_at")
                    if isinstance(progress_payload, dict)
                    else None
                ),
            )
            or _parse_timestamp(
                (
                    state_payload.get("updated_at")
                    if isinstance(state_payload, dict)
                    else None
                ),
            )
            or model.updated_at
        )
        return _run_record_from_model(
            model=model,
            status=status if isinstance(status, str) else model.status,
            updated_at=updated_at,
        )

    def _write_summary(
        self,
        *,
        run_id: str,
        space_id: str,
        summary_type: str,
        payload: JSONObject,
        step_prefix: str,
    ) -> None:
        self._runtime.append_run_summary(
            run_id=run_id,
            tenant_id=space_id,
            summary_type=summary_type,
            summary_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            step_key=_step_key(step_prefix),
        )

    def _write_event_summary(  # noqa: PLR0913
        self,
        *,
        space_id: str,
        run_id: str,
        event_type: str,
        status: str,
        message: str,
        payload: JSONObject,
        progress_percent: float | None,
    ) -> HarnessRunEventRecord:
        now = _utcnow()
        record = HarnessRunEventRecord(
            id=str(uuid4()),
            space_id=space_id,
            run_id=run_id,
            event_type=event_type,
            status=status,
            message=message,
            progress_percent=progress_percent,
            payload=payload,
            created_at=now,
            updated_at=now,
        )
        self._write_summary(
            run_id=run_id,
            space_id=space_id,
            summary_type=f"{_EVENT_PREFIX}{record.id}",
            payload={
                "id": record.id,
                "event_type": record.event_type,
                "status": record.status,
                "message": record.message,
                "progress_percent": record.progress_percent,
                "payload": record.payload,
                "created_at": record.created_at.isoformat(),
                "updated_at": record.updated_at.isoformat(),
            },
            step_prefix="event",
        )
        return record

    def create_run(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        harness_id: str,
        title: str,
        input_payload: JSONObject,
        graph_service_status: str,
        graph_service_version: str,
    ) -> HarnessRunRecord:
        normalized_space_id = str(space_id)
        model = HarnessRunModel(
            space_id=normalized_space_id,
            harness_id=harness_id,
            title=title,
            status="queued",
            input_payload=input_payload,
            graph_service_status=graph_service_status,
            graph_service_version=graph_service_version,
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        self._runtime.ensure_run(run_id=model.id, tenant_id=normalized_space_id)
        record = _run_record_from_model(
            model=model,
            status="queued",
            updated_at=model.created_at,
        )
        self._write_summary(
            run_id=model.id,
            space_id=normalized_space_id,
            summary_type=_RUN_STATE_SUMMARY,
            payload={
                "status": "queued",
                "updated_at": model.created_at.isoformat(),
            },
            step_prefix="run_state",
        )
        progress = _default_progress_record(record)
        self._write_summary(
            run_id=model.id,
            space_id=normalized_space_id,
            summary_type=_PROGRESS_SUMMARY,
            payload={
                "status": progress.status,
                "phase": progress.phase,
                "message": progress.message,
                "progress_percent": progress.progress_percent,
                "completed_steps": progress.completed_steps,
                "total_steps": progress.total_steps,
                "resume_point": progress.resume_point,
                "metadata": progress.metadata,
                "created_at": progress.created_at.isoformat(),
                "updated_at": progress.updated_at.isoformat(),
            },
            step_prefix="progress",
        )
        self._write_event_summary(
            space_id=normalized_space_id,
            run_id=model.id,
            event_type="run.created",
            status="queued",
            message="Run created and queued.",
            payload={"harness_id": harness_id, "title": title},
            progress_percent=0.0,
        )
        return record

    def list_runs(self, *, space_id: UUID | str) -> list[HarnessRunRecord]:
        stmt = (
            select(HarnessRunModel)
            .where(HarnessRunModel.space_id == str(space_id))
            .order_by(HarnessRunModel.created_at.desc())
        )
        models = self._session.execute(stmt).scalars().all()
        return [self._hydrate_run(model=model) for model in models]

    def get_run(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunRecord | None:
        model = self._get_run_model(run_id=run_id)
        if model is None or model.space_id != str(space_id):
            return None
        return self._hydrate_run(model=model)

    def replace_run_input_payload(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        input_payload: JSONObject,
    ) -> HarnessRunRecord | None:
        model = self._get_run_model(run_id=run_id)
        if model is None or model.space_id != str(space_id):
            return None
        model.input_payload = input_payload
        model.updated_at = _utcnow()
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return self._hydrate_run(model=model)

    def get_progress(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunProgressRecord | None:
        run = self.get_run(space_id=space_id, run_id=run_id)
        if run is None:
            return None
        payload = self._latest_progress(space_id=run.space_id, run_id=run.id)
        if isinstance(payload, dict):
            return HarnessRunProgressRecord(
                space_id=run.space_id,
                run_id=run.id,
                status=_payload_string(payload, "status", default=run.status),
                phase=_payload_string(
                    payload,
                    "phase",
                    default=_default_phase_for_status(run.status),
                ),
                message=_payload_string(
                    payload,
                    "message",
                    default=_default_message_for_status(run.status),
                ),
                progress_percent=_payload_float(
                    payload,
                    "progress_percent",
                    default=_default_progress_percent(status=run.status),
                ),
                completed_steps=_payload_int(payload, "completed_steps", default=0),
                total_steps=_payload_optional_int(payload, "total_steps"),
                resume_point=_payload_optional_string(payload, "resume_point"),
                metadata=_payload_json_object(payload, "metadata"),
                created_at=_parse_timestamp(payload.get("created_at"))
                or run.created_at,
                updated_at=_parse_timestamp(payload.get("updated_at"))
                or run.updated_at,
            )
        kernel_progress = self._runtime.get_run_progress(
            run_id=run.id,
            tenant_id=run.space_id,
        )
        kernel_status = self._runtime.get_run_status(
            run_id=run.id,
            tenant_id=run.space_id,
        )
        resume_point = self._runtime.get_resume_point(
            run_id=run.id,
            tenant_id=run.space_id,
        )
        if kernel_progress is None and kernel_status is None:
            return None
        return HarnessRunProgressRecord(
            space_id=run.space_id,
            run_id=run.id,
            status=(
                getattr(kernel_progress, "status", None)
                or getattr(kernel_status, "status", None)
                or run.status
            ),
            phase=getattr(kernel_progress, "current_stage", None) or run.status,
            message=_default_message_for_status(run.status),
            progress_percent=float(getattr(kernel_progress, "percent", 0.0) or 0.0),
            completed_steps=len(getattr(kernel_progress, "completed_stages", ()) or ()),
            total_steps=None,
            resume_point=getattr(resume_point, "step_key", None),
            metadata={},
            created_at=getattr(kernel_progress, "started_at", None) or run.created_at,
            updated_at=getattr(kernel_progress, "updated_at", None) or run.updated_at,
        )

    def set_run_status(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        status: str,
    ) -> HarnessRunRecord | None:
        run = self.get_run(space_id=space_id, run_id=run_id)
        if run is None:
            return None
        now = _utcnow()
        model = self._get_run_model(run_id=run.id)
        if model is not None:
            model.status = status
            model.updated_at = now
            self._session.add(model)
            self._session.commit()
        self._write_summary(
            run_id=run.id,
            space_id=run.space_id,
            summary_type=_RUN_STATE_SUMMARY,
            payload={
                "status": status,
                "updated_at": now.isoformat(),
            },
            step_prefix="run_state",
        )
        existing_progress = self.get_progress(space_id=space_id, run_id=run_id)
        progress_record = HarnessRunProgressRecord(
            space_id=run.space_id,
            run_id=run.id,
            status=status,
            phase=_default_phase_for_status(status),
            message=_default_message_for_status(status),
            progress_percent=_default_progress_percent(
                status=status,
                current=(
                    existing_progress.progress_percent
                    if existing_progress is not None
                    else None
                ),
            ),
            completed_steps=(
                existing_progress.completed_steps
                if existing_progress is not None
                else 0
            ),
            total_steps=(
                existing_progress.total_steps if existing_progress is not None else None
            ),
            resume_point=(
                existing_progress.resume_point
                if existing_progress is not None and status.strip().lower() == "paused"
                else None
            ),
            metadata=(
                existing_progress.metadata if existing_progress is not None else {}
            ),
            created_at=(
                existing_progress.created_at
                if existing_progress is not None
                else run.created_at
            ),
            updated_at=now,
        )
        self._write_summary(
            run_id=run.id,
            space_id=run.space_id,
            summary_type=_PROGRESS_SUMMARY,
            payload={
                "status": progress_record.status,
                "phase": progress_record.phase,
                "message": progress_record.message,
                "progress_percent": progress_record.progress_percent,
                "completed_steps": progress_record.completed_steps,
                "total_steps": progress_record.total_steps,
                "resume_point": progress_record.resume_point,
                "metadata": progress_record.metadata,
                "created_at": progress_record.created_at.isoformat(),
                "updated_at": progress_record.updated_at.isoformat(),
            },
            step_prefix="progress",
        )
        self._write_event_summary(
            space_id=run.space_id,
            run_id=run.id,
            event_type="run.status_changed",
            status=status,
            message=progress_record.message,
            payload={"phase": progress_record.phase},
            progress_percent=progress_record.progress_percent,
        )
        return self.get_run(space_id=space_id, run_id=run_id)

    def set_progress(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        phase: str,
        message: str,
        progress_percent: float,
        completed_steps: int | None = None,
        total_steps: int | None = None,
        resume_point: str | None = None,
        clear_resume_point: bool = False,
        metadata: JSONObject | None = None,
    ) -> HarnessRunProgressRecord | None:
        run = self.get_run(space_id=space_id, run_id=run_id)
        if run is None:
            return None
        existing = self.get_progress(space_id=space_id, run_id=run_id)
        now = _utcnow()
        merged_metadata: JSONObject = {
            **(existing.metadata if existing is not None else {}),
            **(metadata or {}),
        }
        updated = HarnessRunProgressRecord(
            space_id=run.space_id,
            run_id=run.id,
            status=run.status,
            phase=phase.strip()
            or (existing.phase if existing is not None else run.status),
            message=message.strip()
            or (
                existing.message
                if existing is not None
                else _default_message_for_status(run.status)
            ),
            progress_percent=max(0.0, min(progress_percent, 1.0)),
            completed_steps=(
                completed_steps
                if completed_steps is not None
                else (existing.completed_steps if existing is not None else 0)
            ),
            total_steps=(
                total_steps
                if total_steps is not None
                else (existing.total_steps if existing is not None else None)
            ),
            resume_point=(
                None
                if clear_resume_point
                else (
                    resume_point
                    if resume_point is not None
                    else (existing.resume_point if existing is not None else None)
                )
            ),
            metadata=merged_metadata,
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        self._write_summary(
            run_id=run.id,
            space_id=run.space_id,
            summary_type=_PROGRESS_SUMMARY,
            payload={
                "status": updated.status,
                "phase": updated.phase,
                "message": updated.message,
                "progress_percent": updated.progress_percent,
                "completed_steps": updated.completed_steps,
                "total_steps": updated.total_steps,
                "resume_point": updated.resume_point,
                "metadata": updated.metadata,
                "created_at": updated.created_at.isoformat(),
                "updated_at": updated.updated_at.isoformat(),
            },
            step_prefix="progress",
        )
        self._write_event_summary(
            space_id=run.space_id,
            run_id=run.id,
            event_type="run.progress",
            status=run.status,
            message=updated.message,
            payload={
                "phase": updated.phase,
                "resume_point": updated.resume_point,
                "completed_steps": updated.completed_steps,
                "total_steps": updated.total_steps,
                "metadata": updated.metadata,
            },
            progress_percent=updated.progress_percent,
        )
        return updated

    def list_events(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        limit: int = 100,
    ) -> list[HarnessRunEventRecord]:
        run = self.get_run(space_id=space_id, run_id=run_id)
        if run is None:
            return []
        events: list[HarnessRunEventRecord] = []
        for event in self._runtime.get_events(run_id=run.id, tenant_id=run.space_id):
            if event.event_type.value == "run_summary":
                summary_event = _summary_event_payload(event)
                if summary_event is None:
                    continue
                summary_type, payload = summary_event
                if summary_type.startswith(_EVENT_PREFIX):
                    events.append(
                        HarnessRunEventRecord(
                            id=_payload_string(payload, "id", default=event.event_id),
                            space_id=run.space_id,
                            run_id=run.id,
                            event_type=_payload_string(
                                payload,
                                "event_type",
                                default="run.event",
                            ),
                            status=_payload_string(
                                payload,
                                "status",
                                default=run.status,
                            ),
                            message=_payload_string(
                                payload,
                                "message",
                                default="Run event recorded.",
                            ),
                            progress_percent=(
                                _payload_float(payload, "progress_percent", default=0.0)
                                if isinstance(
                                    payload.get("progress_percent"),
                                    int | float,
                                )
                                and not isinstance(
                                    payload.get("progress_percent"),
                                    bool,
                                )
                                else None
                            ),
                            payload=_payload_json_object(payload, "payload"),
                            created_at=_parse_timestamp(payload.get("created_at"))
                            or event.timestamp,
                            updated_at=_parse_timestamp(payload.get("updated_at"))
                            or event.timestamp,
                        ),
                    )
                continue
            events.append(_kernel_event_record(run=run, event=event))
        return events[:limit]

    def record_event(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        event_type: str,
        message: str,
        payload: JSONObject | None = None,
        progress_percent: float | None = None,
    ) -> HarnessRunEventRecord | None:
        run = self.get_run(space_id=space_id, run_id=run_id)
        if run is None:
            return None
        return self._write_event_summary(
            space_id=run.space_id,
            run_id=run.id,
            event_type=event_type.strip() or "run.event",
            status=run.status,
            message=message.strip() or "Run event recorded.",
            payload=payload or {},
            progress_percent=progress_percent,
        )


class ArtanaBackedHarnessArtifactStore(HarnessArtifactStore):
    """Store artifacts and workspace snapshots in Artana summaries."""

    def __init__(self, *, runtime: GraphHarnessKernelRuntime) -> None:
        self._runtime = runtime

    def _artifact_summary_type(self, artifact_key: str) -> str:
        return f"{_ARTIFACT_PREFIX}{artifact_key}"

    def seed_for_run(self, *, run: HarnessRunRecord) -> None:
        workspace_snapshot: JSONObject = {
            "space_id": run.space_id,
            "run_id": run.id,
            "harness_id": run.harness_id,
            "title": run.title,
            "status": run.status,
            "input_payload": run.input_payload,
            "graph_service": {
                "status": run.graph_service_status,
                "version": run.graph_service_version,
            },
            "artifact_keys": ["run_manifest"],
        }
        self.put_artifact(
            space_id=run.space_id,
            run_id=run.id,
            artifact_key="run_manifest",
            media_type="application/json",
            content={
                "run_id": run.id,
                "space_id": run.space_id,
                "harness_id": run.harness_id,
                "title": run.title,
                "status": run.status,
                "created_at": run.created_at.isoformat(),
                "graph_service_status": run.graph_service_status,
                "graph_service_version": run.graph_service_version,
            },
        )
        self._write_workspace(
            space_id=run.space_id,
            run_id=run.id,
            snapshot=workspace_snapshot,
            created_at=run.created_at,
            updated_at=run.created_at,
        )

    def _write_workspace(
        self,
        *,
        space_id: str,
        run_id: str,
        snapshot: JSONObject,
        created_at: datetime,
        updated_at: datetime,
    ) -> HarnessWorkspaceRecord:
        self._runtime.append_run_summary(
            run_id=run_id,
            tenant_id=space_id,
            summary_type=_WORKSPACE_SUMMARY,
            summary_json=json.dumps(
                {
                    "snapshot": snapshot,
                    "created_at": created_at.isoformat(),
                    "updated_at": updated_at.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            step_key=_step_key("workspace"),
        )
        return HarnessWorkspaceRecord(
            space_id=space_id,
            run_id=run_id,
            snapshot=snapshot,
            created_at=created_at,
            updated_at=updated_at,
        )

    def list_artifacts(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> list[HarnessArtifactRecord]:
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        artifact_by_key: dict[str, HarnessArtifactRecord] = {}
        for event in self._runtime.get_events(
            run_id=normalized_run_id,
            tenant_id=normalized_space_id,
        ):
            if event.event_type.value != "run_summary":
                continue
            summary_event = _summary_event_payload(event)
            if summary_event is None:
                continue
            summary_type, payload = summary_event
            if not summary_type.startswith(_ARTIFACT_PREFIX):
                continue
            artifact_key = summary_type.removeprefix(_ARTIFACT_PREFIX)
            artifact_by_key[artifact_key] = HarnessArtifactRecord(
                space_id=normalized_space_id,
                run_id=normalized_run_id,
                key=artifact_key,
                media_type=_payload_string(
                    payload,
                    "media_type",
                    default="application/json",
                ),
                content=_payload_json_object(payload, "content"),
                created_at=_parse_timestamp(payload.get("created_at"))
                or event.timestamp,
                updated_at=_parse_timestamp(payload.get("updated_at"))
                or event.timestamp,
            )
        return list(artifact_by_key.values())

    def get_artifact(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        artifact_key: str,
    ) -> HarnessArtifactRecord | None:
        normalized_key = artifact_key.strip()
        if normalized_key == "":
            return None
        summary = self._runtime.get_latest_run_summary(
            run_id=str(run_id),
            tenant_id=str(space_id),
            summary_type=self._artifact_summary_type(normalized_key),
        )
        payload = _summary_payload(summary)
        if payload is None:
            return None
        timestamp = (
            _parse_timestamp(payload.get("updated_at"))
            or getattr(summary, "created_at", None)
            or _utcnow()
        )
        created_at = _parse_timestamp(payload.get("created_at")) or timestamp
        return HarnessArtifactRecord(
            space_id=str(space_id),
            run_id=str(run_id),
            key=normalized_key,
            media_type=_payload_string(
                payload,
                "media_type",
                default="application/json",
            ),
            content=_payload_json_object(payload, "content"),
            created_at=created_at,
            updated_at=timestamp,
        )

    def get_workspace(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessWorkspaceRecord | None:
        summary = self._runtime.get_latest_run_summary(
            run_id=str(run_id),
            tenant_id=str(space_id),
            summary_type=_WORKSPACE_SUMMARY,
        )
        payload = _summary_payload(summary)
        if payload is None:
            return None
        snapshot = payload.get("snapshot")
        if not isinstance(snapshot, dict):
            return None
        return HarnessWorkspaceRecord(
            space_id=str(space_id),
            run_id=str(run_id),
            snapshot=snapshot,
            created_at=_parse_timestamp(payload.get("created_at")) or _utcnow(),
            updated_at=_parse_timestamp(payload.get("updated_at")) or _utcnow(),
        )

    def put_artifact(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        artifact_key: str,
        media_type: str,
        content: JSONObject,
    ) -> HarnessArtifactRecord:
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        normalized_key = artifact_key.strip()
        now = _utcnow()
        artifact = HarnessArtifactRecord(
            space_id=normalized_space_id,
            run_id=normalized_run_id,
            key=normalized_key,
            media_type=media_type,
            content=content,
            created_at=now,
            updated_at=now,
        )
        self._runtime.append_run_summary(
            run_id=normalized_run_id,
            tenant_id=normalized_space_id,
            summary_type=self._artifact_summary_type(normalized_key),
            summary_json=json.dumps(
                {
                    "media_type": media_type,
                    "content": content,
                    "created_at": artifact.created_at.isoformat(),
                    "updated_at": artifact.updated_at.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            step_key=_step_key(f"artifact_{normalized_key}"),
        )
        workspace = self.get_workspace(space_id=space_id, run_id=run_id)
        if workspace is not None:
            artifact_keys = workspace.snapshot.get("artifact_keys")
            normalized_artifact_keys = (
                list(artifact_keys) if isinstance(artifact_keys, list) else []
            )
            if normalized_key not in normalized_artifact_keys:
                normalized_artifact_keys.append(normalized_key)
            self._write_workspace(
                space_id=normalized_space_id,
                run_id=normalized_run_id,
                snapshot={
                    **workspace.snapshot,
                    "artifact_keys": normalized_artifact_keys,
                    "last_updated_artifact_key": normalized_key,
                },
                created_at=workspace.created_at,
                updated_at=now,
            )
        return artifact

    def patch_workspace(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        patch: JSONObject,
    ) -> HarnessWorkspaceRecord | None:
        workspace = self.get_workspace(space_id=space_id, run_id=run_id)
        if workspace is None:
            return None
        return self._write_workspace(
            space_id=str(space_id),
            run_id=str(run_id),
            snapshot={**workspace.snapshot, **patch},
            created_at=workspace.created_at,
            updated_at=_utcnow(),
        )


__all__ = [
    "ArtanaBackedHarnessArtifactStore",
    "ArtanaBackedHarnessRunRegistry",
]
