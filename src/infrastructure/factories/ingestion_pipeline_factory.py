"""
Factory for creating the ingestion pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.services.kernel.dictionary_management_service import (
    DictionaryManagementService,
)
from src.application.services.kernel.kernel_observation_service import (
    KernelObservationService,
)
from src.infrastructure.embeddings import HybridTextEmbeddingProvider
from src.infrastructure.ingestion.mapping.exact_mapper import ExactMapper
from src.infrastructure.ingestion.mapping.hybrid_mapper import HybridMapper
from src.infrastructure.ingestion.normalization.composite_normalizer import (
    CompositeNormalizer,
)
from src.infrastructure.ingestion.normalization.unit_converter import UnitConverter
from src.infrastructure.ingestion.normalization.value_caster import ValueCaster
from src.infrastructure.ingestion.pipeline import IngestionPipeline
from src.infrastructure.ingestion.provenance.tracker import ProvenanceTracker
from src.infrastructure.ingestion.resolution.entity_resolver import EntityResolver
from src.infrastructure.ingestion.validation.observation_validator import (
    ObservationValidator,
)
from src.infrastructure.repositories.kernel.kernel_dictionary_repository import (
    SqlAlchemyDictionaryRepository,
)
from src.infrastructure.repositories.kernel.kernel_entity_repository import (
    SqlAlchemyKernelEntityRepository,
)
from src.infrastructure.repositories.kernel.kernel_observation_repository import (
    SqlAlchemyKernelObservationRepository,
)
from src.infrastructure.repositories.kernel.kernel_provenance_repository import (
    SqlAlchemyProvenanceRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def create_ingestion_pipeline(session: Session) -> IngestionPipeline:
    """
    Create a fully wired ingestion pipeline.
    """
    dictionary_repo = SqlAlchemyDictionaryRepository(session)
    dictionary_service = DictionaryManagementService(
        dictionary_repo=dictionary_repo,
        embedding_provider=HybridTextEmbeddingProvider(),
    )
    entity_repo = SqlAlchemyKernelEntityRepository(session)
    observation_repo = SqlAlchemyKernelObservationRepository(session)
    provenance_repo = SqlAlchemyProvenanceRepository(session)

    # Mapper
    exact_mapper = ExactMapper(dictionary_service)
    mapper = HybridMapper([exact_mapper])

    # Normalizer
    unit_converter = UnitConverter(dictionary_service)
    value_caster = ValueCaster(dictionary_service)
    normalizer = CompositeNormalizer(unit_converter, value_caster)

    # Resolver
    resolver = EntityResolver(dictionary_service, entity_repo)

    # Validator
    # NOTE: Triple validation is enforced in KernelRelationService when
    # relation edges are created. This ingestion pipeline currently persists
    # observations only.
    validator = ObservationValidator(dictionary_service)

    # Services
    observation_service = KernelObservationService(
        observation_repo,
        entity_repo,
        dictionary_service,
    )
    provenance_tracker = ProvenanceTracker(provenance_repo)

    return IngestionPipeline(
        mapper=mapper,
        normalizer=normalizer,
        resolver=resolver,
        validator=validator,
        observation_service=observation_service,
        provenance_tracker=provenance_tracker,
    )
