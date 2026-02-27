from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from src.application.curation.repositories.audit_repository import AuditLogQuery
from src.application.services.audit_service import AuditTrailService
from src.models.database.audit import AuditLog

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class InMemoryAuditRepository:
    """Minimal in-memory repository for AuditTrailService unit tests."""

    def __init__(self) -> None:
        self._logs: list[AuditLog] = []
        self._next_id = 1

    def record(self, _db: Session, log: AuditLog) -> AuditLog:
        log.id = self._next_id
        self._next_id += 1
        if log.created_at is None:
            log.created_at = datetime.now(UTC)
        self._logs.append(log)
        return log

    def list_logs(
        self,
        _db: Session,
        *,
        query: AuditLogQuery,
        offset: int,
        limit: int,
    ) -> list[AuditLog]:
        filtered = self._filter_logs(query)
        ordered = sorted(
            filtered,
            key=lambda log: (log.created_at, log.id),
            reverse=True,
        )
        start = max(offset, 0)
        end = start + max(limit, 1)
        return ordered[start:end]

    def count_logs(self, _db: Session, *, query: AuditLogQuery) -> int:
        return len(self._filter_logs(query))

    def delete_older_than(self, _db: Session, *, cutoff: datetime, limit: int) -> int:
        effective_limit = max(limit, 1)
        old_logs = sorted(
            [log for log in self._logs if log.created_at < cutoff],
            key=lambda log: (log.created_at, log.id),
        )
        to_delete = {log.id for log in old_logs[:effective_limit]}
        deleted_count = len(to_delete)
        self._logs = [log for log in self._logs if log.id not in to_delete]
        return deleted_count

    def _filter_logs(self, query: AuditLogQuery) -> list[AuditLog]:
        logs = self._logs
        if query.action:
            logs = [log for log in logs if log.action == query.action]
        if query.entity_type:
            logs = [log for log in logs if log.entity_type == query.entity_type]
        if query.entity_id:
            logs = [log for log in logs if log.entity_id == query.entity_id]
        if query.actor_id:
            logs = [log for log in logs if log.user == query.actor_id]
        if query.success is not None:
            logs = [log for log in logs if log.success == query.success]
        if query.created_after is not None:
            logs = [log for log in logs if log.created_at >= query.created_after]
        if query.created_before is not None:
            logs = [log for log in logs if log.created_at <= query.created_before]
        return logs


def _make_log(
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    created_at: datetime,
    actor: str | None = None,
    success: bool | None = True,
) -> AuditLog:
    return AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        user=actor,
        success=success,
        details=None,
        created_at=created_at,
    )


def test_query_logs_applies_pagination(db_session: Session) -> None:
    repo = InMemoryAuditRepository()
    service = AuditTrailService(repo)

    now = datetime.now(UTC)
    repo.record(
        db_session,
        _make_log(
            action="phi.read",
            entity_type="test",
            entity_id="one",
            created_at=now - timedelta(minutes=3),
        ),
    )
    repo.record(
        db_session,
        _make_log(
            action="phi.read",
            entity_type="test",
            entity_id="two",
            created_at=now - timedelta(minutes=2),
        ),
    )
    repo.record(
        db_session,
        _make_log(
            action="phi.read",
            entity_type="test",
            entity_id="three",
            created_at=now - timedelta(minutes=1),
        ),
    )

    result = service.query_logs(
        db_session,
        query=AuditLogQuery(action="phi.read"),
        page=2,
        per_page=1,
    )

    assert result.total == 3
    assert result.page == 2
    assert result.per_page == 1
    assert len(result.logs) == 1
    assert result.logs[0].entity_id == "two"


def test_export_logs_supports_json_and_csv(db_session: Session) -> None:
    repo = InMemoryAuditRepository()
    service = AuditTrailService(repo)

    now = datetime.now(UTC)
    repo.record(
        db_session,
        _make_log(
            action="phi.read",
            entity_type="test",
            entity_id="json-csv-1",
            created_at=now,
        ),
    )
    repo.record(
        db_session,
        _make_log(
            action="phi.update",
            entity_type="test",
            entity_id="json-csv-2",
            created_at=now + timedelta(seconds=1),
        ),
    )

    exported_json = service.export_logs(
        db_session,
        query=AuditLogQuery(entity_type="test"),
        export_format="json",
        limit=50,
    )
    json_payload = json.loads(exported_json)

    assert isinstance(json_payload, list)
    assert len(json_payload) == 2
    assert json_payload[0]["entity_id"] == "json-csv-2"

    exported_csv = service.export_logs(
        db_session,
        query=AuditLogQuery(entity_type="test"),
        export_format="csv",
        limit=50,
    )
    assert exported_csv.startswith("id,created_at,action,entity_type")
    assert "json-csv-1" in exported_csv
    assert "json-csv-2" in exported_csv


def test_cleanup_old_logs_deletes_in_batches(db_session: Session) -> None:
    repo = InMemoryAuditRepository()
    service = AuditTrailService(repo)

    now = datetime.now(UTC)
    repo.record(
        db_session,
        _make_log(
            action="phi.read",
            entity_type="old",
            entity_id="old-1",
            created_at=now - timedelta(days=90),
        ),
    )
    repo.record(
        db_session,
        _make_log(
            action="phi.read",
            entity_type="old",
            entity_id="old-2",
            created_at=now - timedelta(days=60),
        ),
    )
    repo.record(
        db_session,
        _make_log(
            action="phi.read",
            entity_type="new",
            entity_id="new-1",
            created_at=now,
        ),
    )

    deleted = service.cleanup_old_logs(
        db_session,
        retention_days=30,
        batch_size=1,
    )

    assert deleted == 2
    remaining = repo.list_logs(
        db_session,
        query=AuditLogQuery(),
        offset=0,
        limit=10,
    )
    assert len(remaining) == 1
    assert remaining[0].entity_id == "new-1"


def test_cleanup_old_logs_rejects_invalid_retention(db_session: Session) -> None:
    repo = InMemoryAuditRepository()
    service = AuditTrailService(repo)

    with pytest.raises(ValueError, match="retention_days"):
        service.cleanup_old_logs(db_session, retention_days=0, batch_size=100)
