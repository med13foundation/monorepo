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
from src.infrastructure.ingestion.mapping import (
    ExactMapper,
    HybridMapper,
    LLMJudgeMapper,
    VectorMapper,
)
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
from src.infrastructure.repositories.kernel import (
    SqlAlchemyDictionaryRepository,
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelObservationRepository,
    SqlAlchemyProvenanceRepository,
)
from src.infrastructure.security.phi_encryption import (
    build_phi_encryption_service_from_env,
    is_phi_encryption_enabled,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
    from src.domain.ports.dictionary_search_harness_port import (
        DictionarySearchHarnessPort,
    )
    from src.infrastructure.ingestion.interfaces import Mapper


def create_ingestion_pipeline(
    session: Session,
    *,
    mapping_judge_agent: MappingJudgePort | None = None,
    dictionary_search_harness: DictionarySearchHarnessPort | None = None,
) -> IngestionPipeline:
    """
    Create a fully wired ingestion pipeline.
    """
    active_mapping_judge_agent = mapping_judge_agent
    if active_mapping_judge_agent is None:
        from src.infrastructure.llm.adapters.mapping_judge_agent_adapter import (
            ArtanaMappingJudgeAdapter,
        )

        active_mapping_judge_agent = ArtanaMappingJudgeAdapter()

    dictionary_repo = SqlAlchemyDictionaryRepository(session)
    embedding_provider = HybridTextEmbeddingProvider()
    active_dictionary_search_harness = dictionary_search_harness
    if active_dictionary_search_harness is None:
        from src.infrastructure.llm.adapters.dictionary_search_harness_adapter import (
            ArtanaDictionarySearchHarnessAdapter,
        )

        active_dictionary_search_harness = ArtanaDictionarySearchHarnessAdapter(
            dictionary_repo=dictionary_repo,
            embedding_provider=embedding_provider,
            mapping_judge_agent=active_mapping_judge_agent,
        )
    dictionary_service = DictionaryManagementService(
        dictionary_repo=dictionary_repo,
        dictionary_search_harness=active_dictionary_search_harness,
        embedding_provider=embedding_provider,
    )
    enable_phi_encryption = is_phi_encryption_enabled()
    phi_encryption_service = (
        build_phi_encryption_service_from_env() if enable_phi_encryption else None
    )
    entity_repo = SqlAlchemyKernelEntityRepository(
        session,
        phi_encryption_service=phi_encryption_service,
        enable_phi_encryption=enable_phi_encryption,
    )
    observation_repo = SqlAlchemyKernelObservationRepository(session)
    provenance_repo = SqlAlchemyProvenanceRepository(session)

    # Mapper
    exact_mapper = ExactMapper(dictionary_service)
    vector_mapper = VectorMapper(dictionary_service)
    mappers: list[Mapper] = [
        exact_mapper,
        vector_mapper,
        LLMJudgeMapper(
            dictionary_service,
            mapping_judge_agent=active_mapping_judge_agent,
        ),
    ]
    mapper = HybridMapper(mappers)

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
