"""SQLAlchemy implementation of GraphQueryPort for graph-layer agents."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from src.domain.entities.kernel.entities import KernelEntity
from src.domain.entities.kernel.observations import KernelObservation
from src.domain.entities.kernel.relations import KernelRelation, KernelRelationEvidence
from src.domain.ports.graph_query_port import GraphQueryPort
from src.infrastructure.repositories.kernel.kernel_relation_repository import (
    SqlAlchemyKernelRelationRepository,
)
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.observations import ObservationModel
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class SqlAlchemyGraphQueryRepository(GraphQueryPort):
    """Graph-query repository used by graph-layer reasoning agents."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._relations = SqlAlchemyKernelRelationRepository(session)

    def graph_query_neighbourhood(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        depth: int = 1,
        relation_types: list[str] | None = None,
        limit: int = 200,
    ) -> list[KernelRelation]:
        relations = self._relations.find_neighborhood(
            entity_id=entity_id,
            depth=max(depth, 1),
            relation_types=relation_types,
        )
        scoped = [
            relation
            for relation in relations
            if str(relation.research_space_id) == str(research_space_id)
        ]
        return scoped[: max(limit, 1)]

    def graph_query_shared_subjects(
        self,
        *,
        research_space_id: str,
        entity_id_a: str,
        entity_id_b: str,
        limit: int = 100,
    ) -> list[KernelEntity]:
        research_space_uuid = _as_uuid(research_space_id)
        entity_a_uuid = _as_uuid(entity_id_a)
        entity_b_uuid = _as_uuid(entity_id_b)

        variable_ids_a = select(ObservationModel.variable_id).where(
            ObservationModel.research_space_id == research_space_uuid,
            ObservationModel.subject_id == entity_a_uuid,
        )
        variable_ids_b = select(ObservationModel.variable_id).where(
            ObservationModel.research_space_id == research_space_uuid,
            ObservationModel.subject_id == entity_b_uuid,
        )

        subjects_with_a_profile = select(ObservationModel.subject_id).where(
            ObservationModel.research_space_id == research_space_uuid,
            ObservationModel.variable_id.in_(variable_ids_a),
        )
        subjects_with_b_profile = select(ObservationModel.subject_id).where(
            ObservationModel.research_space_id == research_space_uuid,
            ObservationModel.variable_id.in_(variable_ids_b),
        )

        stmt = (
            select(EntityModel)
            .where(
                EntityModel.research_space_id == research_space_uuid,
                EntityModel.id.in_(subjects_with_a_profile),
                EntityModel.id.in_(subjects_with_b_profile),
                EntityModel.id.notin_([entity_a_uuid, entity_b_uuid]),
            )
            .order_by(EntityModel.created_at.desc())
            .limit(max(limit, 1))
        )
        return [
            KernelEntity.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def graph_query_observations(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        variable_ids: list[str] | None = None,
        limit: int = 200,
    ) -> list[KernelObservation]:
        stmt = select(ObservationModel).where(
            ObservationModel.research_space_id == _as_uuid(research_space_id),
            ObservationModel.subject_id == _as_uuid(entity_id),
        )
        if variable_ids:
            stmt = stmt.where(ObservationModel.variable_id.in_(variable_ids))
        stmt = stmt.order_by(ObservationModel.created_at.desc()).limit(max(limit, 1))
        return [
            KernelObservation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def graph_query_relation_evidence(
        self,
        *,
        research_space_id: str,
        relation_id: str,
        limit: int = 200,
    ) -> list[KernelRelationEvidence]:
        stmt = (
            select(RelationEvidenceModel)
            .join(
                RelationModel,
                RelationModel.id == RelationEvidenceModel.relation_id,
            )
            .where(
                RelationModel.id == _as_uuid(relation_id),
                RelationModel.research_space_id == _as_uuid(research_space_id),
            )
            .order_by(RelationEvidenceModel.created_at.desc())
            .limit(max(limit, 1))
        )
        return [
            KernelRelationEvidence.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]


__all__ = ["SqlAlchemyGraphQueryRepository"]
