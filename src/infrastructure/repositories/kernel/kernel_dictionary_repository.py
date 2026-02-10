"""
SQLAlchemy implementation of DictionaryRepository.

Read-heavy repository for the Layer 1 dictionary tables:
variable_definitions, variable_synonyms, transform_registry,
entity_resolution_policies, and relation_constraints.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import and_, select

from src.domain.repositories.kernel.dictionary_repository import DictionaryRepository
from src.models.database.kernel.dictionary import (
    EntityResolutionPolicyModel,
    RelationConstraintModel,
    TransformRegistryModel,
    VariableDefinitionModel,
    VariableSynonymModel,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


class SqlAlchemyDictionaryRepository(DictionaryRepository):
    """SQLAlchemy implementation of the dictionary repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Variable definitions ──────────────────────────────────────────

    def get_variable(self, variable_id: str) -> VariableDefinitionModel | None:
        return self._session.get(VariableDefinitionModel, variable_id)

    def find_variables(
        self,
        *,
        domain_context: str | None = None,
        data_type: str | None = None,
    ) -> list[VariableDefinitionModel]:
        stmt = select(VariableDefinitionModel)
        if domain_context is not None:
            stmt = stmt.where(
                VariableDefinitionModel.domain_context == domain_context,
            )
        if data_type is not None:
            stmt = stmt.where(VariableDefinitionModel.data_type == data_type)
        stmt = stmt.order_by(VariableDefinitionModel.canonical_name)
        return list(self._session.scalars(stmt).all())

    def find_variable_by_synonym(
        self,
        synonym: str,
    ) -> VariableDefinitionModel | None:
        stmt = (
            select(VariableDefinitionModel)
            .join(VariableSynonymModel)
            .where(VariableSynonymModel.synonym == synonym.lower())
        )
        return self._session.scalars(stmt).first()

    def create_variable(  # noqa: PLR0913
        self,
        *,
        variable_id: str,
        canonical_name: str,
        display_name: str,
        data_type: str,
        domain_context: str = "general",
        sensitivity: str = "INTERNAL",
        preferred_unit: str | None = None,
        constraints: JSONObject | None = None,
        description: str | None = None,
    ) -> VariableDefinitionModel:
        var = VariableDefinitionModel(
            id=variable_id,
            canonical_name=canonical_name,
            display_name=display_name,
            data_type=data_type,
            domain_context=domain_context,
            sensitivity=sensitivity,
            preferred_unit=preferred_unit,
            constraints=constraints or {},
            description=description,
        )
        self._session.add(var)
        self._session.flush()
        return var

    # ── Entity resolution policies ────────────────────────────────────

    def get_resolution_policy(
        self,
        entity_type: str,
    ) -> EntityResolutionPolicyModel | None:
        return self._session.get(EntityResolutionPolicyModel, entity_type)

    def find_resolution_policies(self) -> list[EntityResolutionPolicyModel]:
        return list(
            self._session.scalars(
                select(EntityResolutionPolicyModel).order_by(
                    EntityResolutionPolicyModel.entity_type,
                ),
            ).all(),
        )

    # ── Relation constraints ──────────────────────────────────────────

    def get_constraints(
        self,
        *,
        source_type: str | None = None,
        relation_type: str | None = None,
    ) -> list[RelationConstraintModel]:
        stmt = select(RelationConstraintModel)
        if source_type is not None:
            stmt = stmt.where(RelationConstraintModel.source_type == source_type)
        if relation_type is not None:
            stmt = stmt.where(RelationConstraintModel.relation_type == relation_type)
        return list(self._session.scalars(stmt).all())

    def is_triple_allowed(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        stmt = select(RelationConstraintModel).where(
            and_(
                RelationConstraintModel.source_type == source_type,
                RelationConstraintModel.relation_type == relation_type,
                RelationConstraintModel.target_type == target_type,
                RelationConstraintModel.is_allowed.is_(True),
            ),
        )
        return self._session.scalars(stmt).first() is not None

    def requires_evidence(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        stmt = select(RelationConstraintModel).where(
            and_(
                RelationConstraintModel.source_type == source_type,
                RelationConstraintModel.relation_type == relation_type,
                RelationConstraintModel.target_type == target_type,
            ),
        )
        constraint = self._session.scalars(stmt).first()
        if constraint is None:
            # If no constraint exists, default to requiring evidence
            return True
        return constraint.requires_evidence

    # ── Transform registry ────────────────────────────────────────────

    def get_transform(
        self,
        input_unit: str,
        output_unit: str,
    ) -> TransformRegistryModel | None:
        stmt = select(TransformRegistryModel).where(
            and_(
                TransformRegistryModel.input_unit == input_unit,
                TransformRegistryModel.output_unit == output_unit,
                TransformRegistryModel.status == "ACTIVE",
            ),
        )
        return self._session.scalars(stmt).first()

    def find_transforms(
        self,
        *,
        status: str = "ACTIVE",
    ) -> list[TransformRegistryModel]:
        stmt = select(TransformRegistryModel).where(
            TransformRegistryModel.status == status,
        )
        return list(self._session.scalars(stmt).all())


__all__ = ["SqlAlchemyDictionaryRepository"]
