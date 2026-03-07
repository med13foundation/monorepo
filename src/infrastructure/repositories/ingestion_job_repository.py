"""SQLAlchemy repository adapter for ingestion jobs."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, desc, func, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError

from src.domain.entities.ingestion_job import (
    IngestionError,
    IngestionJob,
    IngestionJobKind,
    IngestionStatus,
    IngestionTrigger,
    JobMetrics,
)
from src.domain.repositories.ingestion_job_repository import (
    IngestionJobRepository,
)
from src.infrastructure.llm.config import load_runtime_policy
from src.infrastructure.mappers.ingestion_job_mapper import IngestionJobMapper
from src.models.database.ingestion_job import (
    IngestionJobKindEnum,
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

_PIPELINE_CLAIM_SCAN_LIMIT = 200
_PIPELINE_ACTIVE_QUEUE_STATUSES: frozenset[str] = frozenset(
    {"queued", "retrying", "running"},
)
_PIPELINE_CLAIMABLE_QUEUE_STATUSES: frozenset[str] = frozenset(
    {"queued", "retrying"},
)


def _coerce_json_object(raw_value: object) -> JSONObject:
    if not isinstance(raw_value, dict):
        return {}
    return {str(key): value for key, value in raw_value.items()}


def _normalize_optional_string(raw_value: object) -> str | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized or None


def _parse_timestamp(raw_value: object) -> datetime | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


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
            or "column ingestion_jobs.dictionary_version_used does not exist" in message
            or "column ingestion_jobs.replay_policy does not exist" in message
            or "column ingestion_jobs.job_kind does not exist" in message
        )

    def _resolve_dictionary_version_used(self) -> int:
        try:
            value = self.session.execute(
                text("SELECT COALESCE(MAX(id), 0) FROM dictionary_changelog"),
            ).scalar_one()
        except (OperationalError, ProgrammingError, SQLAlchemyError):
            self.session.rollback()
            return 0
        if isinstance(value, int):
            return max(value, 0)
        if isinstance(value, float):
            return max(int(value), 0)
        if isinstance(value, str):
            try:
                return max(int(value), 0)
            except ValueError:
                return 0
        return 0

    @property
    def session(self) -> Session:
        if self._session is None:
            message = "Session not provided"
            raise ValueError(message)
        return self._session

    def save(self, job: IngestionJob) -> IngestionJob:
        payload = IngestionJobMapper.to_model_dict(job)
        raw_dictionary_version = payload.get("dictionary_version_used")
        if not isinstance(raw_dictionary_version, int) or raw_dictionary_version < 0:
            payload["dictionary_version_used"] = self._resolve_dictionary_version_used()
        raw_replay_policy = payload.get("replay_policy")
        if not isinstance(raw_replay_policy, str) or not raw_replay_policy.strip():
            payload["replay_policy"] = load_runtime_policy().replay_policy
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

    @staticmethod
    def _pipeline_payload_from_job_metadata(job_metadata: object) -> JSONObject:
        metadata = _coerce_json_object(job_metadata)
        return _coerce_json_object(metadata.get("pipeline_run"))

    @classmethod
    def _resolve_pipeline_run_id(cls, job_metadata: object) -> str | None:
        pipeline_payload = cls._pipeline_payload_from_job_metadata(job_metadata)
        return _normalize_optional_string(pipeline_payload.get("run_id"))

    @classmethod
    def _resolve_pipeline_queue_status(cls, job_metadata: object) -> str | None:
        pipeline_payload = cls._pipeline_payload_from_job_metadata(job_metadata)
        queue_status = _normalize_optional_string(pipeline_payload.get("queue_status"))
        if queue_status is not None:
            return queue_status
        return _normalize_optional_string(pipeline_payload.get("status"))

    @classmethod
    def _resolve_pipeline_next_attempt_at(cls, job_metadata: object) -> datetime | None:
        pipeline_payload = cls._pipeline_payload_from_job_metadata(job_metadata)
        return _parse_timestamp(pipeline_payload.get("next_attempt_at"))

    @staticmethod
    def _build_pipeline_job_metadata_update(  # noqa: PLR0913
        *,
        existing_job_metadata: object,
        status: str,
        queue_status: str,
        updated_at: datetime,
        worker_id: str | None = None,
        next_attempt_at: datetime | None = None,
        last_error: str | None = None,
        error_category: str | None = None,
        attempt_count: int | None = None,
        heartbeat_at: datetime | None = None,
    ) -> JSONObject:
        metadata = _coerce_json_object(existing_job_metadata)
        pipeline_payload = _coerce_json_object(metadata.get("pipeline_run"))
        pipeline_payload["status"] = status
        pipeline_payload["queue_status"] = queue_status
        pipeline_payload["updated_at"] = IngestionJobMapper.serialize_timestamp(
            updated_at,
        )
        pipeline_payload["next_attempt_at"] = (
            IngestionJobMapper.serialize_timestamp(next_attempt_at)
            if next_attempt_at is not None
            else None
        )
        if worker_id is not None:
            pipeline_payload["worker_id"] = worker_id
        if last_error is not None:
            pipeline_payload["last_error"] = last_error
        if error_category is not None:
            pipeline_payload["error_category"] = error_category
        if attempt_count is not None:
            pipeline_payload["attempt_count"] = max(attempt_count, 0)
        if heartbeat_at is not None:
            pipeline_payload["heartbeat_at"] = IngestionJobMapper.serialize_timestamp(
                heartbeat_at,
            )
        metadata["pipeline_run"] = pipeline_payload
        return metadata

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

    def find_latest_by_source_and_kind(
        self,
        *,
        source_id: UUID,
        job_kind: IngestionJobKind,
        limit: int = 50,
    ) -> list[IngestionJob]:
        stmt = (
            select(IngestionJobModel)
            .where(IngestionJobModel.source_id == str(source_id))
            .where(
                IngestionJobModel.job_kind == IngestionJobKindEnum(job_kind.value),
            )
            .order_by(desc(IngestionJobModel.triggered_at))
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

    def find_active_pipeline_job_for_source(
        self,
        *,
        source_id: UUID,
        exclude_run_id: str | None = None,
    ) -> IngestionJob | None:
        normalized_exclude_run_id = _normalize_optional_string(exclude_run_id)
        statement = (
            select(IngestionJobModel)
            .where(IngestionJobModel.source_id == str(source_id))
            .where(
                IngestionJobModel.job_kind
                == IngestionJobKindEnum.PIPELINE_ORCHESTRATION,
            )
            .where(
                IngestionJobModel.status.in_(
                    (
                        IngestionStatusEnum.PENDING,
                        IngestionStatusEnum.RUNNING,
                    ),
                ),
            )
            .order_by(desc(IngestionJobModel.triggered_at))
            .limit(_PIPELINE_CLAIM_SCAN_LIMIT)
        )
        candidates = self.session.execute(statement).scalars().all()
        for candidate in candidates:
            queue_status = self._resolve_pipeline_queue_status(candidate.job_metadata)
            if queue_status not in _PIPELINE_ACTIVE_QUEUE_STATUSES:
                continue
            candidate_run_id = self._resolve_pipeline_run_id(candidate.job_metadata)
            if (
                normalized_exclude_run_id is not None
                and candidate_run_id == normalized_exclude_run_id
            ):
                continue
            return IngestionJobMapper.to_domain(candidate)
        return None

    def count_active_pipeline_queue_jobs(self) -> int:
        statement = (
            select(IngestionJobModel)
            .where(
                IngestionJobModel.job_kind
                == IngestionJobKindEnum.PIPELINE_ORCHESTRATION,
            )
            .where(IngestionJobModel.status == IngestionStatusEnum.PENDING)
        )
        candidates = self.session.execute(statement).scalars().all()
        return sum(
            1
            for candidate in candidates
            if self._resolve_pipeline_queue_status(candidate.job_metadata)
            in {"queued", "retrying"}
        )

    def claim_next_pipeline_job(
        self,
        *,
        worker_id: str,
        as_of: datetime,
    ) -> IngestionJob | None:
        statement = (
            select(IngestionJobModel)
            .where(
                IngestionJobModel.job_kind
                == IngestionJobKindEnum.PIPELINE_ORCHESTRATION,
            )
            .where(IngestionJobModel.status == IngestionStatusEnum.PENDING)
            .order_by(IngestionJobModel.triggered_at.asc())
            .limit(_PIPELINE_CLAIM_SCAN_LIMIT)
            .with_for_update(skip_locked=True)
        )
        try:
            candidates = self.session.execute(statement).scalars().all()
            for candidate in candidates:
                queue_status = self._resolve_pipeline_queue_status(
                    candidate.job_metadata,
                )
                if queue_status not in _PIPELINE_CLAIMABLE_QUEUE_STATUSES:
                    continue
                next_attempt_at = self._resolve_pipeline_next_attempt_at(
                    candidate.job_metadata,
                )
                if next_attempt_at is not None and next_attempt_at > as_of:
                    continue
                candidate.status = IngestionStatusEnum.RUNNING
                candidate.started_at = IngestionJobMapper.serialize_timestamp(as_of)
                candidate.completed_at = None
                candidate.job_metadata = self._build_pipeline_job_metadata_update(
                    existing_job_metadata=candidate.job_metadata,
                    status="running",
                    queue_status="running",
                    updated_at=as_of,
                    worker_id=worker_id,
                    heartbeat_at=as_of,
                )
                self.session.commit()
                self.session.refresh(candidate)
                return IngestionJobMapper.to_domain(candidate)
            self.session.rollback()
        except Exception:
            self.session.rollback()
            raise
        return None

    def heartbeat_pipeline_job(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        heartbeat_at: datetime,
    ) -> IngestionJob | None:
        model = self.session.get(IngestionJobModel, str(job_id))
        if model is None:
            return None
        if model.job_kind != IngestionJobKindEnum.PIPELINE_ORCHESTRATION:
            return None
        if model.status != IngestionStatusEnum.RUNNING:
            return None
        current_worker_id = _normalize_optional_string(
            self._pipeline_payload_from_job_metadata(model.job_metadata).get(
                "worker_id",
            ),
        )
        if current_worker_id is not None and current_worker_id != worker_id:
            return None
        model.job_metadata = self._build_pipeline_job_metadata_update(
            existing_job_metadata=model.job_metadata,
            status="running",
            queue_status="running",
            updated_at=heartbeat_at,
            worker_id=worker_id,
            heartbeat_at=heartbeat_at,
        )
        self.session.commit()
        self.session.refresh(model)
        return IngestionJobMapper.to_domain(model)

    def mark_pipeline_job_retryable(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        next_attempt_at: datetime,
        last_error: str,
        error_category: str | None,
    ) -> IngestionJob | None:
        model = self.session.get(IngestionJobModel, str(job_id))
        if model is None:
            return None
        if model.job_kind != IngestionJobKindEnum.PIPELINE_ORCHESTRATION:
            return None
        pipeline_payload = self._pipeline_payload_from_job_metadata(model.job_metadata)
        current_worker_id = _normalize_optional_string(
            pipeline_payload.get("worker_id"),
        )
        if current_worker_id is not None and current_worker_id != worker_id:
            return None
        attempt_count_raw = pipeline_payload.get("attempt_count")
        attempt_count = attempt_count_raw if isinstance(attempt_count_raw, int) else 0
        model.status = IngestionStatusEnum.PENDING
        model.started_at = None
        model.completed_at = None
        model.metrics = JobMetrics(
            records_processed=0,
            records_failed=0,
            records_skipped=0,
            bytes_processed=0,
            api_calls_made=0,
            duration_seconds=None,
            records_per_second=None,
        ).model_dump(mode="json")
        model.errors = []
        model.job_metadata = self._build_pipeline_job_metadata_update(
            existing_job_metadata=model.job_metadata,
            status="retrying",
            queue_status="retrying",
            updated_at=datetime.now(UTC),
            worker_id=worker_id,
            next_attempt_at=next_attempt_at,
            last_error=last_error,
            error_category=error_category,
            attempt_count=attempt_count + 1,
        )
        self.session.commit()
        self.session.refresh(model)
        return IngestionJobMapper.to_domain(model)

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
