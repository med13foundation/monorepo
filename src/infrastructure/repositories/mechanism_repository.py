"""SQLAlchemy-backed implementation of the domain mechanism repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Select, asc, desc, func, or_, select

from src.domain.repositories.mechanism_repository import (
    MechanismRepository as MechanismRepositoryInterface,
)
from src.domain.value_objects.protein_structure import ProteinDomain
from src.infrastructure.mappers.mechanism_mapper import MechanismMapper
from src.models.database.mechanism import MechanismModel
from src.models.database.phenotype import PhenotypeModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.domain.entities.mechanism import Mechanism
    from src.domain.repositories.base import QuerySpecification
    from src.type_definitions.common import JSONObject, MechanismUpdate, QueryFilters


class SqlAlchemyMechanismRepository(MechanismRepositoryInterface):
    """Domain-facing repository adapter for mechanisms backed by SQLAlchemy."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            message = "Session is not configured"
            raise ValueError(message)
        return self._session

    def _to_domain(self, model: MechanismModel | None) -> Mechanism | None:
        return MechanismMapper.to_domain(model) if model else None

    def _to_domain_sequence(self, models: list[MechanismModel]) -> list[Mechanism]:
        return MechanismMapper.to_domain_sequence(models)

    def create(self, mechanism: Mechanism) -> Mechanism:
        model = MechanismMapper.to_model(mechanism)
        if mechanism.phenotype_ids:
            model.phenotypes = self._resolve_phenotypes(mechanism.phenotype_ids)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return MechanismMapper.to_domain(model)

    def get_by_id(self, mechanism_id: int) -> Mechanism | None:
        return self._to_domain(self.session.get(MechanismModel, mechanism_id))

    def find_by_name(self, name: str, *, research_space_id: UUID) -> Mechanism | None:
        stmt = select(MechanismModel).where(
            MechanismModel.name == name,
            MechanismModel.research_space_id == str(research_space_id),
        )
        return self._to_domain(self.session.execute(stmt).scalar_one_or_none())

    def find_all(
        self,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[Mechanism]:
        stmt = select(MechanismModel)
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        return self._to_domain_sequence(list(self.session.execute(stmt).scalars()))

    def exists(self, mechanism_id: int) -> bool:
        stmt = select(func.count()).where(MechanismModel.id == mechanism_id)
        return bool(self.session.execute(stmt).scalar_one())

    def count(self) -> int:
        stmt = select(func.count()).select_from(MechanismModel)
        return int(self.session.execute(stmt).scalar_one())

    def delete(self, mechanism_id: int) -> bool:
        model = self.session.get(MechanismModel, mechanism_id)
        if model is None:
            return False
        self.session.delete(model)
        self.session.commit()
        return True

    def find_by_criteria(self, spec: QuerySpecification) -> list[Mechanism]:
        stmt = select(MechanismModel)
        for field, value in spec.filters.items():
            column = getattr(MechanismModel, field, None)
            if column is not None and value is not None:
                stmt = stmt.where(column == value)
        if spec.offset:
            stmt = stmt.offset(spec.offset)
        if spec.limit:
            stmt = stmt.limit(spec.limit)
        return self._to_domain_sequence(list(self.session.execute(stmt).scalars()))

    def search_mechanisms(
        self,
        query: str,
        limit: int = 10,
        filters: QueryFilters | None = None,
    ) -> list[Mechanism]:
        pattern = f"%{query}%"
        stmt = (
            select(MechanismModel)
            .where(
                or_(
                    MechanismModel.name.ilike(pattern),
                    MechanismModel.description.ilike(pattern),
                ),
            )
            .limit(limit)
        )
        stmt = self._apply_filters(stmt, filters)
        return self._to_domain_sequence(list(self.session.execute(stmt).scalars()))

    def paginate_mechanisms(
        self,
        page: int,
        per_page: int,
        sort_by: str,
        sort_order: str,
        filters: QueryFilters | None = None,
    ) -> tuple[list[Mechanism], int]:
        stmt = select(MechanismModel)
        stmt = self._apply_filters(stmt, filters)

        sort_column = getattr(MechanismModel, sort_by, MechanismModel.name)
        order_fn = desc if sort_order.lower() == "desc" else asc
        stmt = stmt.order_by(order_fn(sort_column))

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total = int(self.session.execute(total_stmt).scalar_one())

        stmt = stmt.offset((page - 1) * per_page).limit(per_page)
        results = list(self.session.execute(stmt).scalars())
        return self._to_domain_sequence(results), total

    def update(
        self,
        mechanism_id: int,
        updates: MechanismUpdate,
    ) -> Mechanism:
        return self.update_mechanism(mechanism_id, updates)

    def update_mechanism(
        self,
        mechanism_id: int,
        updates: MechanismUpdate,
    ) -> Mechanism:
        model = self.session.get(MechanismModel, mechanism_id)
        if model is None:
            message = f"Mechanism {mechanism_id} not found"
            raise ValueError(message)

        if "name" in updates:
            model.name = updates["name"]
        if "description" in updates:
            model.description = updates["description"]
        if "evidence_tier" in updates:
            model.evidence_tier = updates["evidence_tier"]
        if "confidence_score" in updates:
            model.confidence_score = updates["confidence_score"]
        if "source" in updates:
            model.source = updates["source"]
        if "lifecycle_state" in updates:
            model.lifecycle_state = updates["lifecycle_state"]
        if "protein_domains" in updates:
            model.protein_domains = self._normalize_domains(updates["protein_domains"])
        if "phenotype_ids" in updates:
            model.phenotypes = self._resolve_phenotypes(updates["phenotype_ids"])

        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return MechanismMapper.to_domain(model)

    def _resolve_phenotypes(self, phenotype_ids: list[int]) -> list[PhenotypeModel]:
        if not phenotype_ids:
            return []
        stmt = select(PhenotypeModel).where(PhenotypeModel.id.in_(phenotype_ids))
        phenotypes = list(self.session.execute(stmt).scalars())
        if len(phenotypes) != len(set(phenotype_ids)):
            message = "One or more phenotype IDs do not exist"
            raise ValueError(message)
        return phenotypes

    def _normalize_domains(self, payload: list[JSONObject]) -> list[JSONObject]:
        domains: list[JSONObject] = []
        for raw in payload:
            domain = ProteinDomain.model_validate(raw)
            domains.append(domain.model_dump())
        return domains

    def _apply_filters(
        self,
        stmt: Select[tuple[MechanismModel]],
        filters: QueryFilters | None,
    ) -> Select[tuple[MechanismModel]]:
        if not filters:
            return stmt
        for field, value in filters.items():
            column = getattr(MechanismModel, field, None)
            if column is not None and value is not None:
                filter_value = str(value) if field == "research_space_id" else value
                stmt = stmt.where(column == filter_value)
        return stmt


__all__ = ["SqlAlchemyMechanismRepository"]
