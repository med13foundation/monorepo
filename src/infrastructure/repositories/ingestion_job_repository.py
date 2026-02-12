"""SQLAlchemy repository adapter for ingestion jobs."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, desc, func, select
from sqlalchemy.exc import OperationalError, ProgrammingError

from src.domain.entities.ingestion_job import (
    IngestionError,
    IngestionJob,
    IngestionStatus,
    IngestionTrigger,
    JobMetrics,
)
from src.domain.repositories.ingestion_job_repository import (
    IngestionJobRepository,
)
from src.infrastructure.mappers.ingestion_job_mapper import IngestionJobMapper
from src.models.database.ingestion_job import (
    IngestionJobModel,
    IngestionStatusEnum,
    IngestionTriggerEnum,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy import Select
    from sqlalchemy.orm import Session
    from sqlalchemy.sql.elements import ColumnElement

    from src.type_definitions.common import JSONObject


class SqlAlchemyIngestionJobRepository(IngestionJobRepository):
    """Domain-facing repository implementation for ingestion jobs."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @staticmethod
    def _is_missing_optional_column_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "column ingestion_jobs.job_metadata does not exist" in message
            or "column ingestion_jobs.source_config_snapshot does not exist" in message
        )

    @property
    def session(self) -> Session:
        if self._session is None:
            message = "Session not provided"
            raise ValueError(message)
        return self._session

    def save(self, job: IngestionJob) -> IngestionJob:
        payload = IngestionJobMapper.to_model_dict(job)
        model = self.session.get(IngestionJobModel, payload["id"])
        if model is None:
            model = IngestionJobModel(**payload)
            self.session.add(model)
        else:
            for field, value in payload.items():
                setattr(model, field, value)
        self.session.commit()
        self.session.refresh(model)
        return IngestionJobMapper.to_domain(model)

    def find_by_id(self, job_id: UUID) -> IngestionJob | None:
        stmt = select(IngestionJobModel).where(IngestionJobModel.id == str(job_id))
        model = self.session.execute(stmt).scalar_one_or_none()
        return IngestionJobMapper.to_domain(model) if model else None

    def _fetch(
        self,
        stmt: Select[tuple[IngestionJobModel]],
    ) -> list[IngestionJob]:
        logger = logging.getLogger(__name__)
        try:
            models = self.session.execute(stmt).scalars().all()
        except (OperationalError, ProgrammingError) as exc:
            if not self._is_missing_optional_column_error(exc):
                raise
            logger.warning(
                "Ingestion job optional columns are unavailable; returning empty history list",
                exc_info=exc,
            )
            self.session.rollback()
            return []
        return [IngestionJobMapper.to_domain(model) for model in models]

    def find_by_source(
        self,
        source_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        stmt = (
            select(IngestionJobModel)
            .where(IngestionJobModel.source_id == str(source_id))
            .order_by(desc(IngestionJobModel.triggered_at))
            .offset(skip)
            .limit(limit)
        )
        return self._fetch(stmt)

    def find_by_trigger(
        self,
        trigger: IngestionTrigger,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        stmt = (
            select(IngestionJobModel)
            .where(IngestionJobModel.trigger == IngestionTriggerEnum(trigger.value))
            .order_by(desc(IngestionJobModel.triggered_at))
            .offset(skip)
            .limit(limit)
        )
        return self._fetch(stmt)

    def find_by_status(
        self,
        status: IngestionStatus,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        stmt = (
            select(IngestionJobModel)
            .where(IngestionJobModel.status == IngestionStatusEnum(status.value))
            .order_by(desc(IngestionJobModel.triggered_at))
            .offset(skip)
            .limit(limit)
        )
        return self._fetch(stmt)

    def find_running_jobs(self, skip: int = 0, limit: int = 50) -> list[IngestionJob]:
        return self.find_by_status(IngestionStatus.RUNNING, skip, limit)

    def find_failed_jobs(
        self,
        since: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        stmt = select(IngestionJobModel).where(
            IngestionJobModel.status == IngestionStatusEnum.FAILED,
        )
        if since:
            stmt = stmt.where(
                IngestionJobModel.triggered_at
                >= IngestionJobMapper.serialize_timestamp(since),
            )
        stmt = (
            stmt.order_by(desc(IngestionJobModel.triggered_at))
            .offset(skip)
            .limit(limit)
        )
        return self._fetch(stmt)

    def find_recent_jobs(
        self,
        hours: int = 24,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        threshold = datetime.now(UTC) - timedelta(hours=hours)
        stmt = (
            select(IngestionJobModel)
            .where(
                IngestionJobModel.triggered_at
                >= IngestionJobMapper.serialize_timestamp(threshold),
            )
            .order_by(desc(IngestionJobModel.triggered_at))
            .offset(skip)
            .limit(limit)
        )
        return self._fetch(stmt)

    def find_by_triggered_by(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        stmt = (
            select(IngestionJobModel)
            .where(IngestionJobModel.triggered_by == str(user_id))
            .order_by(desc(IngestionJobModel.triggered_at))
            .offset(skip)
            .limit(limit)
        )
        return self._fetch(stmt)

    def update_status(
        self,
        job_id: UUID,
        status: IngestionStatus,
    ) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        updated_job = job.model_copy(update={"status": status})
        return self.save(updated_job)

    def update_metrics(
        self,
        job_id: UUID,
        metrics: JobMetrics,
    ) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        updated_job = job.model_copy(update={"metrics": metrics})
        return self.save(updated_job)

    def add_error(
        self,
        job_id: UUID,
        error: IngestionError,
    ) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        updated_job = job.model_copy(
            update={"errors": [*job.errors, error]},
        )
        return self.save(updated_job)

    def delete(self, job_id: UUID) -> bool:
        model = self.session.get(IngestionJobModel, str(job_id))
        if model is None:
            return False
        self.session.delete(model)
        self.session.commit()
        return True

    def start_job(self, job_id: UUID) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        return self.save(job.start_execution())

    def complete_job(
        self,
        job_id: UUID,
        metrics: JobMetrics,
    ) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        return self.save(job.complete_successfully(metrics))

    def fail_job(
        self,
        job_id: UUID,
        error: IngestionError,
    ) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        return self.save(job.fail(error))

    def cancel_job(self, job_id: UUID) -> IngestionJob | None:
        job = self.find_by_id(job_id)
        if job is None:
            return None
        return self.save(job.cancel())

    def delete_old_jobs(self, days: int = 90) -> int:
        threshold = datetime.now(UTC) - timedelta(days=days)
        stmt = delete(IngestionJobModel).where(
            IngestionJobModel.triggered_at
            < IngestionJobMapper.serialize_timestamp(threshold),
        )
        result = self.session.execute(stmt)
        self.session.commit()
        rowcount = getattr(result, "rowcount", None)
        return int(rowcount or 0)

    def count_by_source(self, source_id: UUID) -> int:
        stmt = select(func.count()).where(IngestionJobModel.source_id == str(source_id))
        return int(self.session.execute(stmt).scalar_one())

    def count_by_status(self, status: IngestionStatus) -> int:
        stmt = select(func.count()).where(
            IngestionJobModel.status == IngestionStatusEnum(status.value),
        )
        return int(self.session.execute(stmt).scalar_one())

    def count_by_trigger(self, trigger: IngestionTrigger) -> int:
        stmt = select(func.count()).where(
            IngestionJobModel.trigger == IngestionTriggerEnum(trigger.value),
        )
        return int(self.session.execute(stmt).scalar_one())

    def exists(self, job_id: UUID) -> bool:
        stmt = select(func.count()).where(IngestionJobModel.id == str(job_id))
        return bool(self.session.execute(stmt).scalar_one())

    def get_job_statistics(self, source_id: UUID | None = None) -> JSONObject:
        filters: list[ColumnElement[bool]] = []
        if source_id:
            filters.append(IngestionJobModel.source_id == str(source_id))

        def _count(additional_clause: ColumnElement[bool] | None = None) -> int:
            stmt = select(func.count()).select_from(IngestionJobModel)
            for clause in filters:
                stmt = stmt.where(clause)
            if additional_clause is not None:
                stmt = stmt.where(additional_clause)
            return int(self.session.execute(stmt).scalar_one())

        total_jobs = _count()
        status_counts = {
            status.value: _count(
                IngestionJobModel.status == IngestionStatusEnum(status.value),
            )
            for status in IngestionStatus
        }
        trigger_counts = {
            trigger.value: _count(
                IngestionJobModel.trigger == IngestionTriggerEnum(trigger.value),
            )
            for trigger in IngestionTrigger
        }

        return {
            "total_jobs": total_jobs,
            "status_counts": status_counts,
            "trigger_counts": trigger_counts,
        }

    def get_recent_failures(
        self,
        limit: int = 10,
    ) -> list[tuple[IngestionJob, IngestionError]]:
        stmt = (
            select(IngestionJobModel)
            .where(IngestionJobModel.status == IngestionStatusEnum.FAILED)
            .order_by(desc(IngestionJobModel.triggered_at))
            .limit(limit)
        )
        jobs = self._fetch(stmt)
        failures: list[tuple[IngestionJob, IngestionError]] = []
        for job in jobs:
            error = (
                job.errors[-1]
                if job.errors
                else IngestionError(
                    error_type="unknown",
                    error_message="No error recorded",
                    record_id=None,
                )
            )
            failures.append((job, error))
        return failures
