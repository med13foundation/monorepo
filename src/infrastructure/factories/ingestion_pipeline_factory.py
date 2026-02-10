"""
Factory for creating the ingestion pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.services.kernel.kernel_observation_service import (
    KernelObservationService,
)
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
    entity_repo = SqlAlchemyKernelEntityRepository(session)
    observation_repo = SqlAlchemyKernelObservationRepository(session)
    provenance_repo = SqlAlchemyProvenanceRepository(session)

    # Mapper
    exact_mapper = ExactMapper(dictionary_repo)
    mapper = HybridMapper([exact_mapper])

    # Normalizer
    unit_converter = UnitConverter(dictionary_repo)
    value_caster = ValueCaster(dictionary_repo)
    normalizer = CompositeNormalizer(unit_converter, value_caster)

    # Resolver
    resolver = EntityResolver(dictionary_repo, entity_repo)

    # Validator
    validator = ObservationValidator(dictionary_repo)

    # Services
    observation_service = KernelObservationService(observation_repo, dictionary_repo)
    provenance_tracker = ProvenanceTracker(provenance_repo)

    return IngestionPipeline(
        mapper=mapper,
        normalizer=normalizer,
        resolver=resolver,
        validator=validator,
        observation_service=observation_service,
        provenance_tracker=provenance_tracker,
    )
