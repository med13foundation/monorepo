"""
Factory for creating the ingestion pipeline.
"""

from __future__ import annotations

import os
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

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
    from src.infrastructure.ingestion.interfaces import Mapper


_ENABLE_LLM_JUDGE_MAPPER_ENV = "MED13_ENABLE_LLM_JUDGE_MAPPER"


def create_ingestion_pipeline(
    session: Session,
    *,
    mapping_judge_agent: MappingJudgePort | None = None,
) -> IngestionPipeline:
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
    vector_mapper = VectorMapper(dictionary_service)
    mappers: list[Mapper] = [exact_mapper, vector_mapper]
    if os.getenv(_ENABLE_LLM_JUDGE_MAPPER_ENV, "0") == "1":
        active_mapping_judge_agent = mapping_judge_agent
        if active_mapping_judge_agent is None:
            from src.infrastructure.llm.adapters.mapping_judge_agent_adapter import (
                FlujoMappingJudgeAdapter,
            )

            active_mapping_judge_agent = FlujoMappingJudgeAdapter()
        mappers.append(
            LLMJudgeMapper(
                dictionary_service,
                mapping_judge_agent=active_mapping_judge_agent,
            ),
        )
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
