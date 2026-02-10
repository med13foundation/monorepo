"""
Application services - orchestration layer for use cases.

These services coordinate domain services and repositories to implement
application use cases while maintaining proper separation of concerns.
"""

from src.application.search.search_service import UnifiedSearchService

from . import (
    audit_service,
    authentication_service,
    authorization_service,
    dashboard_service,
    data_discovery_service,
    data_source_activation_service,
    data_source_ai_test_service,
    data_source_authorization_service,
    discovery_configuration_service,
    evidence_service,
    extraction_queue_service,
    extraction_runner_service,
    gene_service,
    ingestion_scheduling_service,
    mechanism_service,
    membership_management_service,
    phenotype_service,
    publication_extraction_service,
    publication_service,
    pubmed_discovery_service,
    pubmed_ingestion_service,
    pubmed_query_builder,
    source_management_service,
    space_data_discovery_service,
    statement_service,
    storage_configuration_requests,
    storage_configuration_service,
    storage_configuration_validator,
    storage_operation_coordinator,
    system_status_service,
    template_management_service,
    user_management_service,
    variant_service,
)

AuthenticationService = authentication_service.AuthenticationService
AuthorizationService = authorization_service.AuthorizationService
AuditTrailService = audit_service.AuditTrailService
DashboardService = dashboard_service.DashboardService
DataDiscoveryService = data_discovery_service.DataDiscoveryService
DataDiscoveryServiceDependencies = (
    data_discovery_service.DataDiscoveryServiceDependencies
)
DataSourceAiTestService = data_source_ai_test_service.DataSourceAiTestService
DataSourceAiTestDependencies = data_source_ai_test_service.DataSourceAiTestDependencies
DataSourceAiTestSettings = data_source_ai_test_service.DataSourceAiTestSettings
DataSourceActivationService = data_source_activation_service.DataSourceActivationService
DataSourceAuthorizationService = (
    data_source_authorization_service.DataSourceAuthorizationService
)
DataSourceAvailabilitySummary = (
    data_source_activation_service.DataSourceAvailabilitySummary
)
DataSourcePermission = data_source_authorization_service.DataSourcePermission
DiscoveryConfigurationService = (
    discovery_configuration_service.DiscoveryConfigurationService
)
EvidenceApplicationService = evidence_service.EvidenceApplicationService
ExtractionEnqueueSummary = extraction_queue_service.ExtractionEnqueueSummary
ExtractionQueueService = extraction_queue_service.ExtractionQueueService
ExtractionRunSummary = extraction_runner_service.ExtractionRunSummary
ExtractionRunnerService = extraction_runner_service.ExtractionRunnerService
GeneApplicationService = gene_service.GeneApplicationService
IngestionSchedulingService = ingestion_scheduling_service.IngestionSchedulingService
IngestionSchedulingOptions = ingestion_scheduling_service.IngestionSchedulingOptions
PhenotypeApplicationService = phenotype_service.PhenotypeApplicationService
MechanismApplicationService = mechanism_service.MechanismApplicationService
MembershipManagementService = membership_management_service.MembershipManagementService
StatementApplicationService = statement_service.StatementApplicationService
PublicationApplicationService = publication_service.PublicationApplicationService
PublicationExtractionListResult = (
    publication_extraction_service.PublicationExtractionListResult
)
PublicationExtractionService = (
    publication_extraction_service.PublicationExtractionService
)
PubMedDiscoveryService = pubmed_discovery_service.PubMedDiscoveryService
PubMedIngestionService = pubmed_ingestion_service.PubMedIngestionService
PubMedQueryBuilder = pubmed_query_builder.PubMedQueryBuilder
PubmedDownloadRequest = pubmed_discovery_service.PubmedDownloadRequest
RunPubmedSearchRequest = pubmed_discovery_service.RunPubmedSearchRequest
SessionRevocationContext = system_status_service.SessionRevocationContext
SourceManagementService = source_management_service.SourceManagementService
SpaceDataDiscoveryService = space_data_discovery_service.SpaceDataDiscoveryService
StorageConfigurationService = storage_configuration_service.StorageConfigurationService
StorageConfigurationValidator = (
    storage_configuration_validator.StorageConfigurationValidator
)
StorageOperationCoordinator = storage_operation_coordinator.StorageOperationCoordinator
SystemStatusService = system_status_service.SystemStatusService
TemplateManagementService = template_management_service.TemplateManagementService
UserManagementService = user_management_service.UserManagementService
VariantApplicationService = variant_service.VariantApplicationService

CreateSourceRequest = source_management_service.CreateSourceRequest
UpdateSourceRequest = source_management_service.UpdateSourceRequest
CreateStorageConfigurationRequest = (
    storage_configuration_requests.CreateStorageConfigurationRequest
)
UpdateStorageConfigurationRequest = (
    storage_configuration_requests.UpdateStorageConfigurationRequest
)
CreateTemplateRequest = template_management_service.CreateTemplateRequest
UpdateTemplateRequest = template_management_service.UpdateTemplateRequest
UserRole = data_source_authorization_service.UserRole

__all__ = [
    "AuthenticationService",
    "AuthorizationService",
    "AuditTrailService",
    "CreateSourceRequest",
    "CreateStorageConfigurationRequest",
    "CreateTemplateRequest",
    "DashboardService",
    "DataDiscoveryService",
    "DataDiscoveryServiceDependencies",
    "DataSourceAiTestService",
    "DataSourceAiTestDependencies",
    "DataSourceAiTestSettings",
    "DataSourceActivationService",
    "DataSourceAuthorizationService",
    "DataSourceAvailabilitySummary",
    "DataSourcePermission",
    "DiscoveryConfigurationService",
    "EvidenceApplicationService",
    "ExtractionEnqueueSummary",
    "ExtractionQueueService",
    "ExtractionRunSummary",
    "ExtractionRunnerService",
    "GeneApplicationService",
    "IngestionSchedulingService",
    "IngestionSchedulingOptions",
    "MechanismApplicationService",
    "MembershipManagementService",
    "StatementApplicationService",
    "PhenotypeApplicationService",
    "PubMedDiscoveryService",
    "PubMedIngestionService",
    "PubMedQueryBuilder",
    "PubmedDownloadRequest",
    "PublicationApplicationService",
    "PublicationExtractionListResult",
    "PublicationExtractionService",
    "RunPubmedSearchRequest",
    "SessionRevocationContext",
    "SourceManagementService",
    "SpaceDataDiscoveryService",
    "StorageConfigurationService",
    "StorageConfigurationValidator",
    "StorageOperationCoordinator",
    "SystemStatusService",
    "TemplateManagementService",
    "UnifiedSearchService",
    "UpdateSourceRequest",
    "UpdateStorageConfigurationRequest",
    "UpdateTemplateRequest",
    "UserManagementService",
    "UserRole",
    "VariantApplicationService",
]
