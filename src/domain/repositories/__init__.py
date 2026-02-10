"""
Domain repository interfaces - abstract contracts for data access.

These interfaces define the contracts that domain services depend on,
enabling dependency inversion and testability.
"""

from .base import QuerySpecification, Repository
from .data_source_activation_repository import DataSourceActivationRepository
from .evidence_repository import EvidenceRepository
from .extraction_queue_repository import ExtractionQueueRepository
from .gene_repository import GeneRepository
from .ingestion_job_repository import IngestionJobRepository
from .mechanism_repository import MechanismRepository
from .phenotype_repository import PhenotypeRepository
from .publication_extraction_repository import PublicationExtractionRepository
from .publication_repository import PublicationRepository
from .research_space_repository import ResearchSpaceRepository
from .source_template_repository import SourceTemplateRepository
from .statement_repository import StatementRepository
from .storage_repository import (
    StorageConfigurationRepository,
    StorageOperationRepository,
)
from .system_status_repository import SystemStatusRepository

# Data Sources module repositories
from .user_data_source_repository import UserDataSourceRepository
from .variant_repository import VariantRepository

__all__ = [
    "EvidenceRepository",
    "ExtractionQueueRepository",
    "GeneRepository",
    "IngestionJobRepository",
    "MechanismRepository",
    "PhenotypeRepository",
    "PublicationExtractionRepository",
    "PublicationRepository",
    "ResearchSpaceRepository",
    "QuerySpecification",
    "Repository",
    "SourceTemplateRepository",
    "StatementRepository",
    "StorageConfigurationRepository",
    "StorageOperationRepository",
    "SystemStatusRepository",
    "UserDataSourceRepository",
    "VariantRepository",
    "DataSourceActivationRepository",
]
