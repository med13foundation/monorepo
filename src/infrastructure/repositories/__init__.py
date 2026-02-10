"""Repository adapters for infrastructure layer."""

from .biomedical import (
    SqlAlchemyEvidenceRepository,
    SqlAlchemyGeneRepository,
    SqlAlchemyMechanismRepository,
    SqlAlchemyPhenotypeRepository,
    SqlAlchemyPublicationExtractionRepository,
    SqlAlchemyPublicationRepository,
    SqlAlchemyStatementRepository,
    SqlAlchemyVariantRepository,
)
from .core import (
    SqlAlchemyDataSourceActivationRepository,
    SqlAlchemyExtractionQueueRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemyResearchSpaceRepository,
    SqlAlchemySessionRepository,
    SqlAlchemySourceTemplateRepository,
    SqlAlchemyStorageConfigurationRepository,
    SqlAlchemyStorageOperationRepository,
    SqlAlchemySystemStatusRepository,
    SqlAlchemyUserDataSourceRepository,
    SqlAlchemyUserRepository,
)
from .data_discovery import (
    SQLAlchemyDataDiscoverySessionRepository,
    SQLAlchemyDiscoveryPresetRepository,
    SQLAlchemyDiscoverySearchJobRepository,
    SQLAlchemyQueryTestResultRepository,
    SQLAlchemySourceCatalogRepository,
)

__all__ = [
    "SQLAlchemyDataDiscoverySessionRepository",
    "SQLAlchemyDiscoveryPresetRepository",
    "SQLAlchemyDiscoverySearchJobRepository",
    "SQLAlchemyQueryTestResultRepository",
    "SQLAlchemySourceCatalogRepository",
    "SqlAlchemyDataSourceActivationRepository",
    "SqlAlchemyEvidenceRepository",
    "SqlAlchemyExtractionQueueRepository",
    "SqlAlchemyGeneRepository",
    "SqlAlchemyIngestionJobRepository",
    "SqlAlchemyMechanismRepository",
    "SqlAlchemyPhenotypeRepository",
    "SqlAlchemyPublicationExtractionRepository",
    "SqlAlchemyPublicationRepository",
    "SqlAlchemyStatementRepository",
    "SqlAlchemyResearchSpaceRepository",
    "SqlAlchemySourceTemplateRepository",
    "SqlAlchemySessionRepository",
    "SqlAlchemyStorageConfigurationRepository",
    "SqlAlchemyStorageOperationRepository",
    "SqlAlchemySystemStatusRepository",
    "SqlAlchemyUserDataSourceRepository",
    "SqlAlchemyUserRepository",
    "SqlAlchemyVariantRepository",
]
