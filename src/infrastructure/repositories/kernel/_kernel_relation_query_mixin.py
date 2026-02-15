"""Read/query mixin for kernel relation repositories."""

# mypy: disable-error-code="misc"

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select

from src.domain.entities.kernel.relations import KernelRelation
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel

from ._kernel_relation_repository_shared import _as_uuid

if TYPE_CHECKING:
    from uuid import UUID

    from src.infrastructure.repositories.kernel.kernel_relation_repository import (
        SqlAlchemyKernelRelationRepository,
    )


class _KernelRelationQueryMixin:
    """Read and graph-traversal query helpers."""

    def get_by_id(
        self: SqlAlchemyKernelRelationRepository,
        relation_id: str,
    ) -> KernelRelation | None:
        model = self._session.get(RelationModel, _as_uuid(relation_id))
        return KernelRelation.model_validate(model) if model is not None else None

    def find_by_source(
        self: SqlAlchemyKernelRelationRepository,
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
        self: SqlAlchemyKernelRelationRepository,
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
        self: SqlAlchemyKernelRelationRepository,
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

        seen: set[str] = set()
        unique: list[RelationModel] = []
        for rel in all_relations:
            rel_id = str(rel.id)
            if rel_id not in seen:
                seen.add(rel_id)
                unique.append(rel)
        return [KernelRelation.model_validate(model) for model in unique]

    def find_by_research_space(
        self: SqlAlchemyKernelRelationRepository,
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
        self: SqlAlchemyKernelRelationRepository,
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

    def count_by_research_space(
        self: SqlAlchemyKernelRelationRepository,
        research_space_id: str,
    ) -> int:
        """Count total relations in a research space."""
        result = self._session.execute(
            select(func.count()).where(
                RelationModel.research_space_id == _as_uuid(research_space_id),
            ),
        )
        return result.scalar_one()
