"""Aggregated data source entities."""

from .data_source_activation import ActivationScope, DataSourceActivation
from .extraction_queue_item import ExtractionQueueItem, ExtractionStatus
from .ingestion_job import (
    IngestionError,
    IngestionJob,
    IngestionStatus,
    IngestionTrigger,
    JobMetrics,
)
from .source_record_ledger import SourceRecordLedgerEntry
from .source_sync_state import CheckpointKind, SourceSyncState
from .source_template import (
    SourceTemplate,
    TemplateCategory,
    TemplateUIConfig,
    ValidationRule,
)
from .storage_configuration import (
    StorageConfiguration,
    StorageHealthSnapshot,
    StorageOperation,
    StorageProviderMetadata,
    StorageProviderTestResult,
)
from .user_data_source import (
    IngestionSchedule,
    QualityMetrics,
    SourceConfiguration,
    SourceStatus,
    SourceType,
    UserDataSource,
)

__all__ = [
    "ActivationScope",
    "DataSourceActivation",
    "ExtractionQueueItem",
    "ExtractionStatus",
    "IngestionError",
    "IngestionJob",
    "IngestionSchedule",
    "IngestionStatus",
    "IngestionTrigger",
    "JobMetrics",
    "CheckpointKind",
    "QualityMetrics",
    "SourceRecordLedgerEntry",
    "SourceConfiguration",
    "SourceStatus",
    "SourceSyncState",
    "SourceTemplate",
    "SourceType",
    "StorageConfiguration",
    "StorageHealthSnapshot",
    "StorageOperation",
    "StorageProviderMetadata",
    "StorageProviderTestResult",
    "TemplateCategory",
    "TemplateUIConfig",
    "UserDataSource",
    "ValidationRule",
]
