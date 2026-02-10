"""
SQLAlchemy implementation of KernelRelationRepository.

Handles graph-edge CRUD, curation lifecycle, and neighborhood traversal
against the ``relations`` table.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy.engine import CursorResult

from src.domain.repositories.kernel.relation_repository import KernelRelationRepository
from src.models.database.kernel.relations import RelationModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


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
    ) -> RelationModel:
        relation = RelationModel(
            id=uuid4(),
            research_space_id=_as_uuid(research_space_id),
            source_id=_as_uuid(source_id),
            relation_type=relation_type,
            target_id=_as_uuid(target_id),
            confidence=confidence,
            evidence_summary=evidence_summary,
            evidence_tier=evidence_tier,
            curation_status=curation_status,
            provenance_id=(
                _as_uuid(provenance_id) if provenance_id is not None else None
            ),
        )
        self._session.add(relation)
        self._session.flush()
        return relation

    # ── Read ──────────────────────────────────────────────────────────

    def get_by_id(self, relation_id: str) -> RelationModel | None:
        return self._session.get(RelationModel, _as_uuid(relation_id))

    def find_by_source(
        self,
        source_id: str,
        *,
        relation_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[RelationModel]:
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
        return list(self._session.scalars(stmt).all())

    def find_by_target(
        self,
        target_id: str,
        *,
        relation_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[RelationModel]:
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
        return list(self._session.scalars(stmt).all())

    def find_neighborhood(
        self,
        entity_id: str,
        *,
        depth: int = 1,
        relation_types: list[str] | None = None,
    ) -> list[RelationModel]:
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
        return unique

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[RelationModel]:
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
        return list(self._session.scalars(stmt).all())

    def search_by_text(
        self,
        research_space_id: str,
        query: str,
        *,
        limit: int = 20,
    ) -> list[RelationModel]:
        stmt = select(RelationModel).where(
            RelationModel.research_space_id == _as_uuid(research_space_id),
            or_(
                RelationModel.relation_type.ilike(f"%{query}%"),
                RelationModel.evidence_summary.ilike(f"%{query}%"),
                RelationModel.curation_status.ilike(f"%{query}%"),
            ),
        )
        stmt = stmt.order_by(RelationModel.created_at.desc()).limit(limit)
        return list(self._session.scalars(stmt).all())

    # ── Curation lifecycle ────────────────────────────────────────────

    def update_curation(
        self,
        relation_id: str,
        *,
        curation_status: str,
        reviewed_by: str,
        reviewed_at: datetime | None = None,
    ) -> RelationModel:
        relation = self._session.get(RelationModel, _as_uuid(relation_id))
        if relation is None:
            msg = f"Relation {relation_id} not found"
            raise ValueError(msg)
        relation.curation_status = curation_status
        relation.reviewed_by = _as_uuid(reviewed_by)
        relation.reviewed_at = reviewed_at or datetime.now(UTC)
        self._session.flush()
        return relation

    # ── Delete ────────────────────────────────────────────────────────

    def delete(self, relation_id: str) -> bool:
        relation = self.get_by_id(relation_id)
        if relation is None:
            return False
        self._session.delete(relation)
        self._session.flush()
        return True

    def delete_by_provenance(self, provenance_id: str) -> int:
        result = self._session.execute(
            sa_delete(RelationModel).where(
                RelationModel.provenance_id == _as_uuid(provenance_id),
            ),
        )
        count = int(result.rowcount or 0) if isinstance(result, CursorResult) else 0
        self._session.flush()
        logger.info(
            "Rolled back %d relations for provenance %s",
            count,
            provenance_id,
        )
        return count

    # ── Aggregate helpers ─────────────────────────────────────────────

    def count_by_research_space(self, research_space_id: str) -> int:
        """Count total relations in a research space."""
        result = self._session.execute(
            select(func.count()).where(
                RelationModel.research_space_id == _as_uuid(research_space_id),
            ),
        )
        return result.scalar_one()


__all__ = ["SqlAlchemyKernelRelationRepository"]
