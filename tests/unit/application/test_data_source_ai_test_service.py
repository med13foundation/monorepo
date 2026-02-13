"""Tests for the data source AI test service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from src.application.services.data_source_ai_test_service import (
    DataSourceAiTestDependencies,
    DataSourceAiTestService,
    DataSourceAiTestSettings,
)
from src.domain.agents.contracts.query_generation import QueryGenerationContract
from src.domain.agents.ports.query_agent_port import QueryAgentPort
from src.domain.entities.research_space import ResearchSpace, SpaceStatus
from src.domain.entities.user_data_source import (
    IngestionSchedule,
    QualityMetrics,
    SourceConfiguration,
    SourceStatus,
    SourceType,
    UserDataSource,
)
from src.domain.repositories.research_space_repository import ResearchSpaceRepository
from src.domain.repositories.user_data_source_repository import UserDataSourceRepository
from src.domain.services.pubmed_ingestion import PubMedGateway

if TYPE_CHECKING:
    from uuid import UUID

    from src.domain.entities.data_source_configs import PubMedQueryConfig
    from src.type_definitions.common import (
        RawRecord,
        SourceMetadata,
        StatisticsResponse,
    )


class StubPubMedGateway(PubMedGateway):
    """Stub PubMed gateway returning pre-defined records."""

    def __init__(self, records: list[RawRecord]) -> None:
        self._records = records
        self.called_queries: list[str] = []

    async def fetch_records(self, config: PubMedQueryConfig) -> list[RawRecord]:
        self.called_queries.append(config.query)
        return self._records


class StubQueryAgent(QueryAgentPort):
    """Stub query agent returning a predetermined contract and capturing calls."""

    def __init__(self, query: str, confidence: float = 0.9) -> None:
        self._query = query
        self._confidence = confidence
        self.calls: list[dict[str, object]] = []

    async def generate_query(
        self,
        research_space_description: str,
        user_instructions: str,
        source_type: str,
        *,
        model_id: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
    ) -> QueryGenerationContract:
        self.calls.append(
            {
                "research_space_description": research_space_description,
                "user_instructions": user_instructions,
                "source_type": source_type,
                "model_id": model_id,
            },
        )
        return QueryGenerationContract(
            decision="generated",
            confidence_score=self._confidence,
            rationale="Test query generated successfully",
            evidence=[],
            query=self._query,
            source_type=source_type,
            query_complexity="simple",
        )

    async def close(self) -> None:
        pass


class StubResearchSpaceRepository(ResearchSpaceRepository):
    """Stub research space repository."""

    def __init__(self, space: ResearchSpace | None) -> None:
        self._space = space

    def save(self, space: ResearchSpace) -> ResearchSpace:  # pragma: no cover
        self._space = space
        return space

    def find_by_id(self, space_id: UUID) -> ResearchSpace | None:
        if self._space and self._space.id == space_id:
            return self._space
        return None

    def find_by_slug(self, slug: str) -> ResearchSpace | None:  # pragma: no cover
        return None

    def find_by_owner(  # pragma: no cover
        self,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        return []

    def find_by_status(  # pragma: no cover
        self,
        status: SpaceStatus,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        return []

    def find_active_spaces(  # pragma: no cover
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        return []

    def search_by_name(  # pragma: no cover
        self,
        query: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        return []

    def slug_exists(self, slug: str) -> bool:  # pragma: no cover
        return False

    def delete(self, space_id: UUID) -> bool:  # pragma: no cover
        return False

    def exists(self, space_id: UUID) -> bool:  # pragma: no cover
        return self._space is not None and self._space.id == space_id

    def count_by_owner(self, owner_id: UUID) -> int:  # pragma: no cover
        return 0


class StubUserDataSourceRepository(UserDataSourceRepository):
    """Stub user data source repository."""

    def __init__(self, source: UserDataSource | None) -> None:
        self._source = source

    def save(self, source: UserDataSource) -> UserDataSource:  # pragma: no cover
        self._source = source
        return source

    def find_by_id(self, source_id: UUID) -> UserDataSource | None:
        if self._source and self._source.id == source_id:
            return self._source
        return None

    def find_by_owner(  # pragma: no cover
        self,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        return []

    def find_by_type(  # pragma: no cover
        self,
        source_type: SourceType,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        return []

    def find_by_status(  # pragma: no cover
        self,
        status: SourceStatus,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        return []

    def find_active_sources(  # pragma: no cover
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        return []

    def find_by_tag(  # pragma: no cover
        self,
        tag: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        return []

    def search_by_name(  # pragma: no cover
        self,
        query: str,
        owner_id: UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserDataSource]:
        return []

    def update_status(
        self,
        source_id: UUID,
        status: SourceStatus,
    ) -> UserDataSource | None:  # pragma: no cover
        return None

    def update_quality_metrics(
        self,
        source_id: UUID,
        metrics: QualityMetrics,
    ) -> UserDataSource | None:  # pragma: no cover
        return None

    def update_configuration(
        self,
        source_id: UUID,
        config: SourceConfiguration,
    ) -> UserDataSource | None:  # pragma: no cover
        return None

    def update_ingestion_schedule(
        self,
        source_id: UUID,
        schedule: IngestionSchedule,
    ) -> UserDataSource | None:  # pragma: no cover
        return None

    def record_ingestion(
        self,
        source_id: UUID,
    ) -> UserDataSource | None:  # pragma: no cover
        return None

    def delete(self, source_id: UUID) -> bool:  # pragma: no cover
        return False

    def count_by_owner(self, owner_id: UUID) -> int:  # pragma: no cover
        return 0

    def count_by_status(self, status: SourceStatus) -> int:  # pragma: no cover
        return 0

    def count_by_type(self, source_type: SourceType) -> int:  # pragma: no cover
        return 0

    def exists(self, source_id: UUID) -> bool:  # pragma: no cover
        return self._source is not None and self._source.id == source_id

    def get_statistics(self) -> StatisticsResponse:  # pragma: no cover
        return {}


def build_pubmed_source(
    *,
    source_id: UUID,
    research_space_id: UUID | None,
    ai_enabled: bool,
    source_type: SourceType = SourceType.PUBMED,
    query_agent_source_type: str = "pubmed",
    query: str = "MED13",
    model_id: str | None = None,
) -> UserDataSource:
    metadata: SourceMetadata = {
        "query": query,
        "max_results": 50,
        "agent_config": {
            "is_ai_managed": ai_enabled,
            "agent_prompt": "Focus on MED13 clinical studies.",
            "use_research_space_context": True,
            "query_agent_source_type": query_agent_source_type,
            "model_id": model_id,
        },
    }
    return UserDataSource(
        id=source_id,
        owner_id=uuid4(),
        research_space_id=research_space_id,
        name="Test PubMed",
        description="Test",
        source_type=source_type,
        template_id=None,
        configuration=SourceConfiguration(metadata=metadata),
    )


@pytest.mark.asyncio
async def test_ai_test_success_returns_result() -> None:
    source_id = uuid4()
    space_id = uuid4()
    space = ResearchSpace(
        id=space_id,
        slug="test-space",
        name="Test Space",
        description="Study MED13 variants",
        owner_id=uuid4(),
        status=SpaceStatus.ACTIVE,
    )
    source = build_pubmed_source(
        source_id=source_id,
        research_space_id=space_id,
        ai_enabled=True,
    )

    dependencies = DataSourceAiTestDependencies(
        source_repository=StubUserDataSourceRepository(source),
        pubmed_gateway=StubPubMedGateway(
            [
                {
                    "pubmed_id": "1",
                    "title": "MED13 findings in cardiac research",
                    "doi": "10.1000/xyz",
                    "pmc_id": "PMC12345",
                    "publication_date": "2024-01-01",
                    "journal": {"title": "Nature Medicine"},
                },
            ],
        ),
        query_agent=StubQueryAgent("MED13[Title/Abstract]"),
        run_id_provider=None,
        research_space_repository=StubResearchSpaceRepository(space),
    )
    service = DataSourceAiTestService(
        dependencies,
        settings=DataSourceAiTestSettings(
            sample_size=3,
            ai_model_name="openai:gpt-test",
        ),
    )

    result = await service.test_ai_configuration(source_id)

    assert result.success is True
    assert result.executed_query == "MED13[Title/Abstract]"
    assert result.model == "openai:gpt-test"
    assert "MED13" in result.search_terms
    assert result.fetched_records == 1
    assert result.sample_size == 3
    assert len(result.findings) == 1
    assert result.findings[0].title == "MED13 findings in cardiac research"
    assert any(link.label == "PubMed" for link in result.findings[0].links)


@pytest.mark.asyncio
async def test_ai_test_skips_fetch_for_clinvar_connector() -> None:
    source_id = uuid4()
    space_id = uuid4()
    space = ResearchSpace(
        id=space_id,
        slug="test-space",
        name="Test Space",
        description="Study MED13 variants",
        owner_id=uuid4(),
        status=SpaceStatus.ACTIVE,
    )
    source = build_pubmed_source(
        source_id=source_id,
        research_space_id=space_id,
        source_type=SourceType.API,
        query_agent_source_type="clinvar",
        ai_enabled=True,
    )

    pubmed_gateway = StubPubMedGateway(
        [
            {
                "pubmed_id": "1",
                "title": "MED13 findings in cardiac research",
                "doi": "10.1000/xyz",
                "pmc_id": "PMC12345",
                "publication_date": "2024-01-01",
                "journal": {"title": "Nature Medicine"},
            },
        ],
    )
    query_agent = StubQueryAgent("MED13[Title/Abstract]")
    dependencies = DataSourceAiTestDependencies(
        source_repository=StubUserDataSourceRepository(source),
        pubmed_gateway=pubmed_gateway,
        query_agent=query_agent,
        run_id_provider=None,
        research_space_repository=StubResearchSpaceRepository(space),
    )
    service = DataSourceAiTestService(
        dependencies,
        settings=DataSourceAiTestSettings(
            sample_size=3,
            ai_model_name="openai:gpt-test",
        ),
    )

    result = await service.test_ai_configuration(source_id)

    assert result.success is True
    assert result.executed_query == "MED13[Title/Abstract]"
    assert result.fetched_records == 0
    assert not pubmed_gateway.called_queries
    assert query_agent.calls[0]["source_type"] == "clinvar"
    assert "no connector fetch step for clinvar" in result.message


@pytest.mark.asyncio
async def test_ai_disabled_returns_failure() -> None:
    source_id = uuid4()
    source = build_pubmed_source(
        source_id=source_id,
        research_space_id=None,
        ai_enabled=False,
    )

    dependencies = DataSourceAiTestDependencies(
        source_repository=StubUserDataSourceRepository(source),
        pubmed_gateway=StubPubMedGateway([{"pubmed_id": "1"}]),
        query_agent=StubQueryAgent("MED13"),
        run_id_provider=None,
        research_space_repository=StubResearchSpaceRepository(None),
    )
    service = DataSourceAiTestService(
        dependencies,
        settings=DataSourceAiTestSettings(ai_model_name="openai:gpt-test"),
    )

    result = await service.test_ai_configuration(source_id)

    assert result.success is False
    assert "AI-managed queries are disabled" in result.message
    assert result.findings == []


@pytest.mark.asyncio
async def test_no_results_returns_failure() -> None:
    source_id = uuid4()
    source = build_pubmed_source(
        source_id=source_id,
        research_space_id=None,
        ai_enabled=True,
    )

    dependencies = DataSourceAiTestDependencies(
        source_repository=StubUserDataSourceRepository(source),
        pubmed_gateway=StubPubMedGateway([]),
        query_agent=StubQueryAgent("MED13"),
        run_id_provider=None,
        research_space_repository=StubResearchSpaceRepository(None),
    )
    service = DataSourceAiTestService(
        dependencies,
        settings=DataSourceAiTestSettings(ai_model_name="openai:gpt-test"),
    )

    result = await service.test_ai_configuration(source_id)

    assert result.success is False
    assert "no results" in result.message.lower()
    assert result.findings == []


@pytest.mark.asyncio
async def test_ai_test_passes_model_id_from_agent_config() -> None:
    """Should pass model_id from agent_config to the query agent."""
    source_id = uuid4()
    space_id = uuid4()
    space = ResearchSpace(
        id=space_id,
        slug="test-space",
        name="Test Space",
        description="Study MED13",
        owner_id=uuid4(),
        status=SpaceStatus.ACTIVE,
    )
    # Build source with specific model_id in agent_config
    source = build_pubmed_source(
        source_id=source_id,
        research_space_id=space_id,
        ai_enabled=True,
        model_id="openai:gpt-5",
    )

    query_agent = StubQueryAgent("MED13[Title/Abstract]")

    dependencies = DataSourceAiTestDependencies(
        source_repository=StubUserDataSourceRepository(source),
        pubmed_gateway=StubPubMedGateway(
            [
                {
                    "pubmed_id": "1",
                    "title": "MED13 findings",
                    "doi": "10.1000/xyz",
                    "pmc_id": None,
                    "publication_date": "2024-01-01",
                    "journal": {"title": "Nature"},
                },
            ],
        ),
        query_agent=query_agent,
        run_id_provider=None,
        research_space_repository=StubResearchSpaceRepository(space),
    )
    service = DataSourceAiTestService(
        dependencies,
        settings=DataSourceAiTestSettings(
            sample_size=3,
            ai_model_name="openai:gpt-test",
        ),
    )

    result = await service.test_ai_configuration(source_id)

    # Verify model_id was passed to the query agent
    assert len(query_agent.calls) == 1
    assert query_agent.calls[0]["model_id"] == "openai:gpt-5"
    assert result.success is True


@pytest.mark.asyncio
async def test_result_model_shows_configured_model_id() -> None:
    """Result.model should display the configured model_id, not the default."""
    source_id = uuid4()
    space_id = uuid4()
    space = ResearchSpace(
        id=space_id,
        slug="test-space",
        name="Test Space",
        description="Study MED13",
        owner_id=uuid4(),
        status=SpaceStatus.ACTIVE,
    )
    # Configure a specific model for this source
    configured_model = "openai:gpt-5"
    source = build_pubmed_source(
        source_id=source_id,
        research_space_id=space_id,
        ai_enabled=True,
        model_id=configured_model,
    )

    dependencies = DataSourceAiTestDependencies(
        source_repository=StubUserDataSourceRepository(source),
        pubmed_gateway=StubPubMedGateway(
            [
                {
                    "pubmed_id": "1",
                    "title": "MED13 findings",
                    "doi": "10.1000/xyz",
                    "pmc_id": None,
                    "publication_date": "2024-01-01",
                    "journal": {"title": "Nature"},
                },
            ],
        ),
        query_agent=StubQueryAgent("MED13[Title/Abstract]"),
        run_id_provider=None,
        research_space_repository=StubResearchSpaceRepository(space),
    )
    # Default model is different from configured model
    service = DataSourceAiTestService(
        dependencies,
        settings=DataSourceAiTestSettings(
            sample_size=3,
            ai_model_name="openai:gpt-4o-mini",  # Default model
        ),
    )

    result = await service.test_ai_configuration(source_id)

    # Result should show the configured model, not the default
    assert result.model == configured_model
    assert result.model != "openai:gpt-4o-mini"
    assert result.success is True


@pytest.mark.asyncio
async def test_result_model_falls_back_to_default_when_not_configured() -> None:
    """Result.model should display the default model when no model_id is configured."""
    source_id = uuid4()
    space_id = uuid4()
    space = ResearchSpace(
        id=space_id,
        slug="test-space",
        name="Test Space",
        description="Study MED13",
        owner_id=uuid4(),
        status=SpaceStatus.ACTIVE,
    )
    # No model_id configured (None)
    source = build_pubmed_source(
        source_id=source_id,
        research_space_id=space_id,
        ai_enabled=True,
        model_id=None,
    )

    dependencies = DataSourceAiTestDependencies(
        source_repository=StubUserDataSourceRepository(source),
        pubmed_gateway=StubPubMedGateway(
            [
                {
                    "pubmed_id": "1",
                    "title": "MED13 findings",
                    "doi": "10.1000/xyz",
                    "pmc_id": None,
                    "publication_date": "2024-01-01",
                    "journal": {"title": "Nature"},
                },
            ],
        ),
        query_agent=StubQueryAgent("MED13[Title/Abstract]"),
        run_id_provider=None,
        research_space_repository=StubResearchSpaceRepository(space),
    )
    default_model = "openai:gpt-4o-mini"
    service = DataSourceAiTestService(
        dependencies,
        settings=DataSourceAiTestSettings(
            sample_size=3,
            ai_model_name=default_model,
        ),
    )

    result = await service.test_ai_configuration(source_id)

    # Result should show the default model
    assert result.model == default_model
    assert result.success is True


@pytest.mark.asyncio
async def test_ai_test_passes_none_model_id_when_not_configured() -> None:
    """Should pass None model_id when not configured in agent_config."""
    source_id = uuid4()
    space_id = uuid4()
    space = ResearchSpace(
        id=space_id,
        slug="test-space",
        name="Test Space",
        description="Study MED13",
        owner_id=uuid4(),
        status=SpaceStatus.ACTIVE,
    )
    # Build source without model_id (default None)
    source = build_pubmed_source(
        source_id=source_id,
        research_space_id=space_id,
        ai_enabled=True,
    )

    query_agent = StubQueryAgent("MED13[Title/Abstract]")

    dependencies = DataSourceAiTestDependencies(
        source_repository=StubUserDataSourceRepository(source),
        pubmed_gateway=StubPubMedGateway(
            [
                {
                    "pubmed_id": "1",
                    "title": "MED13 findings",
                    "doi": None,
                    "pmc_id": None,
                    "publication_date": "2024-01-01",
                    "journal": {"title": "Nature"},
                },
            ],
        ),
        query_agent=query_agent,
        run_id_provider=None,
        research_space_repository=StubResearchSpaceRepository(space),
    )
    service = DataSourceAiTestService(
        dependencies,
        settings=DataSourceAiTestSettings(
            sample_size=3,
            ai_model_name="openai:gpt-test",
        ),
    )

    result = await service.test_ai_configuration(source_id)

    # Verify model_id was None (system default)
    assert len(query_agent.calls) == 1
    assert query_agent.calls[0]["model_id"] is None
    assert result.success is True


@pytest.mark.asyncio
async def test_result_model_is_none_when_no_query_agent() -> None:
    """Result.model should be None when query agent is not available."""
    source_id = uuid4()
    source = build_pubmed_source(
        source_id=source_id,
        research_space_id=None,
        ai_enabled=True,
        model_id="openai:gpt-5",
    )

    dependencies = DataSourceAiTestDependencies(
        source_repository=StubUserDataSourceRepository(source),
        pubmed_gateway=StubPubMedGateway([]),
        query_agent=None,  # No query agent available
        run_id_provider=None,
        research_space_repository=StubResearchSpaceRepository(None),
    )
    service = DataSourceAiTestService(
        dependencies,
        settings=DataSourceAiTestSettings(
            sample_size=3,
            ai_model_name="openai:gpt-4o-mini",
        ),
    )

    result = await service.test_ai_configuration(source_id)

    # Model should be None when no query agent
    assert result.model is None
    assert result.success is False
    assert "AI agent is not configured" in result.message
