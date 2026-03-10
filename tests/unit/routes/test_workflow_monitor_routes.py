"""Unit tests for workflow monitor route dependency helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.routes.research_spaces import workflow_monitor_routes as routes
from src.routes.research_spaces import workflow_monitor_stream_routes as stream_routes
from src.routes.research_spaces import workflow_monitor_stream_utils as stream_utils


class _StubPort:
    pass


class _ScriptedRequest:
    def __init__(self, disconnected_values: list[bool]) -> None:
        self._disconnected_values = disconnected_values
        self._index = 0

    async def is_disconnected(self) -> bool:
        if self._index >= len(self._disconnected_values):
            return True
        value = self._disconnected_values[self._index]
        self._index += 1
        return value


def _build_monitor_payload() -> dict[str, object]:
    return {
        "source_snapshot": {},
        "last_run": None,
        "pipeline_runs": [],
        "documents": [],
        "document_status_counts": {},
        "extraction_queue": [],
        "extraction_queue_status_counts": {},
        "publication_extractions": [],
        "publication_extraction_status_counts": {},
        "relation_review": {},
        "graph_summary": None,
        "operational_counters": {},
        "warnings": [],
    }


class _MonitorServiceStub:
    def __init__(self, events: list[dict[str, object]] | None = None) -> None:
        self._monitor_payload = _build_monitor_payload()
        self._events = events if events is not None else []

    def get_source_workflow_monitor(self, **_: object) -> dict[str, object]:
        return self._monitor_payload

    def list_workflow_events(self, **_: object) -> dict[str, object]:
        return {"events": self._events}


class _CostAndCompareMonitorServiceStub:
    def __init__(self) -> None:
        self.list_run_costs_calls: list[dict[str, object]] = []
        self.compare_source_runs_calls: list[dict[str, object]] = []

    def list_run_costs(self, **kwargs: object) -> dict[str, object]:
        self.list_run_costs_calls.append(kwargs)
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "items": [
                {
                    "run_id": "run-1",
                    "source_id": str(kwargs["source_id"] or uuid4()),
                    "research_space_id": str(kwargs["space_id"]),
                    "source_name": "PubMed Source",
                    "source_type": kwargs.get("source_type"),
                    "status": "completed",
                    "run_owner_user_id": kwargs.get("user_id"),
                    "run_owner_source": "triggered_by",
                    "started_at": datetime.now(UTC).isoformat(),
                    "completed_at": datetime.now(UTC).isoformat(),
                    "total_duration_ms": 1200,
                    "total_cost_usd": 1.25,
                    "extracted_documents": 3,
                    "persisted_relations": 8,
                },
            ],
            "total": 1,
        }

    def compare_source_runs(self, **kwargs: object) -> dict[str, object]:
        self.compare_source_runs_calls.append(kwargs)
        return {
            "source_id": str(kwargs["source_id"]),
            "run_a_id": kwargs["run_a_id"],
            "run_b_id": kwargs["run_b_id"],
            "generated_at": datetime.now(UTC).isoformat(),
            "run_a": {"run_id": kwargs["run_a_id"], "status": "completed"},
            "run_b": {"run_id": kwargs["run_b_id"], "status": "completed"},
            "delta": {"total_cost_usd": 0.5},
        }


class _NotFoundMonitorServiceStub:
    def get_pipeline_run_summary(self, **_: object) -> dict[str, object]:
        msg = "Pipeline run not found for this source"
        raise LookupError(msg)

    def get_document_trace(self, **_: object) -> dict[str, object]:
        msg = "Document not found for this pipeline run"
        raise LookupError(msg)

    def get_query_generation_trace(self, **_: object) -> dict[str, object]:
        msg = "Pipeline run not found for this source"
        raise LookupError(msg)

    def compare_source_runs(self, **_: object) -> dict[str, object]:
        msg = "Pipeline run 'missing-run' not found for this source"
        raise LookupError(msg)


def _extract_data_payload(sse_event: str) -> dict[str, object]:
    data_line = next(
        line for line in sse_event.splitlines() if line.startswith("data: ")
    )
    parsed = json.loads(data_line.removeprefix("data: "))
    return parsed if isinstance(parsed, dict) else {}


def test_get_run_progress_port_retries_after_backoff(monkeypatch) -> None:
    routes._reset_run_progress_port_cache_for_tests()

    calls = {"count": 0}
    expected_port = _StubPort()

    def _build_port() -> _StubPort:
        calls["count"] += 1
        if calls["count"] == 1:
            msg = "transient startup failure"
            raise RuntimeError(msg)
        return expected_port

    monotonic_values = iter((100.0, 110.0, 131.0, 132.0))

    monkeypatch.setattr(routes, "_build_run_progress_port", _build_port)
    monkeypatch.setattr(routes, "monotonic", lambda: next(monotonic_values))

    first = routes.get_run_progress_port()
    second = routes.get_run_progress_port()
    third = routes.get_run_progress_port()
    fourth = routes.get_run_progress_port()

    assert first is None
    assert second is None
    assert third is expected_port
    assert fourth is expected_port
    assert calls["count"] == 2

    routes._reset_run_progress_port_cache_for_tests()


def test_parse_requested_source_ids_returns_unique_uuid_strings() -> None:
    first = str(uuid4())
    second = str(uuid4())

    parsed = stream_utils.parse_requested_source_ids(f"{first}, {second}, {first}")

    assert parsed == [first, second]


def test_parse_requested_source_ids_rejects_invalid_uuid() -> None:
    with pytest.raises(ValueError, match="Invalid source id in source_ids"):
        stream_utils.parse_requested_source_ids("not-a-uuid")


def test_list_space_pipeline_run_costs_forwards_query_filters(monkeypatch) -> None:
    monkeypatch.setattr(routes, "verify_space_membership", lambda *args, **kwargs: None)
    service = _CostAndCompareMonitorServiceStub()
    space_id = uuid4()

    response = routes.list_space_pipeline_run_costs(
        space_id=space_id,
        query=routes.CostReportQueryParams(
            source_type="pubmed",
            user_id="user-123",
            date_from="2026-01-01T00:00:00Z",
            date_to="2026-01-31T23:59:59Z",
            limit=25,
        ),
        current_user=SimpleNamespace(id=uuid4(), role="member"),
        membership_service=object(),
        monitor_service=service,
        session=object(),
    )

    assert response.total == 1
    assert response.items[0].run_owner_user_id == "user-123"
    assert service.list_run_costs_calls == [
        {
            "space_id": space_id,
            "source_id": None,
            "source_type": "pubmed",
            "user_id": "user-123",
            "date_from": "2026-01-01T00:00:00Z",
            "date_to": "2026-01-31T23:59:59Z",
            "limit": 25,
        },
    ]


def test_list_user_pipeline_run_costs_prefers_path_user_id(monkeypatch) -> None:
    monkeypatch.setattr(routes, "verify_space_membership", lambda *args, **kwargs: None)
    service = _CostAndCompareMonitorServiceStub()
    space_id = uuid4()

    response = routes.list_user_pipeline_run_costs(
        space_id=space_id,
        user_id="path-user",
        query=routes.CostReportQueryParams(
            source_type="pubmed",
            user_id="query-user",
            date_from=None,
            date_to=None,
            limit=10,
        ),
        current_user=SimpleNamespace(id=uuid4(), role="member"),
        membership_service=object(),
        monitor_service=service,
        session=object(),
    )

    assert response.items[0].run_owner_user_id == "path-user"
    assert service.list_run_costs_calls == [
        {
            "space_id": space_id,
            "source_id": None,
            "source_type": "pubmed",
            "user_id": "path-user",
            "date_from": None,
            "date_to": None,
            "limit": 10,
        },
    ]


def test_compare_source_pipeline_runs_returns_validated_payload(monkeypatch) -> None:
    monkeypatch.setattr(routes, "verify_space_membership", lambda *args, **kwargs: None)
    service = _CostAndCompareMonitorServiceStub()
    space_id = uuid4()
    source_id = uuid4()

    response = routes.compare_source_pipeline_runs(
        space_id=space_id,
        source_id=source_id,
        run_a="run-a",
        run_b="run-b",
        route_context=routes.WorkflowMonitorRouteContext(
            current_user=SimpleNamespace(id=uuid4(), role="member"),
            membership_service=object(),
            monitor_service=service,
            session=object(),
        ),
    )

    assert response.source_id == source_id
    assert response.delta == {"total_cost_usd": 0.5}
    assert service.compare_source_runs_calls == [
        {
            "space_id": space_id,
            "source_id": source_id,
            "run_a_id": "run-a",
            "run_b_id": "run-b",
        },
    ]


def test_get_source_pipeline_run_summary_returns_404_for_missing_run(
    monkeypatch,
) -> None:
    monkeypatch.setattr(routes, "verify_space_membership", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        routes.get_source_pipeline_run_summary(
            space_id=uuid4(),
            source_id=uuid4(),
            run_id="missing-run",
            current_user=SimpleNamespace(id=uuid4(), role="member"),
            membership_service=object(),
            monitor_service=_NotFoundMonitorServiceStub(),
            session=object(),
        )

    assert exc_info.value.status_code == 404


def test_get_source_document_trace_returns_404_for_missing_document(
    monkeypatch,
) -> None:
    monkeypatch.setattr(routes, "verify_space_membership", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        routes.get_source_document_trace(
            space_id=uuid4(),
            source_id=uuid4(),
            run_id="run-1",
            document_id=uuid4(),
            route_context=routes.WorkflowMonitorRouteContext(
                current_user=SimpleNamespace(id=uuid4(), role="member"),
                membership_service=object(),
                monitor_service=_NotFoundMonitorServiceStub(),
                session=object(),
            ),
        )

    assert exc_info.value.status_code == 404


def test_get_source_query_trace_returns_404_for_missing_run(monkeypatch) -> None:
    monkeypatch.setattr(routes, "verify_space_membership", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        routes.get_source_query_trace(
            space_id=uuid4(),
            source_id=uuid4(),
            run_id="missing-run",
            current_user=SimpleNamespace(id=uuid4(), role="member"),
            membership_service=object(),
            monitor_service=_NotFoundMonitorServiceStub(),
            session=object(),
        )

    assert exc_info.value.status_code == 404


def test_compare_source_pipeline_runs_returns_404_for_missing_run(
    monkeypatch,
) -> None:
    monkeypatch.setattr(routes, "verify_space_membership", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        routes.compare_source_pipeline_runs(
            space_id=uuid4(),
            source_id=uuid4(),
            run_a="missing-run",
            run_b="run-b",
            route_context=routes.WorkflowMonitorRouteContext(
                current_user=SimpleNamespace(id=uuid4(), role="member"),
                membership_service=object(),
                monitor_service=_NotFoundMonitorServiceStub(),
                session=object(),
            ),
        )

    assert exc_info.value.status_code == 404


def test_sse_event_payload_serializes_to_expected_shape() -> None:
    payload = stream_utils.sse_event_payload(
        event="heartbeat",
        sequence=3,
        data={"ok": True},
    )

    assert "event: heartbeat" in payload
    assert "id: 3" in payload
    assert "data: " in payload
    data_line = next(line for line in payload.splitlines() if line.startswith("data: "))
    assert json.loads(data_line.removeprefix("data: ")) == {"ok": True}


def test_workflow_sse_flag_parser_accepts_enabled_values(monkeypatch) -> None:
    monkeypatch.setenv("MED13_ENABLE_WORKFLOW_SSE", "true")
    assert stream_utils.is_workflow_sse_enabled() is True
    monkeypatch.setenv("MED13_ENABLE_WORKFLOW_SSE", "1")
    assert stream_utils.is_workflow_sse_enabled() is True
    monkeypatch.setenv("MED13_ENABLE_WORKFLOW_SSE", "false")
    assert stream_utils.is_workflow_sse_enabled() is False


@pytest.mark.asyncio
async def test_stream_source_workflow_monitor_returns_404_when_disabled(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_WORKFLOW_SSE", "false")

    request = Request({"type": "http", "headers": []})
    with pytest.raises(HTTPException) as exc_info:
        await stream_routes.stream_source_workflow_monitor(
            request=request,
            space_id=uuid4(),
            source_id=uuid4(),
            query=routes.WorkflowMonitorQueryParams(),
            current_user=None,
            membership_context=stream_routes._MembershipContext(
                membership_service=object(),
                session=object(),
            ),
            monitor_service=None,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_stream_space_workflow_cards_returns_404_when_disabled(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_WORKFLOW_SSE", "false")

    request = Request({"type": "http", "headers": []})
    with pytest.raises(HTTPException) as exc_info:
        await stream_routes.stream_space_workflow_cards(
            request=request,
            space_id=uuid4(),
            query=stream_routes.WorkflowSpaceStreamQueryParams(),
            current_user=None,
            membership_context=stream_routes._MembershipContext(
                membership_service=object(),
                session=object(),
            ),
            monitor_service=None,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_stream_source_workflow_monitor_emits_bootstrap_and_stops_on_disconnect(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_WORKFLOW_SSE", "true")
    monkeypatch.setattr(
        stream_routes.space_dependencies,
        "verify_space_membership",
        lambda *args, **kwargs: None,
    )

    response = await stream_routes.stream_source_workflow_monitor(
        request=_ScriptedRequest([True]),
        space_id=uuid4(),
        source_id=uuid4(),
        query=routes.WorkflowMonitorQueryParams(),
        current_user=SimpleNamespace(id=uuid4(), role="member"),
        membership_context=stream_routes._MembershipContext(
            membership_service=object(),
            session=object(),
        ),
        monitor_service=_MonitorServiceStub(),
    )

    first_event = await anext(response.body_iterator)
    assert "event: bootstrap" in first_event
    payload = _extract_data_payload(first_event)
    assert "monitor" in payload
    assert payload.get("run_id") is None

    with pytest.raises(StopAsyncIteration):
        await anext(response.body_iterator)


@pytest.mark.asyncio
async def test_stream_source_workflow_monitor_emits_heartbeat_when_idle(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_WORKFLOW_SSE", "true")
    monkeypatch.setattr(
        stream_routes.space_dependencies,
        "verify_space_membership",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(stream_utils, "STREAM_HEARTBEAT_SECONDS", 0.0)
    monkeypatch.setattr(stream_utils, "STREAM_TICK_SECONDS", 0.0)

    response = await stream_routes.stream_source_workflow_monitor(
        request=_ScriptedRequest([False, True]),
        space_id=uuid4(),
        source_id=uuid4(),
        query=routes.WorkflowMonitorQueryParams(),
        current_user=SimpleNamespace(id=uuid4(), role="member"),
        membership_context=stream_routes._MembershipContext(
            membership_service=object(),
            session=object(),
        ),
        monitor_service=_MonitorServiceStub(),
    )

    first_event = await anext(response.body_iterator)
    second_event = await anext(response.body_iterator)

    assert "event: bootstrap" in first_event
    assert "event: heartbeat" in second_event


@pytest.mark.asyncio
async def test_stream_space_workflow_cards_emits_bootstrap_payload(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_WORKFLOW_SSE", "true")
    monkeypatch.setattr(
        stream_routes.space_dependencies,
        "verify_space_membership",
        lambda *args, **kwargs: None,
    )
    source_id = str(uuid4())
    monkeypatch.setattr(
        stream_utils,
        "resolve_space_source_ids",
        lambda **_: [source_id],
    )
    event_payload = {
        "event_id": str(uuid4()),
        "occurred_at": "2026-03-02T20:00:00+00:00",
        "category": "run",
        "stage": "ingestion",
        "status": "running",
        "message": "running",
    }

    response = await stream_routes.stream_space_workflow_cards(
        request=_ScriptedRequest([True]),
        space_id=uuid4(),
        query=stream_routes.WorkflowSpaceStreamQueryParams(),
        current_user=SimpleNamespace(id=uuid4(), role="member"),
        membership_context=stream_routes._MembershipContext(
            membership_service=object(),
            session=object(),
        ),
        monitor_service=_MonitorServiceStub(events=[event_payload]),
    )

    first_event = await anext(response.body_iterator)
    assert "event: bootstrap" in first_event
    payload = _extract_data_payload(first_event)
    sources_raw = payload.get("sources")
    assert isinstance(sources_raw, list)
    assert len(sources_raw) == 1
    source_payload = sources_raw[0]
    assert isinstance(source_payload, dict)
    assert source_payload.get("source_id") == source_id


@pytest.mark.asyncio
async def test_stream_source_workflow_monitor_enforces_membership(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_WORKFLOW_SSE", "true")

    def _reject_membership(*_: object, **__: object) -> None:
        raise HTTPException(status_code=403, detail="forbidden")

    monkeypatch.setattr(
        stream_routes.space_dependencies,
        "verify_space_membership",
        _reject_membership,
    )

    with pytest.raises(HTTPException) as exc_info:
        await stream_routes.stream_source_workflow_monitor(
            request=_ScriptedRequest([True]),
            space_id=uuid4(),
            source_id=uuid4(),
            query=routes.WorkflowMonitorQueryParams(),
            current_user=SimpleNamespace(id=uuid4(), role="member"),
            membership_context=stream_routes._MembershipContext(
                membership_service=object(),
                session=object(),
            ),
            monitor_service=_MonitorServiceStub(),
        )

    assert exc_info.value.status_code == 403
