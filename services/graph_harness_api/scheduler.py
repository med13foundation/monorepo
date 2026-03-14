"""Due-run selection and queueing for recurring graph-harness workflows."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from services.graph_harness_api.artana_stores import (
    ArtanaBackedHarnessArtifactStore,
    ArtanaBackedHarnessRunRegistry,
)
from services.graph_harness_api.composition import get_graph_harness_kernel_runtime
from services.graph_harness_api.config import get_settings
from services.graph_harness_api.continuous_learning_runtime import (
    normalize_seed_entity_ids,
    queue_continuous_learning_run,
)
from services.graph_harness_api.run_budget import (
    budget_from_json,
    resolve_continuous_learning_run_budget,
)
from services.graph_harness_api.schedule_policy import is_schedule_due
from services.graph_harness_api.sqlalchemy_stores import (
    SqlAlchemyHarnessScheduleStore,
)
from src.database.session import SessionLocal, set_session_rls_context
from src.type_definitions.common import JSONObject  # noqa: TC001

if TYPE_CHECKING:
    from services.graph_harness_api.artifact_store import HarnessArtifactStore
    from services.graph_harness_api.run_registry import HarnessRunRegistry
    from services.graph_harness_api.schedule_store import (
        HarnessScheduleRecord,
        HarnessScheduleStore,
    )

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TriggeredScheduleRun:
    """One schedule execution triggered by a scheduler tick."""

    schedule_id: str
    space_id: str
    run_id: str


@dataclass(frozen=True, slots=True)
class SchedulerTickResult:
    """Summary of one scheduler tick."""

    started_at: datetime
    completed_at: datetime
    scanned_schedule_count: int
    due_schedule_count: int
    triggered_runs: tuple[TriggeredScheduleRun, ...]
    errors: tuple[str, ...]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        item.strip() for item in value if isinstance(item, str) and item.strip() != ""
    ]


def _schedule_configuration(schedule: HarnessScheduleRecord) -> JSONObject:
    return schedule.configuration if isinstance(schedule.configuration, dict) else {}


def _configuration_string(
    configuration: JSONObject,
    key: str,
    *,
    default: str,
) -> str:
    value = configuration.get(key)
    return value if isinstance(value, str) else default


def _configuration_optional_string(
    configuration: JSONObject,
    key: str,
) -> str | None:
    value = configuration.get(key)
    return value if isinstance(value, str) else None


def _configuration_int(
    configuration: JSONObject,
    key: str,
    *,
    default: int,
) -> int:
    value = configuration.get(key)
    return value if isinstance(value, int) else default


async def _queue_schedule_run(
    *,
    schedule: HarnessScheduleRecord,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    schedule_store: HarnessScheduleStore,
) -> TriggeredScheduleRun:
    configuration = _schedule_configuration(schedule)
    seed_entity_ids = normalize_seed_entity_ids(
        _string_list(configuration.get("seed_entity_ids")),
    )
    if not seed_entity_ids:
        message = f"Schedule '{schedule.id}' is missing required seed_entity_ids"
        raise ValueError(message)
    run_budget = resolve_continuous_learning_run_budget(
        budget_from_json(configuration.get("run_budget")),
    )
    run = queue_continuous_learning_run(
        space_id=UUID(schedule.space_id),
        title=schedule.title,
        seed_entity_ids=seed_entity_ids,
        source_type=_configuration_string(
            configuration,
            "source_type",
            default="pubmed",
        ),
        relation_types=_string_list(configuration.get("relation_types")) or None,
        max_depth=_configuration_int(configuration, "max_depth", default=2),
        max_new_proposals=_configuration_int(
            configuration,
            "max_new_proposals",
            default=20,
        ),
        max_next_questions=_configuration_int(
            configuration,
            "max_next_questions",
            default=5,
        ),
        model_id=_configuration_optional_string(configuration, "model_id"),
        schedule_id=schedule.id,
        run_budget=run_budget,
        graph_service_status="queued",
        graph_service_version="pending",
        previous_graph_snapshot_id=None,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    artifact_store.patch_workspace(
        space_id=schedule.space_id,
        run_id=run.id,
        patch={
            "schedule_id": schedule.id,
            "queued_by": "scheduler",
            "run_budget": run_budget.model_dump(mode="json"),
        },
    )
    run_registry.record_event(
        space_id=schedule.space_id,
        run_id=run.id,
        event_type="schedule.triggered",
        message="Scheduled run queued for worker execution.",
        payload={"schedule_id": schedule.id, "cadence": schedule.cadence},
        progress_percent=0.0,
    )
    updated_schedule = schedule_store.update_schedule(
        space_id=schedule.space_id,
        schedule_id=schedule.id,
        last_run_id=run.id,
        last_run_at=run.created_at,
    )
    if updated_schedule is None:
        message = f"Schedule '{schedule.id}' disappeared during execution"
        raise RuntimeError(message)
    return TriggeredScheduleRun(
        schedule_id=schedule.id,
        space_id=schedule.space_id,
        run_id=run.id,
    )


def _scheduler_error_message(schedule: HarnessScheduleRecord, exc: Exception) -> str:
    return f"schedule:{schedule.id}:{exc}"


async def run_scheduler_tick(
    *,
    schedule_store: HarnessScheduleStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    now: datetime | None = None,
) -> SchedulerTickResult:
    """Queue all active schedules that are due in the current tick."""
    if isinstance(now, datetime):
        started_at = (
            now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
        )
    else:
        started_at = datetime.now(UTC)
    schedules = schedule_store.list_all_schedules(status="active")
    due_schedule_count = 0
    triggered_runs: list[TriggeredScheduleRun] = []
    errors: list[str] = []
    for schedule in schedules:
        try:
            if not is_schedule_due(
                cadence=schedule.cadence,
                last_run_at=schedule.last_run_at,
                now=started_at,
            ):
                continue
            due_schedule_count += 1
            triggered_runs.append(
                await _queue_schedule_run(
                    schedule=schedule,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    schedule_store=schedule_store,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(_scheduler_error_message(schedule, exc))
    return SchedulerTickResult(
        started_at=started_at,
        completed_at=datetime.now(UTC),
        scanned_schedule_count=len(schedules),
        due_schedule_count=due_schedule_count,
        triggered_runs=tuple(triggered_runs),
        errors=tuple(errors),
    )


async def run_service_scheduler_tick(
    *,
    now: datetime | None = None,
) -> SchedulerTickResult:
    """Run one queueing tick against the service's durable stores."""
    with SessionLocal() as session:
        set_session_rls_context(session, bypass_rls=False)
        runtime = get_graph_harness_kernel_runtime()
        return await run_scheduler_tick(
            schedule_store=SqlAlchemyHarnessScheduleStore(session),
            run_registry=ArtanaBackedHarnessRunRegistry(
                session=session,
                runtime=runtime,
            ),
            artifact_store=ArtanaBackedHarnessArtifactStore(runtime=runtime),
            now=now,
        )


async def run_scheduler_loop(
    *,
    poll_seconds: float,
    run_once: bool,
) -> None:
    """Run the thin scheduler loop until stopped or after one tick."""
    if poll_seconds <= 0:
        message = "poll_seconds must be greater than zero"
        raise ValueError(message)
    while True:
        result = await run_service_scheduler_tick()
        LOGGER.info(
            "Harness scheduler tick completed: scanned=%s due=%s triggered=%s errors=%s",
            result.scanned_schedule_count,
            result.due_schedule_count,
            len(result.triggered_runs),
            len(result.errors),
        )
        if run_once:
            return
        await asyncio.sleep(poll_seconds)


def main() -> None:
    """Start the schedule-queueing loop for recurring harness schedules."""
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    asyncio.run(
        run_scheduler_loop(
            poll_seconds=settings.scheduler_poll_seconds,
            run_once=settings.scheduler_run_once,
        ),
    )


if __name__ == "__main__":
    main()


__all__ = [
    "SchedulerTickResult",
    "TriggeredScheduleRun",
    "main",
    "run_scheduler_loop",
    "run_scheduler_tick",
    "run_service_scheduler_tick",
]
