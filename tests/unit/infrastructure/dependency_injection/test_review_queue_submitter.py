"""Unit tests for review-queue submission dedupe behavior."""

from __future__ import annotations

from sqlalchemy import select

from src.infrastructure.dependency_injection.service_factories import (
    ApplicationServiceFactoryMixin,
)
from src.models.database.review import ReviewRecord


def test_review_queue_submitter_dedupes_pending_entries(db_session) -> None:
    submitter = ApplicationServiceFactoryMixin._build_review_queue_submitter(db_session)

    submitter("relation_claim", "claim-1", None, "high")
    submitter("relation_claim", "claim-1", None, "high")

    records = db_session.scalars(
        select(ReviewRecord).where(
            ReviewRecord.entity_type == "relation_claim",
            ReviewRecord.entity_id == "claim-1",
            ReviewRecord.research_space_id.is_(None),
        ),
    ).all()
    assert len(records) == 1
    assert records[0].status == "pending"


def test_review_queue_submitter_allows_new_entry_after_non_pending_status(
    db_session,
) -> None:
    submitter = ApplicationServiceFactoryMixin._build_review_queue_submitter(db_session)

    submitter("relation_claim", "claim-2", None, "high")
    existing = db_session.scalars(
        select(ReviewRecord).where(
            ReviewRecord.entity_type == "relation_claim",
            ReviewRecord.entity_id == "claim-2",
            ReviewRecord.research_space_id.is_(None),
        ),
    ).one()
    existing.status = "approved"
    db_session.commit()

    submitter("relation_claim", "claim-2", None, "high")
    records = db_session.scalars(
        select(ReviewRecord).where(
            ReviewRecord.entity_type == "relation_claim",
            ReviewRecord.entity_id == "claim-2",
            ReviewRecord.research_space_id.is_(None),
        ),
    ).all()
    assert len(records) == 2
