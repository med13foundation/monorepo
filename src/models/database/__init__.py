# MED13 Resource Library - SQLAlchemy Database Models
# Metadata-driven graph kernel + infrastructure models
#
# MIGRATION NOTE (2026-02-09): Old domain-specific models (Gene, Variant,
# Phenotype, Evidence, Mechanism, etc.) have been replaced by the kernel
# schema: Entity, Observation, Relation, Provenance + Dictionary tables.
# Surviving infrastructure models are preserved below.

from . import (
    audit,
    base,
    data_discovery,
    data_source_activation,
    extraction_queue,
    ingestion_job,
    research_space,
    session,
    source_record_ledger,
    source_sync_state,
    source_template,
    storage,
    system_status,
    user,
    user_data_source,
)
from .kernel import (
    EntityIdentifierModel,
    EntityModel,
    EntityResolutionPolicyModel,
    ObservationModel,
    ProvenanceModel,
    RelationConstraintModel,
    RelationModel,
    TransformRegistryModel,
    VariableDefinitionModel,
    VariableSynonymModel,
)

# ── Surviving infrastructure models ──
AuditLog = audit.AuditLog
Base = base.Base
SessionModel = session.SessionModel
SystemStatusModel = system_status.SystemStatusModel
UserModel = user.UserModel

SourceTemplateModel = source_template.SourceTemplateModel
SourceTypeEnum = source_template.SourceTypeEnum
TemplateCategory = source_template.TemplateCategoryEnum

UserDataSourceModel = user_data_source.UserDataSourceModel
DataSourceActivationModel = data_source_activation.DataSourceActivationModel
IngestionJobModel = ingestion_job.IngestionJobModel
ExtractionQueueItemModel = extraction_queue.ExtractionQueueItemModel
SourceSyncStateModel = source_sync_state.SourceSyncStateModel
SourceRecordLedgerModel = source_record_ledger.SourceRecordLedgerModel

ResearchSpaceModel = research_space.ResearchSpaceModel
ResearchSpaceMembershipModel = research_space.ResearchSpaceMembershipModel
MembershipRoleEnum = research_space.MembershipRoleEnum
SpaceStatusEnum = research_space.SpaceStatusEnum

SourceCatalogEntryModel = data_discovery.SourceCatalogEntryModel

StorageConfigurationModel = storage.StorageConfigurationModel
StorageHealthSnapshotModel = storage.StorageHealthSnapshotModel
StorageHealthStatusEnum = storage.StorageHealthStatusEnum
StorageOperationModel = storage.StorageOperationModel
StorageOperationStatusEnum = storage.StorageOperationStatusEnum
StorageOperationTypeEnum = storage.StorageOperationTypeEnum
StorageProviderEnum = storage.StorageProviderEnum

__all__ = [
    # Base
    "Base",
    # Kernel: Dictionary (Layer 1)
    "VariableDefinitionModel",
    "VariableSynonymModel",
    "TransformRegistryModel",
    "EntityResolutionPolicyModel",
    "RelationConstraintModel",
    # Kernel: Data (Layer 2)
    "EntityModel",
    "EntityIdentifierModel",
    "ObservationModel",
    "RelationModel",
    "ProvenanceModel",
    # Surviving infrastructure
    "AuditLog",
    "SessionModel",
    "SourceTemplateModel",
    "SourceTypeEnum",
    "StorageConfigurationModel",
    "StorageHealthSnapshotModel",
    "StorageHealthStatusEnum",
    "StorageOperationModel",
    "StorageOperationStatusEnum",
    "StorageOperationTypeEnum",
    "StorageProviderEnum",
    "SystemStatusModel",
    "TemplateCategory",
    "UserModel",
    # Restored Infrastructure
    "UserDataSourceModel",
    "DataSourceActivationModel",
    "IngestionJobModel",
    "ExtractionQueueItemModel",
    "SourceSyncStateModel",
    "SourceRecordLedgerModel",
    # Restored ResearchSpace
    "ResearchSpaceModel",
    "ResearchSpaceMembershipModel",
    "MembershipRoleEnum",
    "SpaceStatusEnum",
    # Restored DataDiscovery
    "SourceCatalogEntryModel",
]
