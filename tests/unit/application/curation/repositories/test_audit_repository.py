from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.application.curation.repositories.audit_repository import (
    AuditLogQuery,
    SqlAlchemyAuditRepository,
)
from src.models.database.audit import AuditLog

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _seed_log(
    session: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    created_at: datetime,
    actor: str | None = None,
    success: bool | None = True,
) -> AuditLog:
    log = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        user=actor,
        success=success,
        details=None,
        created_at=created_at,
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


def test_list_and_count_logs_apply_filters(db_session: Session) -> None:
    repository = SqlAlchemyAuditRepository()
    now = datetime.now(UTC)

    _seed_log(
        db_session,
        action="phi.read",
        entity_type="repo_test",
        entity_id="target",
        actor="user-a",
        success=True,
        created_at=now - timedelta(minutes=2),
    )
    _seed_log(
        db_session,
        action="phi.update",
        entity_type="repo_test",
        entity_id="target",
        actor="user-a",
        success=False,
        created_at=now - timedelta(minutes=1),
    )
    _seed_log(
        db_session,
        action="phi.read",
        entity_type="repo_test",
        entity_id="other",
        actor="user-b",
        success=True,
        created_at=now,
    )

    query = AuditLogQuery(action="phi.read", entity_id="target", actor_id="user-a")
    records = repository.list_logs(
        db_session,
        query=query,
        offset=0,
        limit=10,
    )
    count = repository.count_logs(db_session, query=query)

    assert count == 1
    assert len(records) == 1
    assert records[0].action == "phi.read"
    assert records[0].entity_id == "target"


def test_delete_older_than_respects_limit(db_session: Session) -> None:
    repository = SqlAlchemyAuditRepository()
    now = datetime.now(UTC)

    _seed_log(
        db_session,
        action="phi.read",
        entity_type="repo_cleanup",
        entity_id="old-1",
        created_at=now - timedelta(days=120),
    )
    _seed_log(
        db_session,
        action="phi.read",
        entity_type="repo_cleanup",
        entity_id="old-2",
        created_at=now - timedelta(days=90),
    )
    _seed_log(
        db_session,
        action="phi.read",
        entity_type="repo_cleanup",
        entity_id="old-3",
        created_at=now - timedelta(days=60),
    )
    _seed_log(
        db_session,
        action="phi.read",
        entity_type="repo_cleanup",
        entity_id="new-1",
        created_at=now,
    )

    cutoff = now - timedelta(days=30)

    first_deleted = repository.delete_older_than(
        db_session,
        cutoff=cutoff,
        limit=2,
    )
    second_deleted = repository.delete_older_than(
        db_session,
        cutoff=cutoff,
        limit=2,
    )

    assert first_deleted == 2
    assert second_deleted == 1

    remaining = repository.list_logs(
        db_session,
        query=AuditLogQuery(entity_type="repo_cleanup"),
        offset=0,
        limit=10,
    )
    assert len(remaining) == 1
    assert remaining[0].entity_id == "new-1"
