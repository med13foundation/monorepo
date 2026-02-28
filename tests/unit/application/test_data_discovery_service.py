"""
Unit tests for DataDiscoveryService application service.

Following type safety patterns with mock repositories and
comprehensive business logic testing.
"""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from src.application.services.data_discovery_service import (
    DataDiscoveryService,
    DataDiscoveryServiceDependencies,
)
from src.application.services.data_discovery_service.requests import (
    AddSourceToSpaceRequest,
    CreateDataDiscoverySessionRequest,
    ExecuteQueryTestRequest,
    UpdateSessionParametersRequest,
)
from src.application.services.source_management_service import CreateSourceRequest
from src.domain.entities.data_discovery_parameters import (
    AdvancedQueryParameters,
    CatalogAIProfile,
    CatalogDiscoveryDefaults,
    QueryParameterCapabilities,
    QueryParameterType,
    TestResultStatus,
)
from src.domain.entities.user_data_source import ScheduleFrequency, SourceType
from tests.test_types.data_discovery_fixtures import (
    TEST_SESSION_ACTIVE,
    TEST_SOURCE_CLINVAR,
    create_test_data_discovery_session,
    create_test_source_catalog_entry,
)
from tests.test_types.mocks import (
    create_mock_data_discovery_repositories,
    create_mock_query_client,
)


