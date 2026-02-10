"""
SQLAlchemy implementation of KernelRelationRepository.

Handles graph-edge CRUD, curation lifecycle, and neighborhood traversal
against the ``relations`` table.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import delete as sa_delete
from sqlalchemy import or_, select

from src.domain.repositories.kernel.relation_repository import KernelRelationRepository
from src.models.database.kernel.relations import RelationModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SqlAlchemyKernelRelationRepository(KernelRelationRepository):
    """SQLAlchemy implementation of the kernel relation repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Write ─────────────────────────────────────────────────────────

    def create(  # noqa: PLR0913
        self,
        *,
        study_id: str,
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
            id=str(uuid4()),
            study_id=study_id,
            source_id=source_id,
            relation_type=relation_type,
            target_id=target_id,
            confidence=confidence,
            evidence_summary=evidence_summary,
            evidence_tier=evidence_tier,
            curation_status=curation_status,
            provenance_id=provenance_id,
        )
        self._session.add(relation)
        self._session.flush()
        return relation

    # ── Read ──────────────────────────────────────────────────────────

    def get_by_id(self, relation_id: str) -> RelationModel | None:
        return self._session.get(RelationModel, relation_id)

    def find_by_source(
        self,
        source_id: str,
        *,
        relation_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[RelationModel]:
        stmt = select(RelationModel).where(RelationModel.source_id == source_id)
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
        stmt = select(RelationModel).where(RelationModel.target_id == target_id)
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
        visited_ids: set[str] = set()
        frontier: set[str] = {entity_id}
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
            next_frontier: set[str] = set()
            for rel in hop_relations:
                if rel.source_id not in visited_ids:
                    next_frontier.add(rel.source_id)
                if rel.target_id not in visited_ids:
                    next_frontier.add(rel.target_id)
            frontier = next_frontier

        # Deduplicate (a relation may appear in multiple hops)
        seen: set[str] = set()
        unique: list[RelationModel] = []
        for rel in all_relations:
            if rel.id not in seen:
                seen.add(rel.id)
                unique.append(rel)
        return unique

    def find_by_study(
        self,
        study_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[RelationModel]:
        stmt = select(RelationModel).where(RelationModel.study_id == study_id)
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

    # ── Curation lifecycle ────────────────────────────────────────────

    def update_curation(
        self,
        relation_id: str,
        *,
        curation_status: str,
        reviewed_by: str,
        reviewed_at: datetime | None = None,
    ) -> RelationModel:
        relation = self._session.get(RelationModel, relation_id)
        if relation is None:
            msg = f"Relation {relation_id} not found"
            raise ValueError(msg)
        relation.curation_status = curation_status
        relation.reviewed_by = reviewed_by
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
                RelationModel.provenance_id == provenance_id,
            ),
        )
        count: int = result.rowcount  # type: ignore[attr-defined]
        self._session.flush()
        logger.info(
            "Rolled back %d relations for provenance %s",
            count,
            provenance_id,
        )
        return count


__all__ = ["SqlAlchemyKernelRelationRepository"]
