"""Curation and delete mixin for kernel relation repositories."""

# mypy: disable-error-code="misc"

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.engine import CursorResult

from src.domain.entities.kernel.relations import KernelRelation
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel

from ._kernel_relation_repository_shared import (
    _as_uuid,
    _clamp_confidence,
    _normalize_evidence_tier,
    _tier_rank,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.infrastructure.repositories.kernel.kernel_relation_repository import (
        SqlAlchemyKernelRelationRepository,
    )

logger = logging.getLogger(__name__)


class _KernelRelationCurationMixin:
    """Curation lifecycle, delete, and aggregate helper methods."""

    def update_curation(
        self: SqlAlchemyKernelRelationRepository,
        relation_id: str,
        *,
        curation_status: str,
        reviewed_by: str,
        reviewed_at: datetime | None = None,
    ) -> KernelRelation:
        relation_model = self._session.get(RelationModel, _as_uuid(relation_id))
        if relation_model is None:
            msg = f"Relation {relation_id} not found"
            raise ValueError(msg)
        relation_model.curation_status = curation_status
        relation_model.reviewed_by = _as_uuid(reviewed_by)
        relation_model.reviewed_at = reviewed_at or datetime.now(UTC)
        self._session.flush()
        return KernelRelation.model_validate(relation_model)

    def delete(
        self: SqlAlchemyKernelRelationRepository,
        relation_id: str,
    ) -> bool:
        relation_model = self._session.get(RelationModel, _as_uuid(relation_id))
        if relation_model is None:
            return False
        self._session.delete(relation_model)
        self._session.flush()
        return True

    def delete_by_provenance(
        self: SqlAlchemyKernelRelationRepository,
        provenance_id: str,
    ) -> int:
        target_provenance_id = _as_uuid(provenance_id)
        relation_ids = list(
            set(
                self._session.scalars(
                    select(RelationEvidenceModel.relation_id).where(
                        RelationEvidenceModel.provenance_id == target_provenance_id,
                    ),
                ).all(),
            ),
        )
        if not relation_ids:
            return 0

        self._session.execute(
            sa_delete(RelationEvidenceModel).where(
                RelationEvidenceModel.provenance_id == target_provenance_id,
            ),
        )

        for relation_id in relation_ids:
            relation_model = self._session.get(RelationModel, relation_id)
            if relation_model is None:
                continue
            self._recompute_relation_aggregate(relation_id)

        delete_result = self._session.execute(
            sa_delete(RelationModel).where(
                RelationModel.id.in_(relation_ids),
                ~RelationModel.evidences.any(),
            ),
        )
        count = (
            int(delete_result.rowcount or 0)
            if isinstance(delete_result, CursorResult)
            else 0
        )
        self._session.flush()
        logger.info(
            "Rolled back %d relations for provenance %s",
            count,
            provenance_id,
        )
        return count

    def _recompute_relation_aggregate(
        self: SqlAlchemyKernelRelationRepository,
        relation_id: UUID,
    ) -> None:
        relation_model = self._session.get(RelationModel, relation_id)
        if relation_model is None:
            return

        evidences = list(
            self._session.scalars(
                select(RelationEvidenceModel).where(
                    RelationEvidenceModel.relation_id == relation_id,
                ),
            ).all(),
        )
        if not evidences:
            relation_model.aggregate_confidence = 0.0
            relation_model.source_count = 0
            relation_model.highest_evidence_tier = None
            relation_model.updated_at = datetime.now(UTC)
            return

        product = 1.0
        highest_tier: str | None = None
        highest_rank = -1

        for evidence in evidences:
            confidence = _clamp_confidence(float(evidence.confidence))
            product *= 1.0 - confidence

            tier = _normalize_evidence_tier(evidence.evidence_tier)
            rank = _tier_rank(tier)
            if rank > highest_rank:
                highest_rank = rank
                highest_tier = tier

        relation_model.aggregate_confidence = _clamp_confidence(1.0 - product)
        relation_model.source_count = len(evidences)
        relation_model.highest_evidence_tier = highest_tier
        relation_model.updated_at = datetime.now(UTC)
