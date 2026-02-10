"""
SQLAlchemy implementation of ProvenanceRepository.

Handles provenance record CRUD against the ``provenance`` table.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select

from src.domain.repositories.kernel.provenance_repository import ProvenanceRepository
from src.models.database.kernel.provenance import ProvenanceModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SqlAlchemyProvenanceRepository(ProvenanceRepository):
    """SQLAlchemy implementation of the provenance repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(  # noqa: PLR0913
        self,
        *,
        study_id: str,
        source_type: str,
        source_ref: str | None = None,
        extraction_run_id: str | None = None,
        mapping_method: str | None = None,
        mapping_confidence: float | None = None,
        agent_model: str | None = None,
        raw_input: dict[str, object] | None = None,
    ) -> ProvenanceModel:
        prov = ProvenanceModel(
            id=str(uuid4()),
            study_id=study_id,
            source_type=source_type,
            source_ref=source_ref,
            extraction_run_id=extraction_run_id,
            mapping_method=mapping_method,
            mapping_confidence=mapping_confidence,
            agent_model=agent_model,
            raw_input=raw_input,
        )
        self._session.add(prov)
        self._session.flush()
        return prov

    def get_by_id(self, provenance_id: str) -> ProvenanceModel | None:
        return self._session.get(ProvenanceModel, provenance_id)

    def find_by_study(
        self,
        study_id: str,
        *,
        source_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ProvenanceModel]:
        stmt = (
            select(ProvenanceModel)
            .where(ProvenanceModel.study_id == study_id)
            .order_by(ProvenanceModel.created_at.desc())
        )
        if source_type is not None:
            stmt = stmt.where(ProvenanceModel.source_type == source_type)
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return list(self._session.scalars(stmt).all())

    def find_by_extraction_run(
        self,
        extraction_run_id: str,
    ) -> list[ProvenanceModel]:
        stmt = (
            select(ProvenanceModel)
            .where(ProvenanceModel.extraction_run_id == extraction_run_id)
            .order_by(ProvenanceModel.created_at.desc())
        )
        return list(self._session.scalars(stmt).all())


__all__ = ["SqlAlchemyProvenanceRepository"]
