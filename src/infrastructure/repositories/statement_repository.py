"""SQLAlchemy-backed implementation of the domain statement repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Select, asc, desc, func, or_, select

from src.domain.repositories.statement_repository import (
    StatementRepository as StatementRepositoryInterface,
)
from src.domain.value_objects.protein_structure import ProteinDomain
from src.infrastructure.mappers.statement_mapper import StatementMapper
from src.models.database.phenotype import PhenotypeModel
from src.models.database.statement import StatementModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.domain.entities.statement import StatementOfUnderstanding
    from src.domain.repositories.base import QuerySpecification
    from src.type_definitions.common import JSONObject, QueryFilters, StatementUpdate


class SqlAlchemyStatementRepository(StatementRepositoryInterface):
    """Domain-facing repository adapter for statements backed by SQLAlchemy."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            message = "Session is not configured"
            raise ValueError(message)
        return self._session

    def _to_domain(
        self,
        model: StatementModel | None,
    ) -> StatementOfUnderstanding | None:
        return StatementMapper.to_domain(model) if model else None

    def _to_domain_sequence(
        self,
        models: list[StatementModel],
    ) -> list[StatementOfUnderstanding]:
        return StatementMapper.to_domain_sequence(models)

    def create(self, statement: StatementOfUnderstanding) -> StatementOfUnderstanding:
        model = StatementMapper.to_model(statement)
        if statement.phenotype_ids:
            model.phenotypes = self._resolve_phenotypes(statement.phenotype_ids)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return StatementMapper.to_domain(model)

    def get_by_id(self, statement_id: int) -> StatementOfUnderstanding | None:
        return self._to_domain(self.session.get(StatementModel, statement_id))

    def find_by_title(
        self,
        title: str,
        *,
        research_space_id: UUID,
    ) -> StatementOfUnderstanding | None:
        stmt = select(StatementModel).where(
            StatementModel.title == title,
            StatementModel.research_space_id == str(research_space_id),
        )
        return self._to_domain(self.session.execute(stmt).scalar_one_or_none())

    def find_all(
        self,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[StatementOfUnderstanding]:
        stmt = select(StatementModel)
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        return self._to_domain_sequence(list(self.session.execute(stmt).scalars()))

    def exists(self, statement_id: int) -> bool:
        stmt = select(func.count()).where(StatementModel.id == statement_id)
        return bool(self.session.execute(stmt).scalar_one())

    def count(self) -> int:
        stmt = select(func.count()).select_from(StatementModel)
        return int(self.session.execute(stmt).scalar_one())

    def delete(self, statement_id: int) -> bool:
        model = self.session.get(StatementModel, statement_id)
        if model is None:
            return False
        self.session.delete(model)
        self.session.commit()
        return True

    def find_by_criteria(
        self,
        spec: QuerySpecification,
    ) -> list[StatementOfUnderstanding]:
        stmt = select(StatementModel)
        for field, value in spec.filters.items():
            column = getattr(StatementModel, field, None)
            if column is not None and value is not None:
                stmt = stmt.where(column == value)
        if spec.offset:
            stmt = stmt.offset(spec.offset)
        if spec.limit:
            stmt = stmt.limit(spec.limit)
        return self._to_domain_sequence(list(self.session.execute(stmt).scalars()))

    def search_statements(
        self,
        query: str,
        limit: int = 10,
        filters: QueryFilters | None = None,
    ) -> list[StatementOfUnderstanding]:
        pattern = f"%{query}%"
        stmt = (
            select(StatementModel)
            .where(
                or_(
                    StatementModel.title.ilike(pattern),
                    StatementModel.summary.ilike(pattern),
                ),
            )
            .limit(limit)
        )
        stmt = self._apply_filters(stmt, filters)
        return self._to_domain_sequence(list(self.session.execute(stmt).scalars()))

    def paginate_statements(
        self,
        page: int,
        per_page: int,
        sort_by: str,
        sort_order: str,
        filters: QueryFilters | None = None,
    ) -> tuple[list[StatementOfUnderstanding], int]:
        stmt = select(StatementModel)
        stmt = self._apply_filters(stmt, filters)

        sort_column = getattr(StatementModel, sort_by, StatementModel.title)
        order_fn = desc if sort_order.lower() == "desc" else asc
        stmt = stmt.order_by(order_fn(sort_column))

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total = int(self.session.execute(total_stmt).scalar_one())

        stmt = stmt.offset((page - 1) * per_page).limit(per_page)
        results = list(self.session.execute(stmt).scalars())
        return self._to_domain_sequence(results), total

    def update(
        self,
        statement_id: int,
        updates: StatementUpdate,
    ) -> StatementOfUnderstanding:
        return self.update_statement(statement_id, updates)

    def update_statement(
        self,
        statement_id: int,
        updates: StatementUpdate,
    ) -> StatementOfUnderstanding:
        model = self.session.get(StatementModel, statement_id)
        if model is None:
            message = f"Statement {statement_id} not found"
            raise ValueError(message)

        self._apply_scalar_updates(model, updates)
        self._apply_relation_updates(model, updates)

        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return StatementMapper.to_domain(model)

    def _apply_scalar_updates(
        self,
        model: StatementModel,
        updates: StatementUpdate,
    ) -> None:
        if "title" in updates:
            model.title = updates["title"]
        if "summary" in updates:
            model.summary = updates["summary"]
        if "evidence_tier" in updates:
            model.evidence_tier = updates["evidence_tier"]
        if "confidence_score" in updates:
            model.confidence_score = updates["confidence_score"]
        if "status" in updates:
            model.status = updates["status"]
        if "source" in updates:
            model.source = updates["source"]
        if "promoted_mechanism_id" in updates:
            model.promoted_mechanism_id = updates["promoted_mechanism_id"]

    def _apply_relation_updates(
        self,
        model: StatementModel,
        updates: StatementUpdate,
    ) -> None:
        if "protein_domains" in updates:
            model.protein_domains = self._normalize_domains(updates["protein_domains"])
        if "phenotype_ids" in updates:
            model.phenotypes = self._resolve_phenotypes(updates["phenotype_ids"])

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
        stmt: Select[tuple[StatementModel]],
        filters: QueryFilters | None,
    ) -> Select[tuple[StatementModel]]:
        if not filters:
            return stmt
        for field, value in filters.items():
            column = getattr(StatementModel, field, None)
            if column is not None and value is not None:
                filter_value = str(value) if field == "research_space_id" else value
                stmt = stmt.where(column == filter_value)
        return stmt


__all__ = ["SqlAlchemyStatementRepository"]
