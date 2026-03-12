"""Read/query mixin for kernel relation repositories."""

# mypy: disable-error-code="misc"

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, and_, func, or_, select
from sqlalchemy.orm import aliased

from src.domain.entities.kernel.relations import KernelRelation
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.relation_claims import RelationClaimModel
from src.models.database.kernel.relation_projection_sources import (
    RelationProjectionSourceModel,
)
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel

from ._kernel_relation_repository_shared import _as_uuid

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.sql import Select
    from sqlalchemy.sql.elements import ColumnElement

    from src.infrastructure.repositories.kernel.kernel_relation_repository import (
        SqlAlchemyKernelRelationRepository,
    )


class _KernelRelationQueryMixin:
    """Read and graph-traversal query helpers."""

    _HIGH_CONFIDENCE_THRESHOLD = 0.8
    _MEDIUM_CONFIDENCE_THRESHOLD = 0.6

    def get_by_id(
        self: SqlAlchemyKernelRelationRepository,
        relation_id: str,
        *,
        claim_backed_only: bool = True,
    ) -> KernelRelation | None:
        stmt = select(RelationModel).where(RelationModel.id == _as_uuid(relation_id))
        if claim_backed_only:
            stmt = stmt.where(self._active_support_projection_exists())
        model = self._session.scalars(stmt.limit(1)).first()
        return KernelRelation.model_validate(model) if model is not None else None

    def find_by_triple(
        self: SqlAlchemyKernelRelationRepository,
        *,
        research_space_id: str,
        source_id: str,
        relation_type: str,
        target_id: str,
        claim_backed_only: bool = True,
    ) -> KernelRelation | None:
        stmt = select(RelationModel).where(
            RelationModel.research_space_id == _as_uuid(research_space_id),
            RelationModel.source_id == _as_uuid(source_id),
            RelationModel.relation_type == relation_type,
            RelationModel.target_id == _as_uuid(target_id),
        )
        if claim_backed_only:
            stmt = stmt.where(self._active_support_projection_exists())
        model = self._session.scalars(stmt.limit(1)).first()
        return KernelRelation.model_validate(model) if model is not None else None

    def find_by_source(
        self: SqlAlchemyKernelRelationRepository,
        source_id: str,
        *,
        relation_type: str | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        stmt = select(RelationModel).where(
            RelationModel.source_id == _as_uuid(source_id),
        )
        if relation_type is not None:
            stmt = stmt.where(RelationModel.relation_type == relation_type)
        if claim_backed_only:
            stmt = stmt.where(self._active_support_projection_exists())
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
        claim_backed_only: bool = True,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        stmt = select(RelationModel).where(
            RelationModel.target_id == _as_uuid(target_id),
        )
        if relation_type is not None:
            stmt = stmt.where(RelationModel.relation_type == relation_type)
        if claim_backed_only:
            stmt = stmt.where(self._active_support_projection_exists())
        stmt = stmt.order_by(RelationModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelRelation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_neighborhood(  # noqa: C901
        self: SqlAlchemyKernelRelationRepository,
        entity_id: str,
        *,
        depth: int = 1,
        relation_types: list[str] | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
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
            if claim_backed_only:
                stmt = stmt.where(self._active_support_projection_exists())

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
        unique.sort(key=lambda rel: rel.updated_at, reverse=True)
        if limit is not None:
            unique = unique[: max(limit, 1)]
        return [KernelRelation.model_validate(model) for model in unique]

    def find_by_research_space(  # noqa: C901, PLR0913 - query builder needs discrete optional filters
        self: SqlAlchemyKernelRelationRepository,
        research_space_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        validation_state: str | None = None,
        source_document_id: str | None = None,
        certainty_band: str | None = None,
        node_query: str | None = None,
        node_ids: list[str] | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        stmt = self._build_research_space_stmt(
            research_space_id=research_space_id,
            relation_type=relation_type,
            curation_status=curation_status,
            validation_state=validation_state,
            source_document_id=source_document_id,
            certainty_band=certainty_band,
            node_query=node_query,
            node_ids=node_ids,
            claim_backed_only=claim_backed_only,
        )
        if stmt is None:
            return []
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
        claim_backed_only: bool = True,
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
        if claim_backed_only:
            stmt = stmt.where(self._active_support_projection_exists())
        models = list(self._session.scalars(stmt).all())
        seen: set[UUID] = set()
        unique_models: list[RelationModel] = []
        for model in models:
            if model.id in seen:
                continue
            seen.add(model.id)
            unique_models.append(model)
        return [KernelRelation.model_validate(model) for model in unique_models]

    def count_by_research_space(  # noqa: PLR0913
        self: SqlAlchemyKernelRelationRepository,
        research_space_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        validation_state: str | None = None,
        source_document_id: str | None = None,
        certainty_band: str | None = None,
        node_query: str | None = None,
        node_ids: list[str] | None = None,
        claim_backed_only: bool = True,
    ) -> int:
        """Count total relations in a research space."""
        stmt = self._build_research_space_stmt(
            research_space_id=research_space_id,
            relation_type=relation_type,
            curation_status=curation_status,
            validation_state=validation_state,
            source_document_id=source_document_id,
            certainty_band=certainty_band,
            node_query=node_query,
            node_ids=node_ids,
            claim_backed_only=claim_backed_only,
        )
        if stmt is None:
            return 0
        result = self._session.execute(
            stmt.with_only_columns(
                func.count(func.distinct(RelationModel.id)),
                maintain_column_froms=True,
            ),
        )
        return int(result.scalar_one())

    def _build_research_space_stmt(  # noqa: C901, PLR0912, PLR0913
        self: SqlAlchemyKernelRelationRepository,
        *,
        research_space_id: str,
        relation_type: str | None,
        curation_status: str | None,
        validation_state: str | None,
        source_document_id: str | None,
        certainty_band: str | None,
        node_query: str | None,
        node_ids: list[str] | None,
        claim_backed_only: bool,
    ) -> Select[tuple[RelationModel]] | None:
        stmt = select(RelationModel).where(
            RelationModel.research_space_id == _as_uuid(research_space_id),
        )
        if claim_backed_only:
            stmt = stmt.where(self._active_support_projection_exists())
        if relation_type is not None:
            stmt = stmt.where(RelationModel.relation_type == relation_type)
        if curation_status is not None:
            stmt = stmt.where(RelationModel.curation_status == curation_status)
        if validation_state is not None:
            claim_relation_ids = select(RelationClaimModel.linked_relation_id).where(
                RelationClaimModel.research_space_id == _as_uuid(research_space_id),
                RelationClaimModel.linked_relation_id.is_not(None),
                RelationClaimModel.validation_state == validation_state,
            )
            stmt = stmt.where(RelationModel.id.in_(claim_relation_ids))
        if source_document_id is not None:
            source_document_uuid = _try_as_uuid(source_document_id)
            if source_document_uuid is None:
                return None
            evidence_relation_ids = select(RelationEvidenceModel.relation_id).where(
                RelationEvidenceModel.source_document_id == source_document_uuid,
            )
            claim_relation_ids = select(RelationClaimModel.linked_relation_id).where(
                RelationClaimModel.research_space_id == _as_uuid(research_space_id),
                RelationClaimModel.linked_relation_id.is_not(None),
                RelationClaimModel.source_document_id == source_document_uuid,
            )
            stmt = stmt.where(
                or_(
                    RelationModel.id.in_(evidence_relation_ids),
                    RelationModel.id.in_(claim_relation_ids),
                ),
            )
        if certainty_band is not None:
            normalized_band = certainty_band.strip().upper()
            if normalized_band == "HIGH":
                stmt = stmt.where(
                    RelationModel.aggregate_confidence
                    >= self._HIGH_CONFIDENCE_THRESHOLD,
                )
            elif normalized_band == "MEDIUM":
                stmt = stmt.where(
                    RelationModel.aggregate_confidence
                    >= self._MEDIUM_CONFIDENCE_THRESHOLD,
                    RelationModel.aggregate_confidence
                    < self._HIGH_CONFIDENCE_THRESHOLD,
                )
            elif normalized_band == "LOW":
                stmt = stmt.where(
                    RelationModel.aggregate_confidence
                    < self._MEDIUM_CONFIDENCE_THRESHOLD,
                )
        if node_ids:
            node_uuid_ids: list[UUID] = []
            for node_id in node_ids:
                trimmed = node_id.strip()
                if not trimmed:
                    continue
                try:
                    node_uuid_ids.append(_as_uuid(trimmed))
                except ValueError:
                    continue
            if not node_uuid_ids:
                return None
            stmt = stmt.where(
                or_(
                    RelationModel.source_id.in_(node_uuid_ids),
                    RelationModel.target_id.in_(node_uuid_ids),
                ),
            )
        if node_query is not None and node_query.strip():
            source_entity = aliased(EntityModel)
            target_entity = aliased(EntityModel)
            search_term = f"%{node_query.strip()}%"
            stmt = stmt.join(
                source_entity,
                source_entity.id == RelationModel.source_id,
            ).join(
                target_entity,
                target_entity.id == RelationModel.target_id,
            )
            stmt = stmt.where(
                or_(
                    RelationModel.source_id.cast(String).ilike(search_term),
                    RelationModel.target_id.cast(String).ilike(search_term),
                    source_entity.display_label.ilike(search_term),
                    target_entity.display_label.ilike(search_term),
                    source_entity.entity_type.ilike(search_term),
                    target_entity.entity_type.ilike(search_term),
                ),
            )
        return stmt

    @staticmethod
    def _active_support_projection_exists() -> ColumnElement[bool]:
        projection_to_claim = and_(
            RelationClaimModel.id == RelationProjectionSourceModel.claim_id,
            RelationClaimModel.research_space_id
            == RelationProjectionSourceModel.research_space_id,
        )
        return (
            select(RelationProjectionSourceModel.id)
            .join(RelationClaimModel, projection_to_claim)
            .where(
                RelationProjectionSourceModel.relation_id == RelationModel.id,
                RelationProjectionSourceModel.research_space_id
                == RelationModel.research_space_id,
                RelationClaimModel.polarity == "SUPPORT",
                RelationClaimModel.claim_status == "RESOLVED",
                RelationClaimModel.persistability == "PERSISTABLE",
            )
            .exists()
        )


def _try_as_uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return _as_uuid(normalized)
    except ValueError:
        return None
