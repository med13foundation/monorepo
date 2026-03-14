"""Service-local schedule storage contracts for graph-harness workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID, uuid4

from services.graph_harness_api.schedule_policy import normalize_schedule_cadence
from src.type_definitions.common import JSONObject  # noqa: TC001


@dataclass(frozen=True, slots=True)
class HarnessScheduleRecord:
    """One stored harness schedule definition."""

    id: str
    space_id: str
    harness_id: str
    title: str
    cadence: str
    status: str
    created_by: str
    configuration: JSONObject
    metadata: JSONObject
    last_run_id: str | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class HarnessScheduleStore:
    """Store and retrieve harness schedule definitions."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._schedules: dict[str, HarnessScheduleRecord] = {}

    def create_schedule(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        harness_id: str,
        title: str,
        cadence: str,
        created_by: UUID | str,
        configuration: JSONObject,
        metadata: JSONObject,
        status: str = "active",
    ) -> HarnessScheduleRecord:
        """Persist one new schedule definition."""
        now = datetime.now(UTC)
        normalized_cadence = normalize_schedule_cadence(cadence)
        record = HarnessScheduleRecord(
            id=str(uuid4()),
            space_id=str(space_id),
            harness_id=harness_id,
            title=title,
            cadence=normalized_cadence,
            status=status,
            created_by=str(created_by),
            configuration=configuration,
            metadata=metadata,
            last_run_id=None,
            last_run_at=None,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._schedules[record.id] = record
        return record

    def list_schedules(
        self,
        *,
        space_id: UUID | str,
    ) -> list[HarnessScheduleRecord]:
        """Return schedules for one research space ordered by freshness."""
        normalized_space_id = str(space_id)
        with self._lock:
            schedules = [
                record
                for record in self._schedules.values()
                if record.space_id == normalized_space_id
            ]
        return sorted(schedules, key=lambda record: record.updated_at, reverse=True)

    def list_all_schedules(
        self,
        *,
        status: str | None = None,
    ) -> list[HarnessScheduleRecord]:
        """Return all schedules, optionally filtered by status."""
        normalized_status = status.strip() if isinstance(status, str) else None
        with self._lock:
            schedules = list(self._schedules.values())
        filtered = [
            record
            for record in schedules
            if normalized_status is None or record.status == normalized_status
        ]
        return sorted(filtered, key=lambda record: record.updated_at, reverse=True)

    def get_schedule(
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
    ) -> HarnessScheduleRecord | None:
        """Return one schedule definition."""
        with self._lock:
            schedule = self._schedules.get(str(schedule_id))
        if schedule is None or schedule.space_id != str(space_id):
            return None
        return schedule

    def update_schedule(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
        title: str | None = None,
        cadence: str | None = None,
        status: str | None = None,
        configuration: JSONObject | None = None,
        metadata: JSONObject | None = None,
        last_run_id: UUID | str | None = None,
        last_run_at: datetime | None = None,
    ) -> HarnessScheduleRecord | None:
        """Update one stored schedule definition."""
        existing = self.get_schedule(space_id=space_id, schedule_id=schedule_id)
        if existing is None:
            return None
        updated = HarnessScheduleRecord(
            id=existing.id,
            space_id=existing.space_id,
            harness_id=existing.harness_id,
            title=(
                title
                if isinstance(title, str) and title.strip() != ""
                else existing.title
            ),
            cadence=(
                normalize_schedule_cadence(cadence)
                if isinstance(cadence, str) and cadence.strip() != ""
                else existing.cadence
            ),
            status=(
                status
                if isinstance(status, str) and status.strip() != ""
                else existing.status
            ),
            created_by=existing.created_by,
            configuration=(
                configuration if configuration is not None else existing.configuration
            ),
            metadata=metadata if metadata is not None else existing.metadata,
            last_run_id=(
                str(last_run_id) if last_run_id is not None else existing.last_run_id
            ),
            last_run_at=(
                last_run_at if last_run_at is not None else existing.last_run_at
            ),
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
        )
        with self._lock:
            self._schedules[existing.id] = updated
        return updated


__all__ = ["HarnessScheduleRecord", "HarnessScheduleStore"]
