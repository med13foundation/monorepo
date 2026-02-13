"""Aggregated core repositories."""

from .data_source_activation_repository import SqlAlchemyDataSourceActivationRepository
from .extraction_queue_repository import SqlAlchemyExtractionQueueRepository
from .ingestion_job_repository import SqlAlchemyIngestionJobRepository
from .research_space_repository import SqlAlchemyResearchSpaceRepository
from .source_record_ledger_repository import SqlAlchemySourceRecordLedgerRepository
from .source_sync_state_repository import SqlAlchemySourceSyncStateRepository
from .source_template_repository import SqlAlchemySourceTemplateRepository
from .sqlalchemy_session_repository import SqlAlchemySessionRepository
from .sqlalchemy_user_repository import SqlAlchemyUserRepository
from .storage_repository import (
    SqlAlchemyStorageConfigurationRepository,
    SqlAlchemyStorageOperationRepository,
)
from .system_status_repository import SqlAlchemySystemStatusRepository
from .user_data_source_repository import SqlAlchemyUserDataSourceRepository

__all__ = [
    "SqlAlchemyDataSourceActivationRepository",
    "SqlAlchemyExtractionQueueRepository",
    "SqlAlchemyIngestionJobRepository",
    "SqlAlchemyResearchSpaceRepository",
    "SqlAlchemySourceRecordLedgerRepository",
    "SqlAlchemySourceSyncStateRepository",
    "SqlAlchemySourceTemplateRepository",
    "SqlAlchemySessionRepository",
    "SqlAlchemyStorageConfigurationRepository",
    "SqlAlchemyStorageOperationRepository",
    "SqlAlchemySystemStatusRepository",
    "SqlAlchemyUserDataSourceRepository",
    "SqlAlchemyUserRepository",
]
