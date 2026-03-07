"""
Factory mixin for building application services used by the dependency container.
"""

from __future__ import annotations

import logging
import os
from contextlib import suppress
from typing import TYPE_CHECKING

from src.application.agents.services import (
    ContentEnrichmentService,
    ContentEnrichmentServiceDependencies,
    EntityRecognitionService,
    EntityRecognitionServiceDependencies,
    ExtractionService,
    ExtractionServiceDependencies,
    GovernanceService,
    GraphConnectionService,
    GraphConnectionServiceDependencies,
    GraphSearchService,
    GraphSearchServiceDependencies,
)
from src.domain.agents.models import ModelCapability
from src.infrastructure.dependency_injection import (
    analysis_service_factories,
    curation_service_factories,
    discovery_service_factories,
    kernel_service_factories,
)
from src.infrastructure.factories.ingestion_pipeline_factory import (
    create_ingestion_pipeline,
)
from src.infrastructure.llm.adapters import (
    ArtanaContentEnrichmentAdapter,
    ArtanaEntityRecognitionAdapter,
    ArtanaEvidenceSentenceHarnessAdapter,
    ArtanaExtractionAdapter,
    ArtanaExtractionPolicyAdapter,
    ArtanaGraphConnectionAdapter,
    ArtanaGraphSearchAdapter,
    ArtanaMappingJudgeAdapter,
    ArtanaQueryAgentAdapter,
)
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.repositories import (
    SqlAlchemyResearchSpaceRepository,
    SqlAlchemySourceDocumentRepository,
)
from src.infrastructure.repositories.kernel import (
    SqlAlchemyGraphQueryRepository,
    SqlAlchemyKernelClaimEvidenceRepository,
    SqlAlchemyKernelClaimParticipantRepository,
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelRelationClaimRepository,
    SqlAlchemyKernelRelationRepository,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from artana.store import PostgresStore
    from sqlalchemy.orm import Session

    from src.application.services import SystemStatusService
    from src.domain.agents.ports import (
        EntityRecognitionPort,
        ExtractionAgentPort,
        GraphConnectionPort,
        QueryAgentPort,
    )
    from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
    from src.domain.ports.evidence_sentence_harness_port import (
        EvidenceSentenceHarnessPort,
    )
    from src.domain.services import storage_metrics, storage_providers


class ApplicationServiceFactoryMixin(
    analysis_service_factories.AnalysisServiceFactoryMixin,
    curation_service_factories.CurationServiceFactoryMixin,
    discovery_service_factories.DiscoveryServiceFactoryMixin,
    kernel_service_factories.KernelServiceFactoryMixin,
):
    """Provides helper factory methods shared by the dependency container."""

    if TYPE_CHECKING:
        _storage_plugin_registry: storage_providers.StoragePluginRegistry
        _storage_metrics_recorder: storage_metrics.StorageMetricsRecorder
        _entity_recognition_agent: EntityRecognitionPort | None
        _extraction_agent: ExtractionAgentPort | None
        _mapping_judge_agent: MappingJudgePort | None
        _graph_connection_agent: GraphConnectionPort | None
        _query_agent: QueryAgentPort | None

    if TYPE_CHECKING:

        def get_system_status_service(self) -> SystemStatusService: ...

        def get_artana_store(self) -> PostgresStore: ...

    _logger = logging.getLogger(__name__)

    def get_query_agent(self) -> QueryAgentPort:
        if self._query_agent is None:
            registry = get_model_registry()
            model_spec = registry.get_default_model(ModelCapability.QUERY_GENERATION)
            self._query_agent = ArtanaQueryAgentAdapter(
                model=model_spec.model_id,
                artana_store=self.get_artana_store(),
            )
        return self._query_agent

    @staticmethod
    def _build_review_queue_submitter(
        session: Session,
    ) -> Callable[[str, str, str | None, str], None]:
        from src.application.curation.repositories.review_repository import (
            SqlAlchemyReviewRepository,
        )
        from src.application.curation.services.review_service import ReviewService

        repository = SqlAlchemyReviewRepository()
        review_service = ReviewService(repository)

        def submit_review_item(
            entity_type: str,
            entity_id: str,
            research_space_id: str | None,
            priority: str,
        ) -> None:
            try:
                existing = repository.find_by_entity(
                    session,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    research_space_id=research_space_id,
                )
                if existing is not None:
                    existing_status = str(existing.get("status", "")).strip().lower()
                    if existing_status == "pending":
                        return
                review_service.submit(
                    session,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    priority=priority,
                    research_space_id=research_space_id,
                )
            except Exception as exc:  # noqa: BLE001
                with suppress(Exception):
                    session.rollback()
                ApplicationServiceFactoryMixin._logger.warning(
                    "Review queue submit skipped due to repository error: %s",
                    exc,
                )

        return submit_review_item

    @staticmethod
    def _is_stage_enabled(flag_name: str) -> bool:
        return os.getenv(flag_name, "1").strip() == "1"

    def get_entity_recognition_agent(self) -> EntityRecognitionPort:
        if self._entity_recognition_agent is None:
            registry = get_model_registry()
            model_spec = registry.get_default_model(
                ModelCapability.EVIDENCE_EXTRACTION,
            )
            self._entity_recognition_agent = ArtanaEntityRecognitionAdapter(
                model=model_spec.model_id,
                artana_store=self.get_artana_store(),
            )
        return self._entity_recognition_agent

    def get_extraction_agent(self) -> ExtractionAgentPort:
        if self._extraction_agent is None:
            registry = get_model_registry()
            model_spec = registry.get_default_model(
                ModelCapability.EVIDENCE_EXTRACTION,
            )
            self._extraction_agent = ArtanaExtractionAdapter(
                model=model_spec.model_id,
                artana_store=self.get_artana_store(),
            )
        return self._extraction_agent

    def get_mapping_judge_agent(self) -> MappingJudgePort | None:
        if not self._is_stage_enabled("MED13_ENABLE_ENDPOINT_SHAPE_AGENT"):
            return None
        if self._mapping_judge_agent is not None:
            return self._mapping_judge_agent
        registry = get_model_registry()
        model_spec = registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        try:
            self._mapping_judge_agent = ArtanaMappingJudgeAdapter(
                model=model_spec.model_id,
                artana_store=self.get_artana_store(),
            )
        except Exception as exc:  # noqa: BLE001 - fail-closed to deterministic guard
            self._logger.warning(
                "Endpoint-shape mapping judge unavailable, using deterministic guard only: %s",
                exc,
            )
            self._mapping_judge_agent = None
        return self._mapping_judge_agent

    def create_entity_recognition_service(
        self,
        session: Session,
    ) -> EntityRecognitionService:
        dictionary_service = self.create_dictionary_management_service(session)
        concept_service = self.create_concept_management_service(session)
        governance_service = GovernanceService()
        ingestion_pipeline = create_ingestion_pipeline(session)
        registry = get_model_registry()
        model_spec = registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        entity_recognition_agent = ArtanaEntityRecognitionAdapter(
            model=model_spec.model_id,
            dictionary_service=dictionary_service,
            artana_store=self.get_artana_store(),
        )
        extraction_agent = ArtanaExtractionAdapter(
            model=model_spec.model_id,
            dictionary_service=dictionary_service,
            artana_store=self.get_artana_store(),
        )
        extraction_policy_agent = ArtanaExtractionPolicyAdapter(
            model=model_spec.model_id,
            artana_store=self.get_artana_store(),
        )
        evidence_sentence_harness = self._create_evidence_sentence_harness(
            model_id=model_spec.model_id,
        )
        extraction_service = ExtractionService(
            dependencies=ExtractionServiceDependencies(
                extraction_agent=extraction_agent,
                extraction_policy_agent=extraction_policy_agent,
                ingestion_pipeline=ingestion_pipeline,
                relation_repository=SqlAlchemyKernelRelationRepository(session),
                relation_claim_repository=SqlAlchemyKernelRelationClaimRepository(
                    session,
                ),
                claim_participant_repository=(
                    SqlAlchemyKernelClaimParticipantRepository(session)
                ),
                claim_evidence_repository=SqlAlchemyKernelClaimEvidenceRepository(
                    session,
                ),
                entity_repository=SqlAlchemyKernelEntityRepository(session),
                dictionary_service=dictionary_service,
                concept_service=concept_service,
                evidence_sentence_harness=evidence_sentence_harness,
                endpoint_shape_judge=self.get_mapping_judge_agent(),
                governance_service=governance_service,
                review_queue_submitter=self._build_review_queue_submitter(session),
                rollback_on_error=session.rollback,
            ),
        )

        return EntityRecognitionService(
            dependencies=EntityRecognitionServiceDependencies(
                entity_recognition_agent=entity_recognition_agent,
                source_document_repository=SqlAlchemySourceDocumentRepository(session),
                ingestion_pipeline=ingestion_pipeline,
                dictionary_service=dictionary_service,
                extraction_service=extraction_service,
                governance_service=governance_service,
                research_space_repository=SqlAlchemyResearchSpaceRepository(session),
            ),
            default_shadow_mode=False,
        )

    def create_extraction_service(self, session: Session) -> ExtractionService:
        dictionary_service = self.create_dictionary_management_service(session)
        concept_service = self.create_concept_management_service(session)
        registry = get_model_registry()
        model_spec = registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        extraction_agent = ArtanaExtractionAdapter(
            model=model_spec.model_id,
            dictionary_service=dictionary_service,
            artana_store=self.get_artana_store(),
        )
        extraction_policy_agent = ArtanaExtractionPolicyAdapter(
            model=model_spec.model_id,
            artana_store=self.get_artana_store(),
        )
        evidence_sentence_harness = self._create_evidence_sentence_harness(
            model_id=model_spec.model_id,
        )
        return ExtractionService(
            dependencies=ExtractionServiceDependencies(
                extraction_agent=extraction_agent,
                extraction_policy_agent=extraction_policy_agent,
                ingestion_pipeline=create_ingestion_pipeline(session),
                relation_repository=SqlAlchemyKernelRelationRepository(session),
                relation_claim_repository=SqlAlchemyKernelRelationClaimRepository(
                    session,
                ),
                claim_participant_repository=(
                    SqlAlchemyKernelClaimParticipantRepository(session)
                ),
                claim_evidence_repository=SqlAlchemyKernelClaimEvidenceRepository(
                    session,
                ),
                entity_repository=SqlAlchemyKernelEntityRepository(session),
                dictionary_service=dictionary_service,
                concept_service=concept_service,
                evidence_sentence_harness=evidence_sentence_harness,
                endpoint_shape_judge=self.get_mapping_judge_agent(),
                governance_service=GovernanceService(),
                review_queue_submitter=self._build_review_queue_submitter(session),
                rollback_on_error=session.rollback,
            ),
        )

    def _create_evidence_sentence_harness(
        self,
        *,
        model_id: str | None,
    ) -> EvidenceSentenceHarnessPort | None:
        try:
            return ArtanaEvidenceSentenceHarnessAdapter(
                model=model_id,
                artana_store=self.get_artana_store(),
            )
        except Exception as exc:  # noqa: BLE001 - fail-open for optional path
            self._logger.warning(
                "Evidence sentence harness unavailable; optional relation sentence fallback disabled: %s",
                exc,
            )
            return None

    def create_graph_connection_service(
        self,
        session: Session,
    ) -> GraphConnectionService:
        dictionary_service = self.create_dictionary_management_service(session)
        relation_repository = SqlAlchemyKernelRelationRepository(session)
        graph_query_service = SqlAlchemyGraphQueryRepository(session)
        registry = get_model_registry()
        model_spec = registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        graph_connection_agent = ArtanaGraphConnectionAdapter(
            model=model_spec.model_id,
            dictionary_service=dictionary_service,
            graph_query_service=graph_query_service,
            relation_repository=relation_repository,
            artana_store=self.get_artana_store(),
        )
        return GraphConnectionService(
            dependencies=GraphConnectionServiceDependencies(
                graph_connection_agent=graph_connection_agent,
                relation_repository=relation_repository,
                governance_service=GovernanceService(),
                research_space_repository=SqlAlchemyResearchSpaceRepository(session),
                review_queue_submitter=self._build_review_queue_submitter(session),
            ),
        )

    def create_graph_search_service(self, session: Session) -> GraphSearchService:
        from src.application.services.research_query_service import ResearchQueryService

        dictionary_service = self.create_dictionary_management_service(session)
        graph_query_service = SqlAlchemyGraphQueryRepository(session)
        research_query_service = ResearchQueryService(
            dictionary_service=dictionary_service,
        )
        graph_search_agent = None
        if self._is_stage_enabled("MED13_ENABLE_GRAPH_SEARCH_AGENT"):
            registry = get_model_registry()
            model_spec = registry.get_default_model(ModelCapability.QUERY_GENERATION)
            graph_search_agent = ArtanaGraphSearchAdapter(
                model=model_spec.model_id,
                graph_query_service=graph_query_service,
                artana_store=self.get_artana_store(),
            )

        return GraphSearchService(
            dependencies=GraphSearchServiceDependencies(
                research_query_service=research_query_service,
                graph_query_service=graph_query_service,
                graph_search_agent=graph_search_agent,
                governance_service=GovernanceService(),
            ),
        )

    def create_content_enrichment_service(
        self,
        session: Session,
    ) -> ContentEnrichmentService:
        content_enrichment_agent = None
        if self._is_stage_enabled("MED13_ENABLE_CONTENT_ENRICHMENT_AGENT"):
            registry = get_model_registry()
            model_spec = registry.get_default_model(
                ModelCapability.EVIDENCE_EXTRACTION,
            )
            content_enrichment_agent = ArtanaContentEnrichmentAdapter(
                model=model_spec.model_id,
                artana_store=self.get_artana_store(),
            )
        return ContentEnrichmentService(
            dependencies=ContentEnrichmentServiceDependencies(
                source_document_repository=SqlAlchemySourceDocumentRepository(session),
                content_enrichment_agent=content_enrichment_agent,
                storage_coordinator=self.create_storage_operation_coordinator(session),
            ),
        )
