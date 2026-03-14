"""Unit tests for the graph-harness schedule queueing loop."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from services.graph_harness_api.artifact_store import HarnessArtifactStore
from services.graph_harness_api.run_registry import HarnessRunRegistry
from services.graph_harness_api.schedule_policy import is_schedule_due
from services.graph_harness_api.schedule_store import (
    HarnessScheduleRecord,
    HarnessScheduleStore,
)
from services.graph_harness_api.scheduler import run_scheduler_tick


def test_is_schedule_due_uses_period_windows() -> None:
    now = datetime(2026, 3, 13, 15, 0, tzinfo=UTC)

    assert is_schedule_due(cadence="manual", last_run_at=None, now=now) is False
    assert is_schedule_due(
        cadence="hourly",
        last_run_at=now - timedelta(hours=1),
        now=now,
    )
    assert is_schedule_due(
        cadence="daily",
        last_run_at=now - timedelta(days=1),
        now=now,
    )
    assert is_schedule_due(
        cadence="weekly",
        last_run_at=now - timedelta(days=7),
        now=now,
    )
    assert is_schedule_due(
        cadence="weekday",
        last_run_at=now - timedelta(days=1),
        now=now,
    )
    assert is_schedule_due(cadence="daily", last_run_at=now, now=now) is False


def test_run_scheduler_tick_queues_due_schedules() -> None:
    schedule_store = HarnessScheduleStore()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    space_id = uuid4()
    created = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Daily refresh",
        cadence="daily",
        created_by=uuid4(),
        configuration={
            "seed_entity_ids": ["11111111-1111-1111-1111-111111111111"],
            "source_type": "pubmed",
        },
        metadata={},
    )
    schedule_store.update_schedule(
        space_id=space_id,
        schedule_id=created.id,
        last_run_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
    )

    result = asyncio.run(
        run_scheduler_tick(
            schedule_store=schedule_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            now=datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
        ),
    )

    assert result.scanned_schedule_count == 1
    assert result.due_schedule_count == 1
    assert len(result.triggered_runs) == 1
    assert result.errors == ()

    updated_schedule = schedule_store.get_schedule(
        space_id=space_id,
        schedule_id=created.id,
    )
    assert updated_schedule is not None
    assert updated_schedule.last_run_id == result.triggered_runs[0].run_id
    assert updated_schedule.last_run_at is not None

    runs = run_registry.list_runs(space_id=space_id)
    assert len(runs) == 1
    assert runs[0].harness_id == "continuous-learning"
    assert runs[0].status == "queued"
    progress = run_registry.get_progress(space_id=space_id, run_id=runs[0].id)
    assert progress is not None
    assert progress.phase == "queued"

    workspace = artifact_store.get_workspace(space_id=space_id, run_id=runs[0].id)
    assert workspace is not None
    assert workspace.snapshot["status"] == "queued"
    assert workspace.snapshot["schedule_id"] == created.id


def test_run_scheduler_tick_skips_not_due_and_manual_schedules() -> None:
    schedule_store = HarnessScheduleStore()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    space_id = uuid4()
    schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Manual refresh",
        cadence="manual",
        created_by=uuid4(),
        configuration={"seed_entity_ids": ["entity-1"], "source_type": "pubmed"},
        metadata={},
    )
    daily_schedule = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Daily refresh",
        cadence="daily",
        created_by=uuid4(),
        configuration={"seed_entity_ids": ["entity-1"], "source_type": "pubmed"},
        metadata={},
    )
    schedule_store.update_schedule(
        space_id=space_id,
        schedule_id=daily_schedule.id,
        last_run_at=datetime(2026, 3, 13, 8, 0, tzinfo=UTC),
    )
    paused_schedule = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Paused refresh",
        cadence="daily",
        created_by=uuid4(),
        configuration={"seed_entity_ids": ["entity-1"], "source_type": "pubmed"},
        metadata={},
    )
    schedule_store.update_schedule(
        space_id=space_id,
        schedule_id=paused_schedule.id,
        status="paused",
        last_run_at=datetime(2026, 3, 12, 8, 0, tzinfo=UTC),
    )

    result = asyncio.run(
        run_scheduler_tick(
            schedule_store=schedule_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            now=datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
        ),
    )

    assert result.scanned_schedule_count == 2
    assert result.due_schedule_count == 0
    assert result.triggered_runs == ()
    assert result.errors == ()
    assert run_registry.list_runs(space_id=space_id) == []


def test_run_scheduler_tick_records_schedule_configuration_errors() -> None:
    schedule_store = HarnessScheduleStore()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    space_id = str(uuid4())
    invalid_schedule = HarnessScheduleRecord(
        id="invalid-schedule",
        space_id=space_id,
        harness_id="continuous-learning",
        title="Broken refresh",
        cadence="daily",
        status="active",
        created_by=str(uuid4()),
        configuration={"seed_entity_ids": [], "source_type": "pubmed"},
        metadata={},
        last_run_id=None,
        last_run_at=None,
        created_at=datetime(2026, 3, 12, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 3, 12, 8, 0, tzinfo=UTC),
    )
    schedule_store._schedules[invalid_schedule.id] = invalid_schedule  # noqa: SLF001

    result = asyncio.run(
        run_scheduler_tick(
            schedule_store=schedule_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            now=datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
        ),
    )

    assert result.due_schedule_count == 1
    assert result.triggered_runs == ()
    assert len(result.errors) == 1
    assert "missing required seed_entity_ids" in result.errors[0]
