"""Integration test for Exact->Vector mapper fallback in kernel ingestion."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.application.services.kernel.dictionary_management_service import (
    DictionaryManagementService,
)
from src.database.seeds.seeder import seed_all
from src.database.session import SessionLocal
from src.domain.agents.contracts.mapping_judge import MappingJudgeContract
from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
from src.domain.entities.user import UserRole, UserStatus
from src.domain.ports.dictionary_search_harness_port import DictionarySearchHarnessPort
from src.graph.pack_registry import resolve_graph_domain_pack
from src.infrastructure.embeddings import HybridTextEmbeddingProvider
from src.infrastructure.factories.ingestion_pipeline_factory import (
    create_ingestion_pipeline,
)
from src.infrastructure.repositories.kernel import SqlAlchemyDictionaryRepository
from src.models.database.kernel.observations import ObservationModel
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from src.type_definitions.ingestion import RawRecord

if TYPE_CHECKING:
    from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext
    from src.domain.entities.kernel.dictionary import DictionarySearchResult
    from src.domain.ports.text_embedding_port import TextEmbeddingPort


class NoopMappingJudgeAgent(MappingJudgePort):
    """Fail-fast-safe stub that never remaps candidates."""

    def judge(
        self,
        context: MappingJudgeContext,
        *,
        model_id: str | None = None,
    ) -> MappingJudgeContract:
        del model_id
        return MappingJudgeContract(
            decision="no_match",
            selected_variable_id=None,
            candidate_count=len(context.candidates),
            selection_rationale="No mapping change requested.",
            confidence_score=0.0,
            rationale="No mapping change requested.",
            evidence=[],
            agent_run_id="noop-mapping-judge",
        )

    def close(self) -> None:
        return None


class StagedDictionarySearchHarness(DictionarySearchHarnessPort):
    """Direct + vector harness stub for ingestion integration tests."""

    def __init__(
        self,
        *,
        dictionary_repo: SqlAlchemyDictionaryRepository,
        embedding_provider: TextEmbeddingPort,
    ) -> None:
        self._dictionary = dictionary_repo
        self._embedding_provider = embedding_provider

    def search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        direct_results = self._dictionary.search_dictionary(
            terms=terms,
            dimensions=dimensions,
            domain_context=domain_context,
            limit=limit,
            query_embeddings=None,
            include_inactive=include_inactive,
        )
        if any(
            result.match_method in {"exact", "synonym"} for result in direct_results
        ):
            return direct_results
        normalized_terms = [term.strip().casefold() for term in terms if term.strip()]
        embeddings: dict[str, list[float]] = {}
        for index, embedding in enumerate(
            self._embedding_provider.embed_texts(
                normalized_terms,
                model_name="text-embedding-3-small",
            ),
        ):
            if embedding is None:
                continue
            embeddings[normalized_terms[index]] = embedding
        if not embeddings:
            return direct_results
        vector_results = self._dictionary.search_dictionary(
            terms=terms,
            dimensions=dimensions,
            domain_context=domain_context,
            limit=limit,
            query_embeddings=embeddings,
            include_inactive=include_inactive,
        )
        return vector_results if vector_results else direct_results


@pytest.mark.integration
@pytest.mark.database
def test_pipeline_uses_vector_mapper_when_exact_match_is_missing(
    postgres_required,
) -> None:
    """Pipeline should map a semantic key via VectorMapper when ExactMapper misses."""
    assert postgres_required is None

    session = SessionLocal()
    try:
        seed_all(session)

        suffix = uuid4().hex
        slug_suffix = suffix[:16]
        user = UserModel(
            email=f"kernel-vector-{suffix}@example.com",
            username=f"kernel-vector-{suffix}",
            full_name="Kernel Vector Test",
            hashed_password="hashed_password",
            role=UserRole.RESEARCHER,
            status=UserStatus.ACTIVE,
            email_verified=True,
        )
        session.add(user)
        session.flush()

        space = ResearchSpaceModel(
            slug=f"kvector-{slug_suffix}",
            name="Kernel Vector Mapper Space",
            description="Space used for vector-mapper ingestion fallback tests",
            owner_id=user.id,
            status="active",
        )
        session.add(space)
        session.flush()

        dictionary_service = DictionaryManagementService(
            dictionary_repo=SqlAlchemyDictionaryRepository(
                session,
                builtin_domain_contexts=resolve_graph_domain_pack().dictionary_domain_contexts,
            ),
            dictionary_search_harness=StagedDictionarySearchHarness(
                dictionary_repo=SqlAlchemyDictionaryRepository(
                    session,
                    builtin_domain_contexts=resolve_graph_domain_pack().dictionary_domain_contexts,
                ),
                embedding_provider=HybridTextEmbeddingProvider(),
            ),
            embedding_provider=HybridTextEmbeddingProvider(),
        )
        dictionary_service.create_variable(
            variable_id="VAR_ENLARGED_HEART_SIGNAL",
            canonical_name="cardiomegaly_marker",
            display_name="Cardiomegaly Marker",
            data_type="BOOLEAN",
            domain_context="clinical",
            description="enlarged heart",
            created_by="manual:test",
        )

        pipeline = create_ingestion_pipeline(
            session,
            mapping_judge_agent=NoopMappingJudgeAgent(),
            dictionary_search_harness=StagedDictionarySearchHarness(
                dictionary_repo=SqlAlchemyDictionaryRepository(
                    session,
                    builtin_domain_contexts=resolve_graph_domain_pack().dictionary_domain_contexts,
                ),
                embedding_provider=HybridTextEmbeddingProvider(),
            ),
        )
        raw_record = RawRecord(
            source_id=str(uuid4()),
            data={
                "enlarged heart": True,
            },
            metadata={
                "type": "clinvar",
                "entity_type": "PUBLICATION",
                "domain_context": "clinical",
            },
        )

        result = pipeline.run([raw_record], research_space_id=str(space.id))

        assert result.success is True
        assert result.observations_created == 1

        observation = session.execute(
            select(ObservationModel).where(
                ObservationModel.research_space_id == space.id,
                ObservationModel.variable_id == "VAR_ENLARGED_HEART_SIGNAL",
            ),
        ).scalars()
        persisted = observation.one()
        assert persisted.value_boolean is True
    finally:
        session.close()
