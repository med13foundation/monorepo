"""Unit tests for Artana-kernel-backed graph-harness lifecycle adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from services.graph_harness_api.artana_stores import (
    ArtanaBackedHarnessArtifactStore,
    ArtanaBackedHarnessRunRegistry,
)
from src.models.database import Base
from tests.graph_harness_api_support import (
    FakeStepToolResult,
    fake_tool_allowlist,
    fake_tool_result_payload,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True, slots=True)
class _FakeSummary:
    summary_json: str


@dataclass(frozen=True, slots=True)
class _FakeEventType:
    value: str


@dataclass(frozen=True, slots=True)
class _FakePayload:
    payload: dict[str, object]

    def model_dump(self, *, mode: str = "json") -> dict[str, object]:
        _ = mode
        return self.payload


@dataclass(frozen=True, slots=True)
class _FakeEvent:
    event_id: str
    event_type: _FakeEventType
    payload: _FakePayload
    timestamp: datetime


class _FakeKernelRuntime:
    def __init__(self) -> None:
        self._runs: set[tuple[str, str]] = set()
        self._summaries: dict[tuple[str, str, str], _FakeSummary] = {}
        self._events: dict[tuple[str, str], list[_FakeEvent]] = {}

    def ensure_run(self, *, run_id: str, tenant_id: str) -> bool:
        key = (tenant_id, run_id)
        if key in self._runs:
            return False
        self._runs.add(key)
        return True

    def append_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        summary_json: str,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> int:
        _ = parent_step_key
        summary = _FakeSummary(summary_json=summary_json)
        self._summaries[(tenant_id, run_id, summary_type)] = summary
        self._events.setdefault((tenant_id, run_id), []).append(
            _FakeEvent(
                event_id=f"{step_key}:{len(self._events.get((tenant_id, run_id), []))}",
                event_type=_FakeEventType(value="run_summary"),
                payload=_FakePayload(
                    payload={
                        "summary_type": summary_type,
                        "summary_json": summary_json,
                        "step_key": step_key,
                    },
                ),
                timestamp=datetime.now(UTC),
            ),
        )
        return len(self._events[(tenant_id, run_id)])

    def get_latest_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
    ) -> _FakeSummary | None:
        return self._summaries.get((tenant_id, run_id, summary_type))

    def get_events(
        self,
        *,
        run_id: str,
        tenant_id: str,
    ) -> tuple[_FakeEvent, ...]:
        return tuple(self._events.get((tenant_id, run_id), []))

    def get_run_status(self, *, run_id: str, tenant_id: str) -> None:
        _ = run_id, tenant_id

    def get_run_progress(self, *, run_id: str, tenant_id: str) -> None:
        _ = run_id, tenant_id

    def get_resume_point(self, *, run_id: str, tenant_id: str) -> None:
        _ = run_id, tenant_id

    def explain_tool_allowlist(
        self,
        *,
        tenant_id: str,
        run_id: str,
        visible_tool_names: set[str] | None = None,
    ) -> dict[str, object]:
        _ = tenant_id, run_id
        return fake_tool_allowlist(visible_tool_names=visible_tool_names)

    def step_tool(
        self,
        *,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        arguments,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> FakeStepToolResult:
        _ = run_id, tenant_id, step_key, parent_step_key
        return FakeStepToolResult(
            result_json=json.dumps(
                fake_tool_result_payload(tool_name=tool_name, arguments=arguments),
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
        )

    def reconcile_tool(
        self,
        *,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        arguments,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> str:
        _ = run_id, tenant_id, step_key, parent_step_key
        return json.dumps(
            fake_tool_result_payload(tool_name=tool_name, arguments=arguments),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    db_session = session_local()
    try:
        yield db_session
    finally:
        db_session.close()


def test_artana_backed_run_registry_persists_catalog_and_kernel_lifecycle(
    session: Session,
) -> None:
    runtime = _FakeKernelRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    space_id = str(uuid4())

    run = registry.create_run(
        space_id=space_id,
        harness_id="graph-chat",
        title="Chat run",
        input_payload={"question": "What is known?"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    assert run.status == "queued"
    progress = registry.get_progress(space_id=space_id, run_id=run.id)
    assert progress is not None
    assert progress.phase == "queued"

    updated = registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
    )
    assert updated is not None
    assert updated.status == "completed"

    finalized = registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="finalize",
        message="Artifacts finalized.",
        progress_percent=1.0,
        completed_steps=2,
        total_steps=2,
        metadata={"artifact_key": "chat_summary"},
        clear_resume_point=True,
    )
    assert finalized is not None
    assert finalized.progress_percent == 1.0
    assert finalized.metadata["artifact_key"] == "chat_summary"

    recorded_event = registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="run.summary_written",
        message="Summary stored.",
        payload={"artifact_key": "chat_summary"},
    )
    assert recorded_event is not None

    fetched = registry.get_run(space_id=space_id, run_id=run.id)
    assert fetched is not None
    assert fetched.status == "completed"

    events = registry.list_events(space_id=space_id, run_id=run.id)
    assert [event.event_type for event in events] == [
        "run.created",
        "run.status_changed",
        "run.progress",
        "run.summary_written",
    ]


def test_artana_backed_artifact_store_uses_kernel_summaries(
    session: Session,
) -> None:
    runtime = _FakeKernelRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    artifact_store = ArtanaBackedHarnessArtifactStore(runtime=runtime)
    space_id = str(uuid4())
    run = registry.create_run(
        space_id=space_id,
        harness_id="graph-search",
        title="Search run",
        input_payload={"question": "Find MED13 links"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    artifact_store.seed_for_run(run=run)
    seeded = artifact_store.list_artifacts(space_id=space_id, run_id=run.id)
    assert [artifact.key for artifact in seeded] == ["run_manifest"]

    workspace = artifact_store.get_workspace(space_id=space_id, run_id=run.id)
    assert workspace is not None
    assert workspace.snapshot["artifact_keys"] == ["run_manifest"]

    stored_artifact = artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="graph_search_result",
        media_type="application/json",
        content={"decision": "generated"},
    )
    assert stored_artifact.key == "graph_search_result"

    patched_workspace = artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "completed"},
    )
    assert patched_workspace is not None
    assert patched_workspace.snapshot["status"] == "completed"

    artifacts = artifact_store.list_artifacts(space_id=space_id, run_id=run.id)
    assert {artifact.key for artifact in artifacts} == {
        "run_manifest",
        "graph_search_result",
    }
    fetched = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="graph_search_result",
    )
    assert fetched is not None
    assert fetched.content["decision"] == "generated"
