"""
SQLAlchemy implementation of KernelRelationRepository.

Handles graph-edge CRUD, curation lifecycle, and neighborhood traversal
against the canonical ``relations`` + ``relation_evidence`` tables.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select

from src.domain.entities.kernel.relations import KernelRelation
from src.domain.repositories.kernel.relation_repository import KernelRelationRepository
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel

from ._kernel_relation_auto_promotion_mixin import _KernelRelationAutoPromotionMixin
from ._kernel_relation_curation_mixin import _KernelRelationCurationMixin
from ._kernel_relation_query_mixin import _KernelRelationQueryMixin
from ._kernel_relation_repository_shared import (
    AutoPromotionPolicy,
    _as_uuid,
    _clamp_confidence,
    _normalize_evidence_tier,
    _try_as_uuid,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class SqlAlchemyKernelRelationRepository(
    _KernelRelationAutoPromotionMixin,
    _KernelRelationCurationMixin,
    _KernelRelationQueryMixin,
    KernelRelationRepository,
):
    """SQLAlchemy implementation of the kernel relation repository."""

    def __init__(
        self,
        session: Session,
        *,
        auto_promotion_policy: AutoPromotionPolicy | None = None,
    ) -> None:
        self._session = session
        self._auto_promotion_policy = (
            auto_promotion_policy or AutoPromotionPolicy.from_environment()
        )

    def create(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_id: str,
        relation_type: str,
        target_id: str,
        confidence: float = 0.5,
        evidence_summary: str | None = None,
        evidence_tier: str | None = None,
        curation_status: str = "DRAFT",
        provenance_id: str | None = None,
        source_document_id: str | None = None,
        agent_run_id: str | None = None,
    ) -> KernelRelation:
        canonical_stmt = select(RelationModel).where(
            RelationModel.research_space_id == _as_uuid(research_space_id),
            RelationModel.source_id == _as_uuid(source_id),
            RelationModel.relation_type == relation_type,
            RelationModel.target_id == _as_uuid(target_id),
        )
        relation = self._session.scalars(canonical_stmt).first()

        if relation is None:
            relation = RelationModel(
                id=uuid4(),
                research_space_id=_as_uuid(research_space_id),
                source_id=_as_uuid(source_id),
                relation_type=relation_type,
                target_id=_as_uuid(target_id),
                aggregate_confidence=0.0,
                source_count=0,
                highest_evidence_tier=None,
                curation_status=curation_status,
                provenance_id=(
                    _as_uuid(provenance_id) if provenance_id is not None else None
                ),
            )
            self._session.add(relation)
            self._session.flush()
        normalized_confidence = _clamp_confidence(confidence)
        normalized_tier = _normalize_evidence_tier(evidence_tier)
        provenance_uuid = _as_uuid(provenance_id) if provenance_id is not None else None
        source_document_uuid = _try_as_uuid(source_document_id)
        agent_run_uuid = _try_as_uuid(agent_run_id)

        if provenance_uuid is not None and relation.provenance_id is None:
            relation.provenance_id = provenance_uuid

        duplicate_stmt = select(RelationEvidenceModel.id).where(
            RelationEvidenceModel.relation_id == relation.id,
            RelationEvidenceModel.confidence == normalized_confidence,
            RelationEvidenceModel.evidence_tier == normalized_tier,
        )
        if evidence_summary is None:
            duplicate_stmt = duplicate_stmt.where(
                RelationEvidenceModel.evidence_summary.is_(None),
            )
        else:
            duplicate_stmt = duplicate_stmt.where(
                RelationEvidenceModel.evidence_summary == evidence_summary,
            )
        if provenance_uuid is None:
            duplicate_stmt = duplicate_stmt.where(
                RelationEvidenceModel.provenance_id.is_(None),
            )
        else:
            duplicate_stmt = duplicate_stmt.where(
                RelationEvidenceModel.provenance_id == provenance_uuid,
            )
        duplicate_evidence_id = self._session.scalar(duplicate_stmt.limit(1))

        if duplicate_evidence_id is None:
            evidence = RelationEvidenceModel(
                id=uuid4(),
                relation_id=relation.id,
                confidence=normalized_confidence,
                evidence_summary=evidence_summary,
                evidence_tier=normalized_tier,
                provenance_id=provenance_uuid,
                source_document_id=source_document_uuid,
                agent_run_id=agent_run_uuid,
            )
            self._session.add(evidence)
            self._session.flush()

        self._recompute_relation_aggregate(relation.id)
        auto_promotion_decision = self._apply_auto_promotion(relation.id)
        self._log_auto_promotion_decision(
            relation=relation,
            decision=auto_promotion_decision,
        )
        self._session.flush()
        return KernelRelation.model_validate(relation)


__all__ = ["SqlAlchemyKernelRelationRepository"]
