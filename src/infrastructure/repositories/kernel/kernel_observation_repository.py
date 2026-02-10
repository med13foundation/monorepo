"""
SQLAlchemy implementation of KernelObservationRepository.

Handles typed observation writes/reads against the ``observations`` table,
including batch inserts and provenance-scoped rollback.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from src.domain.repositories.kernel.observation_repository import (
    KernelObservationRepository,
)
from src.models.database.kernel.observations import ObservationModel

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SqlAlchemyKernelObservationRepository(KernelObservationRepository):
    """SQLAlchemy implementation of the kernel observation repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Write ─────────────────────────────────────────────────────────

    def create(  # noqa: PLR0913
        self,
        *,
        study_id: str,
        subject_id: str,
        variable_id: str,
        value_numeric: float | None = None,
        value_text: str | None = None,
        value_date: datetime | None = None,
        value_coded: str | None = None,
        value_json: dict[str, object] | None = None,
        unit: str | None = None,
        observed_at: datetime | None = None,
        provenance_id: str | None = None,
        confidence: float = 1.0,
    ) -> ObservationModel:
        obs = ObservationModel(
            id=str(uuid4()),
            study_id=study_id,
            subject_id=subject_id,
            variable_id=variable_id,
            value_numeric=value_numeric,
            value_text=value_text,
            value_date=value_date,
            value_coded=value_coded,
            value_json=value_json,
            unit=unit,
            observed_at=observed_at,
            provenance_id=provenance_id,
            confidence=confidence,
        )
        self._session.add(obs)
        self._session.flush()
        return obs

    def create_batch(
        self,
        observations: list[dict[str, object]],
    ) -> int:
        if not observations:
            return 0
        models = []
        for obs_data in observations:
            obs_data.setdefault("id", str(uuid4()))
            models.append(ObservationModel(**obs_data))
        self._session.add_all(models)
        self._session.flush()
        return len(models)

    # ── Read ──────────────────────────────────────────────────────────

    def get_by_id(self, observation_id: str) -> ObservationModel | None:
        return self._session.get(ObservationModel, observation_id)

    def find_by_subject(
        self,
        subject_id: str,
        *,
        variable_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ObservationModel]:
        stmt = select(ObservationModel).where(
            ObservationModel.subject_id == subject_id,
        )
        if variable_id is not None:
            stmt = stmt.where(ObservationModel.variable_id == variable_id)
        stmt = stmt.order_by(ObservationModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return list(self._session.scalars(stmt).all())

    def find_by_variable(
        self,
        study_id: str,
        variable_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ObservationModel]:
        stmt = (
            select(ObservationModel)
            .where(
                ObservationModel.study_id == study_id,
                ObservationModel.variable_id == variable_id,
            )
            .order_by(ObservationModel.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return list(self._session.scalars(stmt).all())

    def find_by_study(
        self,
        study_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ObservationModel]:
        stmt = (
            select(ObservationModel)
            .where(ObservationModel.study_id == study_id)
            .order_by(ObservationModel.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return list(self._session.scalars(stmt).all())

    # ── Delete ────────────────────────────────────────────────────────

    def delete(self, observation_id: str) -> bool:
        obs = self.get_by_id(observation_id)
        if obs is None:
            return False
        self._session.delete(obs)
        self._session.flush()
        return True

    def delete_by_provenance(self, provenance_id: str) -> int:
        result = self._session.execute(
            sa_delete(ObservationModel).where(
                ObservationModel.provenance_id == provenance_id,
            ),
        )
        count: int = result.rowcount  # type: ignore[attr-defined]
        self._session.flush()
        logger.info(
            "Rolled back %d observations for provenance %s",
            count,
            provenance_id,
        )
        return count

    # ── Aggregate helpers ─────────────────────────────────────────────

    def count_by_study(self, study_id: str) -> int:
        """Count total observations in a study."""
        result = self._session.execute(
            select(func.count()).where(ObservationModel.study_id == study_id),
        )
        return result.scalar_one()


__all__ = ["SqlAlchemyKernelObservationRepository"]
