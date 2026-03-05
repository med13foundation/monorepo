"""Integration test for Vector->LLM judge mapper fallback in kernel ingestion."""

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
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.mapping_judge import (
    MappingJudgeCandidate,
    MappingJudgeContract,
)
from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
from src.domain.entities.user import UserRole, UserStatus
from src.domain.ports.dictionary_search_harness_port import DictionarySearchHarnessPort
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


class StubMappingJudgeAgent(MappingJudgePort):
    """Deterministic mapping judge used in integration fallback tests."""

    def judge(
        self,
        context: MappingJudgeContext,
        *,
        model_id: str | None = None,
    ) -> MappingJudgeContract:
        _ = model_id
        chosen = context.candidates[0]
        return MappingJudgeContract(
            decision="matched",
            selected_variable_id=chosen.variable_id,
            candidate_count=len(context.candidates),
            selection_rationale="Selected best fuzzy candidate.",
            selected_candidate=MappingJudgeCandidate(
                variable_id=chosen.variable_id,
                display_name=chosen.display_name,
                match_method=chosen.match_method,
                similarity_score=chosen.similarity_score,
                description=chosen.description,
                metadata=chosen.metadata,
            ),
            confidence_score=0.86,
            rationale="Fuzzy candidate judged semantically aligned.",
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"stub-judge:{context.source_id}:{context.field_key}",
                    excerpt="Stub judge picked first candidate.",
                    relevance=0.8,
                ),
            ],
            agent_run_id="stub-run-1",
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
def test_pipeline_uses_llm_judge_mapper_when_vector_has_no_match(
    postgres_required,
) -> None:
    """Pipeline should map through LLMJudgeMapper when exact/vector are insufficient."""
    assert postgres_required is None

    session = SessionLocal()
    try:
        seed_all(session)

        suffix = uuid4().hex
        slug_suffix = suffix[:16]
        user = UserModel(
            email=f"kernel-judge-{suffix}@example.com",
            username=f"kernel-judge-{suffix}",
            full_name="Kernel LLM Judge Test",
            hashed_password="hashed_password",
            role=UserRole.RESEARCHER,
            status=UserStatus.ACTIVE,
            email_verified=True,
        )
        session.add(user)
        session.flush()

        space = ResearchSpaceModel(
            slug=f"kjudge-{slug_suffix}",
            name="Kernel LLM Judge Space",
            description="Space used for llm-judge ingestion fallback tests",
            owner_id=user.id,
            status="active",
        )
        session.add(space)
        session.flush()

        dictionary_service = DictionaryManagementService(
            dictionary_repo=SqlAlchemyDictionaryRepository(session),
            dictionary_search_harness=StagedDictionarySearchHarness(
                dictionary_repo=SqlAlchemyDictionaryRepository(session),
                embedding_provider=HybridTextEmbeddingProvider(),
            ),
            embedding_provider=HybridTextEmbeddingProvider(),
        )
        dictionary_service.create_variable(
            variable_id="VAR_CARDIOMEGALY_MARKER",
            canonical_name="cardiomegaly_marker",
            display_name="Cardiomegaly Marker",
            data_type="BOOLEAN",
            domain_context="clinical",
            description=None,
            created_by="manual:test",
        )

        pipeline = create_ingestion_pipeline(
            session,
            mapping_judge_agent=StubMappingJudgeAgent(),
            dictionary_search_harness=StagedDictionarySearchHarness(
                dictionary_repo=SqlAlchemyDictionaryRepository(session),
                embedding_provider=HybridTextEmbeddingProvider(),
            ),
        )
        raw_record = RawRecord(
            source_id=str(uuid4()),
            data={
                "cardiomegaly markr": True,
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
                ObservationModel.variable_id == "VAR_CARDIOMEGALY_MARKER",
            ),
        ).scalars()
        persisted = observation.one()
        assert persisted.value_boolean is True
    finally:
        session.close()