class TestDataDiscoveryService:
    """Test DataDiscoveryService application service."""

    @pytest.fixture
    def service(self) -> DataDiscoveryService:
        """Create a data discovery service with mock dependencies."""
        mock_repos = create_mock_data_discovery_repositories()
        mock_client = create_mock_query_client()
        return DataDiscoveryService(
            data_discovery_session_repository=mock_repos["session_repo"],
            source_catalog_repository=mock_repos["catalog_repo"],
            query_result_repository=mock_repos["query_repo"],
            source_query_client=mock_client,
            source_management_service=Mock(),
            dependencies=DataDiscoveryServiceDependencies(),
        )

    def test_create_session(self, service: DataDiscoveryService) -> None:
        """Test creating a new data discovery session."""
        owner_id = uuid4()
        request = CreateDataDiscoverySessionRequest(
            owner_id=owner_id,
            name="Test Session",
            research_space_id=uuid4(),
            initial_parameters=AdvancedQueryParameters(
                gene_symbol="MED13L",
                search_term="atrial septal defect",
            ),
        )

        # Mock the repository save to return the session
        service._session_repo.save.side_effect = lambda s: s

        session = service.create_session(request)

        assert session.owner_id == owner_id
        assert session.name == "Test Session"
        assert session.research_space_id == request.research_space_id
        assert session.current_parameters.gene_symbol == "MED13L"
        assert session.is_active is True

    def test_get_session(self, service: DataDiscoveryService) -> None:
        """Test retrieving a data discovery session."""
        session_id = TEST_SESSION_ACTIVE.id

        # Mock the repository to return our test session
        service._session_repo.find_by_id.return_value = TEST_SESSION_ACTIVE

        result = service.get_session(session_id)

        assert result is not None
        assert result.id == session_id
        service._session_repo.find_by_id.assert_called_once_with(session_id)

    def test_get_session_not_found(self, service: DataDiscoveryService) -> None:
        """Test retrieving a non-existent session."""
        session_id = uuid4()

        # Mock the repository to return None
        service._session_repo.find_by_id.return_value = None

        result = service.get_session(session_id)

        assert result is None

    def test_update_session_parameters(self, service: DataDiscoveryService) -> None:
        """Test updating session parameters."""
        session_id = TEST_SESSION_ACTIVE.id
        new_params = AdvancedQueryParameters(gene_symbol="TP53", search_term="cancer")

        # Mock the repository
        service._session_repo.find_by_id.return_value = TEST_SESSION_ACTIVE
        updated_session = create_test_data_discovery_session(
            id=session_id,
            current_parameters=new_params,
        )
        service._session_repo.save.return_value = updated_session

        request = UpdateSessionParametersRequest(
            session_id=session_id,
            parameters=new_params,
        )

        result = service.update_session_parameters(request)

        assert result is not None
        assert result.current_parameters.gene_symbol == "TP53"
        service._session_repo.save.assert_called_once()

    def test_update_session_parameters_not_found(
        self,
        service: DataDiscoveryService,
    ) -> None:
        """Test updating parameters for non-existent session."""
        session_id = uuid4()
        service._session_repo.find_by_id.return_value = None

        request = UpdateSessionParametersRequest(
            session_id=session_id,
            parameters=AdvancedQueryParameters(),
        )

        result = service.update_session_parameters(request)

        assert result is None

    def test_toggle_source_selection(self, service: DataDiscoveryService) -> None:
        """Test toggling source selection."""
        session_id = TEST_SESSION_ACTIVE.id

        # Mock the repository
        service._session_repo.find_by_id.return_value = TEST_SESSION_ACTIVE
        service._catalog_repo.find_by_id.return_value = TEST_SOURCE_CLINVAR
        updated_session = create_test_data_discovery_session(
            id=session_id,
            selected_sources=["clinvar"],  # Added clinvar
        )
        service._session_repo.save.return_value = updated_session

        result = service.toggle_source_selection(session_id, "clinvar")

        assert result is not None
        assert "clinvar" in result.selected_sources
        service._session_repo.save.assert_called_once()

    def test_set_source_selection_filters_invalid_sources(
        self,
        service: DataDiscoveryService,
    ) -> None:
        """Test setting selections filters out invalid catalog entries."""
        session_id = TEST_SESSION_ACTIVE.id
        service._session_repo.find_by_id.return_value = TEST_SESSION_ACTIVE
        service._catalog_repo.find_by_id.side_effect = lambda source_id: (
            TEST_SOURCE_CLINVAR if source_id == "clinvar" else None
        )
        updated_session = create_test_data_discovery_session(
            id=session_id,
            selected_sources=["clinvar"],
        )
        service._session_repo.save.return_value = updated_session

        result = service.set_source_selection(session_id, ["clinvar", "missing"])

        assert result is not None
        assert result.selected_sources == ["clinvar"]

    def test_set_source_selection_session_missing(
        self,
        service: DataDiscoveryService,
    ) -> None:
        """Test attempting to set selections for a missing session."""
        session_id = uuid4()
        service._session_repo.find_by_id.return_value = None

        result = service.set_source_selection(session_id, ["clinvar"])

        assert result is None

    def test_get_source_catalog(self, service: DataDiscoveryService) -> None:
        """Test retrieving source catalog."""
        # Mock the repository
        service._catalog_repo.find_all_active.return_value = [TEST_SOURCE_CLINVAR]

        result = service.get_source_catalog()

        assert len(result) == 1
        assert result[0].id == TEST_SOURCE_CLINVAR.id
        service._catalog_repo.find_all_active.assert_called_once()

    def test_get_source_catalog_filtered(self, service: DataDiscoveryService) -> None:
        """Test retrieving filtered source catalog."""
        # Mock the repository
        service._catalog_repo.search.return_value = [TEST_SOURCE_CLINVAR]

        result = service.get_source_catalog(
            category="Genomic Variant Databases",
            search_query="clinvar",
        )

        assert len(result) == 1
        service._catalog_repo.search.assert_called_once_with(
            "clinvar",
            "Genomic Variant Databases",
        )

    async def test_execute_query_test_success(
        self,
        service: DataDiscoveryService,
    ) -> None:
        """Test executing a successful query test."""
        session_id = TEST_SESSION_ACTIVE.id

        # Mock dependencies
        service._session_repo.find_by_id.return_value = TEST_SESSION_ACTIVE
        service._catalog_repo.find_by_id.return_value = TEST_SOURCE_CLINVAR

        # Mock successful URL generation (for gene-type sources)
        service._query_client.validate_parameters.return_value = True
        service._query_client.generate_url.return_value = (
            "https://example.com/generated-url"
        )

        # Mock repository saves
        mock_result = Mock()
        mock_result.is_successful.return_value = True
        service._query_repo.save.return_value = mock_result

        request = ExecuteQueryTestRequest(
            session_id=session_id,
            catalog_entry_id=TEST_SOURCE_CLINVAR.id,
        )

        result = await service.execute_query_test(request)

        assert result is not None
        service._query_client.generate_url.assert_called_once()
        service._query_repo.save.assert_called_once()

    async def test_execute_query_test_validation_failure(
        self,
        service: DataDiscoveryService,
    ) -> None:
        """Test query test with parameter validation failure."""
        session_id = TEST_SESSION_ACTIVE.id

        # Mock dependencies
        service._session_repo.find_by_id.return_value = TEST_SESSION_ACTIVE
        service._catalog_repo.find_by_id.return_value = TEST_SOURCE_CLINVAR

        # Mock validation failure
        service._query_client.validate_parameters.return_value = False

        # Mock repository save to return a proper result
        mock_result = Mock()
        mock_result.status = TestResultStatus.VALIDATION_FAILED
        service._query_repo.save.return_value = mock_result

        request = ExecuteQueryTestRequest(
            session_id=session_id,
            catalog_entry_id=TEST_SOURCE_CLINVAR.id,
        )

        result = await service.execute_query_test(request)

        assert result is not None
        assert result.status == TestResultStatus.VALIDATION_FAILED
        service._query_client.execute_query.assert_not_called()

    async def test_execute_query_test_session_not_found(
        self,
        service: DataDiscoveryService,
    ) -> None:
        """Test query test with non-existent session."""
        session_id = uuid4()

        # Mock session not found
        service._session_repo.find_by_id.return_value = None

        request = ExecuteQueryTestRequest(
            session_id=session_id,
            catalog_entry_id="test-source",
        )

        result = await service.execute_query_test(request)

        assert result is None

    def test_toggle_source_selection_missing_catalog(
        self,
        service: DataDiscoveryService,
    ) -> None:
        """Selection toggle should noop when catalog entry not found."""
        session_id = TEST_SESSION_ACTIVE.id
        service._session_repo.find_by_id.return_value = TEST_SESSION_ACTIVE
        service._catalog_repo.find_by_id.return_value = None

        result = service.toggle_source_selection(session_id, "missing-entry")

        assert result is None
        service._session_repo.save.assert_not_called()

    def test_toggle_source_selection_allows_missing_parameters(
        self,
        service: DataDiscoveryService,
    ) -> None:
        """Selection toggle should proceed even when required parameters are missing."""
        session_id = TEST_SESSION_ACTIVE.id
        session_without_params = create_test_data_discovery_session(
            id=session_id,
            current_parameters=AdvancedQueryParameters(
                gene_symbol=None,
                search_term=None,
            ),
        )
        service._session_repo.find_by_id.return_value = session_without_params
        source_requires_gene = TEST_SOURCE_CLINVAR.model_copy()
        service._catalog_repo.find_by_id.return_value = source_requires_gene
        updated_session = create_test_data_discovery_session(
            id=session_id,
            selected_sources=[source_requires_gene.id],
        )
        service._session_repo.save.return_value = updated_session

        result = service.toggle_source_selection(session_id, source_requires_gene.id)

        assert result is not None
        assert source_requires_gene.id in result.selected_sources
        service._session_repo.save.assert_called_once()

    def test_toggle_source_selection_allows_paramless_sources(
        self,
        service: DataDiscoveryService,
    ) -> None:
        """Ensure sources that require no parameters can be toggled without data."""
        session_id = TEST_SESSION_ACTIVE.id
        session_without_params = create_test_data_discovery_session(
            id=session_id,
            current_parameters=AdvancedQueryParameters(
                gene_symbol=None,
                search_term=None,
            ),
        )
        service._session_repo.find_by_id.return_value = session_without_params
        source_paramless = TEST_SOURCE_CLINVAR.model_copy(
            update={"param_type": QueryParameterType.NONE},
        )
        service._catalog_repo.find_by_id.return_value = source_paramless
        updated_session = create_test_data_discovery_session(
            id=session_id,
            selected_sources=[source_paramless.id],
        )
        service._session_repo.save.return_value = updated_session

        result = service.toggle_source_selection(session_id, source_paramless.id)

        assert result is not None
        assert source_paramless.id in result.selected_sources

    def test_get_session_test_results(self, service: DataDiscoveryService) -> None:
        """Test retrieving session test results."""
        session_id = TEST_SESSION_ACTIVE.id
        mock_results = [Mock()]

        # Mock the repository
        service._query_repo.find_by_session.return_value = mock_results

        result = service.get_session_test_results(session_id)

        assert result == mock_results
        service._query_repo.find_by_session.assert_called_once_with(session_id)

    async def test_add_source_to_space(self, service: DataDiscoveryService) -> None:
        """Test adding a source to a research space."""
        session_id = TEST_SESSION_ACTIVE.id
        space_id = uuid4()

        # Create a catalog entry without template to avoid template lookup
        catalog_entry_no_template = create_test_source_catalog_entry(
            entry_id=TEST_SOURCE_CLINVAR.id,
            source_template_id=None,  # No template, will use SourceType.API default
        )

        # Mock dependencies
        service._session_repo.find_by_id.return_value = TEST_SESSION_ACTIVE
        service._catalog_repo.find_by_id.return_value = catalog_entry_no_template

        # Mock source management service
        mock_data_source = Mock()
        mock_data_source.id = uuid4()
        service._source_service.create_source.return_value = mock_data_source

        request = AddSourceToSpaceRequest(
            session_id=session_id,
            catalog_entry_id=catalog_entry_no_template.id,
            research_space_id=space_id,
        )

        result = await service.add_source_to_space(request)

        assert result == mock_data_source.id
        service._source_service.create_source.assert_called_once()

    async def test_add_source_to_space_applies_api_defaults(
        self,
        service: DataDiscoveryService,
    ) -> None:
        """Catalog API entries should receive defaults when no config is provided."""
        session_id = TEST_SESSION_ACTIVE.id
        space_id = uuid4()
        catalog_entry_api = create_test_source_catalog_entry(
            entry_id="clinvar-api",
            source_type=SourceType.API,
            source_template_id=None,
            api_endpoint="https://api.ncbi.nlm.nih.gov/clinvar/v1",
            url_template=None,
        )

        service._session_repo.find_by_id.return_value = TEST_SESSION_ACTIVE
        service._catalog_repo.find_by_id.return_value = catalog_entry_api

        mock_data_source = Mock()
        mock_data_source.id = uuid4()

        def _create_source_side_effect(create_request: CreateSourceRequest) -> Mock:
            configuration = create_request.configuration
            source_type = create_request.source_type

            assert source_type == SourceType.API
            assert configuration.url == "https://api.ncbi.nlm.nih.gov/clinvar/v1"
            assert configuration.requests_per_minute == 10
            assert configuration.metadata.get("catalog_entry_id") == "clinvar-api"
            return mock_data_source

        service._source_service.create_source.side_effect = _create_source_side_effect

        request = AddSourceToSpaceRequest(
            session_id=session_id,
            catalog_entry_id=catalog_entry_api.id,
            research_space_id=space_id,
            source_config={},
        )

        result = await service.add_source_to_space(request)

        assert result == mock_data_source.id
        service._source_service.create_source.assert_called_once()

    async def test_add_source_to_space_applies_discovery_defaults_and_schedule(
        self,
        service: DataDiscoveryService,
    ) -> None:
        """Discovery defaults should hydrate AI config and ingestion schedule."""
        session_id = TEST_SESSION_ACTIVE.id
        space_id = uuid4()
        catalog_entry_benchmark = create_test_source_catalog_entry(
            entry_id="clinvar_benchmark",
            name="ClinVar Pathogenicity Benchmark",
            category="AI / ML Benchmark Datasets",
            param_type="none",
            source_type=SourceType.API,
            source_template_id=None,
            api_endpoint="https://github.com/genomicsAI/clinvar-benchmark",
            url_template="https://github.com/genomicsAI/clinvar-benchmark",
            capabilities=QueryParameterCapabilities(
                discovery_defaults=CatalogDiscoveryDefaults(
                    schedule_enabled=True,
                    schedule_frequency="daily",
                    schedule_timezone="UTC",
                    ai_profile=CatalogAIProfile(
                        is_ai_managed=True,
                        source_type="clinvar",
                        agent_prompt=(
                            "Use ClinVar-specific ontology and evidence criteria "
                            "for pathogenicity-focused queries."
                        ),
                        use_research_space_context=True,
                        default_query="MED13 pathogenic variant",
                    ),
                ),
            ),
        )

        service._session_repo.find_by_id.return_value = TEST_SESSION_ACTIVE
        service._catalog_repo.find_by_id.return_value = catalog_entry_benchmark

        mock_data_source = Mock()
        mock_data_source.id = uuid4()

        def _create_source_side_effect(create_request: CreateSourceRequest) -> Mock:
            metadata = create_request.configuration.metadata
            assert metadata.get("query") == "MED13 pathogenic variant"
            agent_config = metadata.get("agent_config")
            assert isinstance(agent_config, dict)
            assert agent_config.get("is_ai_managed") is True
            assert agent_config.get("query_agent_source_type") == "clinvar"
            assert create_request.ingestion_schedule is not None
            assert create_request.ingestion_schedule.enabled is True
            assert (
                create_request.ingestion_schedule.frequency == ScheduleFrequency.DAILY
            )
            assert create_request.ingestion_schedule.timezone == "UTC"
            return mock_data_source

        service._source_service.create_source.side_effect = _create_source_side_effect

        request = AddSourceToSpaceRequest(
            session_id=session_id,
            catalog_entry_id=catalog_entry_benchmark.id,
            research_space_id=space_id,
            source_config={},
        )

        result = await service.add_source_to_space(request)

        assert result == mock_data_source.id
        service._source_service.create_source.assert_called_once()

    async def test_add_source_to_space_applies_clinvar_defaults(
        self,
        service: DataDiscoveryService,
    ) -> None:
        """ClinVar entries should create ClinVar sources with metadata defaults."""
        session_id = TEST_SESSION_ACTIVE.id
        space_id = uuid4()
        catalog_entry_clinvar = create_test_source_catalog_entry(
            entry_id="clinvar",
            name="ClinVar",
            category="Genomic Variant Databases",
            param_type="gene",
            source_type=SourceType.CLINVAR,
            source_template_id=None,
            api_endpoint="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
            url_template="https://www.ncbi.nlm.nih.gov/clinvar/?term=${gene}[gene]",
        )

        service._session_repo.find_by_id.return_value = TEST_SESSION_ACTIVE
        service._catalog_repo.find_by_id.return_value = catalog_entry_clinvar

        mock_data_source = Mock()
        mock_data_source.id = uuid4()

        def _create_source_side_effect(create_request: CreateSourceRequest) -> Mock:
            metadata = create_request.configuration.metadata
            assert create_request.source_type == SourceType.CLINVAR
            assert metadata.get("gene_symbol") == "MED13L"
            assert isinstance(metadata.get("query"), str)
            assert create_request.configuration.requests_per_minute == 10
            return mock_data_source

        service._source_service.create_source.side_effect = _create_source_side_effect

        request = AddSourceToSpaceRequest(
            session_id=session_id,
            catalog_entry_id="clinvar",
            research_space_id=space_id,
            source_config={},
        )

        result = await service.add_source_to_space(request)

        assert result == mock_data_source.id
        service._source_service.create_source.assert_called_once()

    async def test_add_source_to_space_coerces_legacy_pubmed_source_type(
        self,
        service: DataDiscoveryService,
    ) -> None:
        """PubMed entries mislabeled as API should still create PubMed sources."""
        session_id = TEST_SESSION_ACTIVE.id
        space_id = uuid4()
        catalog_entry_pubmed = create_test_source_catalog_entry(
            entry_id="pubmed",
            name="PubMed",
            category="Scientific Literature",
            param_type="gene_and_term",
            source_type=SourceType.API,
            source_template_id=None,
            api_endpoint=None,
            url_template="https://pubmed.ncbi.nlm.nih.gov/?term=${gene}+${term}",
        )

        service._session_repo.find_by_id.return_value = TEST_SESSION_ACTIVE
        service._catalog_repo.find_by_id.return_value = catalog_entry_pubmed

        mock_data_source = Mock()
        mock_data_source.id = uuid4()

        def _create_source_side_effect(create_request: CreateSourceRequest) -> Mock:
            configuration = create_request.configuration
            source_type = create_request.source_type

            assert source_type == SourceType.PUBMED
            assert isinstance(configuration.metadata.get("query"), str)
            assert configuration.metadata.get("domain_context") == "clinical"
            return mock_data_source

        service._source_service.create_source.side_effect = _create_source_side_effect

        request = AddSourceToSpaceRequest(
            session_id=session_id,
            catalog_entry_id="pubmed",
            research_space_id=space_id,
            source_config={},
        )

        result = await service.add_source_to_space(request)

        assert result == mock_data_source.id
        service._source_service.create_source.assert_called_once()

    def test_delete_session(self, service: DataDiscoveryService) -> None:
        """Test deleting a workbench session."""
        session_id = TEST_SESSION_ACTIVE.id

        # Mock successful deletion
        service._session_repo.delete.return_value = True
        service._query_repo.delete_session_results.return_value = 5

        result = service.delete_session(session_id)

        assert result is True
        service._session_repo.delete.assert_called_once_with(session_id)
        service._query_repo.delete_session_results.assert_called_once_with(session_id)

    def test_delete_session_not_found(self, service: DataDiscoveryService) -> None:
        """Test deleting a non-existent session."""
        session_id = uuid4()

        # Mock deletion failure
        service._session_repo.delete.return_value = False

        result = service.delete_session(session_id)

        assert result is False
