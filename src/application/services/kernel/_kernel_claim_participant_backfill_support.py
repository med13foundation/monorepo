"""Support types and queries for claim participant backfill."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import and_, or_, select

from src.models.database.kernel.relation_claims import RelationClaimModel
from src.models.database.kernel.relation_projection_sources import (
    RelationProjectionSourceModel,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ClaimParticipantBackfillSummary:
    """Backfill result summary for one research space."""

    scanned_claims: int
    created_participants: int
    skipped_existing: int
    unresolved_endpoints: int
    dry_run: bool


@dataclass(frozen=True)
class ClaimParticipantCoverageSummary:
    """Coverage summary for claim participant anchors in one research space."""

    total_claims: int
    claims_with_any_participants: int
    claims_with_subject: int
    claims_with_object: int
    unresolved_subject_endpoints: int
    unresolved_object_endpoints: int


@dataclass(frozen=True)
class ClaimParticipantBackfillGlobalSummary:
    """Backfill result summary across all research spaces."""

    scanned_claims: int
    created_participants: int
    skipped_existing: int
    unresolved_endpoints: int
    research_spaces: int
    dry_run: bool


@dataclass(frozen=True)
class _Anchor:
    entity_id: str | None
    label: str | None


def list_projection_relevant_claim_models(
    session: Session,
    *,
    limit: int,
    offset: int,
) -> list[RelationClaimModel]:
    projection_exists = (
        select(RelationProjectionSourceModel.id)
        .where(
            RelationProjectionSourceModel.claim_id == RelationClaimModel.id,
            RelationProjectionSourceModel.research_space_id
            == RelationClaimModel.research_space_id,
        )
        .exists()
    )
    stmt = (
        select(RelationClaimModel)
        .where(
            RelationClaimModel.polarity == "SUPPORT",
            or_(
                and_(
                    RelationClaimModel.claim_status == "RESOLVED",
                    RelationClaimModel.persistability == "PERSISTABLE",
                ),
                RelationClaimModel.linked_relation_id.is_not(None),
                projection_exists,
            ),
        )
        .order_by(RelationClaimModel.created_at.asc(), RelationClaimModel.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(stmt).all())


__all__ = [
    "ClaimParticipantBackfillSummary",
    "ClaimParticipantCoverageSummary",
    "ClaimParticipantBackfillGlobalSummary",
    "list_projection_relevant_claim_models",
]
