"""
SQLAlchemy implementation of KernelRelationRepository.

Handles graph-edge CRUD, curation lifecycle, and neighborhood traversal
against the canonical ``relations`` + ``relation_evidence`` tables.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy.engine import CursorResult

from src.domain.entities.kernel.relations import KernelRelation
from src.domain.repositories.kernel.relation_repository import KernelRelationRepository
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_DEFAULT_EVIDENCE_TIER = "COMPUTATIONAL"
_EVIDENCE_TIER_RANK: dict[str, int] = {
    "EXPERT_CURATED": 6,
    "CLINICAL": 5,
    "EXPERIMENTAL": 4,
    "LITERATURE": 3,
    "STRUCTURED_DATA": 2,
    "COMPUTATIONAL": 1,
}


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _clamp_confidence(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _normalize_evidence_tier(value: str | None) -> str:
    if value is None:
        return _DEFAULT_EVIDENCE_TIER
    normalized = value.strip().upper()
    if not normalized:
        return _DEFAULT_EVIDENCE_TIER
    return normalized


def _tier_rank(value: str | None) -> int:
    if value is None:
        return 0
    return _EVIDENCE_TIER_RANK.get(value.strip().upper(), 0)


class SqlAlchemyKernelRelationRepository(KernelRelationRepository):
    """SQLAlchemy implementation of the kernel relation repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Write ─────────────────────────────────────────────────────────

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
        elif provenance_id is not None and relation.provenance_id is None:
            relation.provenance_id = _as_uuid(provenance_id)

        evidence = RelationEvidenceModel(
            id=uuid4(),
            relation_id=relation.id,
            confidence=_clamp_confidence(confidence),
            evidence_summary=evidence_summary,
            evidence_tier=_normalize_evidence_tier(evidence_tier),
            provenance_id=(
                _as_uuid(provenance_id) if provenance_id is not None else None
            ),
            source_document_id=None,
            agent_run_id=None,
        )
        self._session.add(evidence)
        self._session.flush()

        self._recompute_relation_aggregate(relation.id)
        self._session.flush()
        return KernelRelation.model_validate(relation)

    # ── Read ──────────────────────────────────────────────────────────

    def get_by_id(self, relation_id: str) -> KernelRelation | None:
        model = self._session.get(RelationModel, _as_uuid(relation_id))
        return KernelRelation.model_validate(model) if model is not None else None

    def find_by_source(
        self,
        source_id: str,
        *,
        relation_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        stmt = select(RelationModel).where(
            RelationModel.source_id == _as_uuid(source_id),
        )
        if relation_type is not None:
            stmt = stmt.where(RelationModel.relation_type == relation_type)
        stmt = stmt.order_by(RelationModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelRelation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_by_target(
        self,
        target_id: str,
        *,
        relation_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        stmt = select(RelationModel).where(
            RelationModel.target_id == _as_uuid(target_id),
        )
        if relation_type is not None:
            stmt = stmt.where(RelationModel.relation_type == relation_type)
        stmt = stmt.order_by(RelationModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelRelation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_neighborhood(
        self,
        entity_id: str,
        *,
        depth: int = 1,
        relation_types: list[str] | None = None,
    ) -> list[KernelRelation]:
        """
        Multi-hop neighborhood traversal.

        For depth=1, returns all relations where the entity is source or target.
        For depth>1, iteratively expands the frontier.
        """
        visited_ids: set[UUID] = set()
        frontier: set[UUID] = {_as_uuid(entity_id)}
        all_relations: list[RelationModel] = []

        for _hop in range(depth):
            if not frontier:
                break

            stmt = select(RelationModel).where(
                or_(
                    RelationModel.source_id.in_(frontier),
                    RelationModel.target_id.in_(frontier),
                ),
            )
            if relation_types:
                stmt = stmt.where(RelationModel.relation_type.in_(relation_types))

            hop_relations = list(self._session.scalars(stmt).all())
            all_relations.extend(hop_relations)

            visited_ids |= frontier
            next_frontier: set[UUID] = set()
            for rel in hop_relations:
                src_id = _as_uuid(rel.source_id)
                tgt_id = _as_uuid(rel.target_id)
                if src_id not in visited_ids:
                    next_frontier.add(src_id)
                if tgt_id not in visited_ids:
                    next_frontier.add(tgt_id)
            frontier = next_frontier

        # Deduplicate (a relation may appear in multiple hops)
        seen: set[str] = set()
        unique: list[RelationModel] = []
        for rel in all_relations:
            rel_id = str(rel.id)
            if rel_id not in seen:
                seen.add(rel_id)
                unique.append(rel)
        return [KernelRelation.model_validate(model) for model in unique]

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        stmt = select(RelationModel).where(
            RelationModel.research_space_id == _as_uuid(research_space_id),
        )
        if relation_type is not None:
            stmt = stmt.where(RelationModel.relation_type == relation_type)
        if curation_status is not None:
            stmt = stmt.where(RelationModel.curation_status == curation_status)
        stmt = stmt.order_by(RelationModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelRelation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def search_by_text(
        self,
        research_space_id: str,
        query: str,
        *,
        limit: int = 20,
    ) -> list[KernelRelation]:
        stmt = (
            select(RelationModel)
            .outerjoin(
                RelationEvidenceModel,
                RelationEvidenceModel.relation_id == RelationModel.id,
            )
            .where(
                RelationModel.research_space_id == _as_uuid(research_space_id),
                or_(
                    RelationModel.relation_type.ilike(f"%{query}%"),
                    RelationModel.curation_status.ilike(f"%{query}%"),
                    RelationEvidenceModel.evidence_summary.ilike(f"%{query}%"),
                ),
            )
            .order_by(RelationModel.updated_at.desc())
            .limit(limit)
        )
        models = list(self._session.scalars(stmt).all())
        seen: set[UUID] = set()
        unique_models: list[RelationModel] = []
        for model in models:
            if model.id in seen:
                continue
            seen.add(model.id)
            unique_models.append(model)
        return [KernelRelation.model_validate(model) for model in unique_models]

    # ── Curation lifecycle ────────────────────────────────────────────

    def update_curation(
        self,
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

    # ── Delete ────────────────────────────────────────────────────────

    def delete(self, relation_id: str) -> bool:
        relation_model = self._session.get(RelationModel, _as_uuid(relation_id))
        if relation_model is None:
            return False
        self._session.delete(relation_model)
        self._session.flush()
        return True

    def delete_by_provenance(self, provenance_id: str) -> int:
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

    # ── Aggregate helpers ─────────────────────────────────────────────

    def _recompute_relation_aggregate(self, relation_id: UUID) -> None:
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

    def count_by_research_space(self, research_space_id: str) -> int:
        """Count total relations in a research space."""
        result = self._session.execute(
            select(func.count()).where(
                RelationModel.research_space_id == _as_uuid(research_space_id),
            ),
        )
        return result.scalar_one()


__all__ = ["SqlAlchemyKernelRelationRepository"]
