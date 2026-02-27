"""
Typed mock implementations for MED13 Resource Library testing.

Provides type-safe mock repositories and services for comprehensive unit testing.
"""

from typing import TypedDict
from unittest.mock import MagicMock
from uuid import UUID

from src.application.services.data_discovery_service import DataDiscoveryService
from src.application.services.space_data_discovery_service import (
    SpaceDataDiscoveryService,
)
from src.domain.entities.data_discovery_session import (
    DataDiscoverySession,
    SourceCatalogEntry,
)
from src.domain.entities.discovery_preset import DiscoveryPreset
from src.domain.entities.publication import Publication
from src.domain.repositories.publication_repository import PublicationRepository
from src.type_definitions.common import (
    JSONObject,
    PublicationUpdate,
)

from .fixtures import (
    TestPublication,
    create_test_space_discovery_session,
)


def create_mock_space_discovery_service(
    space_id: UUID,
    *,
    sessions: list[DataDiscoverySession] | None = None,
    catalog_entries: list[SourceCatalogEntry] | None = None,
    presets: list[DiscoveryPreset] | None = None,
) -> tuple[SpaceDataDiscoveryService, MagicMock]:
    """
    Create a space discovery service backed by a mocked DataDiscoveryService.

    Args:
        space_id: Scoped research space identifier
        sessions: Optional list of seeded sessions
        catalog_entries: Optional list of catalog entries returned by get_catalog

    Returns:
        Tuple of (SpaceDataDiscoveryService, underlying mock DataDiscoveryService)
    """
    base_service = MagicMock(spec=DataDiscoveryService)
    seeded_sessions = sessions or []

    base_service.get_source_catalog.return_value = catalog_entries or []
    base_service.get_sessions_for_space.return_value = seeded_sessions

    def _find_session(session_id: UUID) -> DataDiscoverySession | None:
        for session in seeded_sessions:
            if session.id == session_id:
                return session
        return None

    def _find_owned(session_id: UUID, owner_id: UUID) -> DataDiscoverySession | None:
        for session in seeded_sessions:
            if session.id == session_id and session.owner_id == owner_id:
                return session
        return None

    base_service.get_session.side_effect = _find_session
    base_service.get_session_for_owner.side_effect = _find_owned

    def _create_session(request):
        session = create_test_space_discovery_session(
            space_id,
            owner_id=request.owner_id,
            name=request.name,
        )
        seeded_sessions.append(session)
        return session

    base_service.create_session.side_effect = _create_session
    base_service.update_session_parameters.return_value = None
    base_service.toggle_source_selection.return_value = None
    base_service.set_source_selection.return_value = None
    base_service.delete_session.return_value = True

    config_service = MagicMock()
    config_service.list_pubmed_presets.return_value = presets or []

    service = SpaceDataDiscoveryService(space_id, base_service, config_service)
    service._config_service_mock = config_service  # test hook
    return service, base_service


class MockPublicationRepository(PublicationRepository):
    """Type-safe mock publication repository for testing."""

    def __init__(self, publications: list[TestPublication] | None = None):
        """
        Initialize mock repository with test data.

        Args:
            publications: List of test publications to populate repository
        """
        self._publications: dict[int, TestPublication] = {}
        self._id_counter = 1

        if publications:
            for publication in publications:
                self._publications[self._id_counter] = publication
                self._id_counter += 1

        # Mock methods for tracking calls
        self.save_publication = MagicMock()
        self.get_publication_by_id = MagicMock()
        self.list_publications = MagicMock()
        self.update_publication = MagicMock()
        self.delete_publication = MagicMock()

    def save(self, publication: Publication) -> Publication:
        """Mock save method."""
        self.save_publication(publication)
        return publication

    def get_by_id(self, publication_id: int) -> Publication | None:
        """Mock get by ID method."""
        self.get_publication_by_id(publication_id)
        if publication_id in self._publications:
            test_publication = self._publications[publication_id]
            return Publication(
                title=test_publication.title,
                authors=test_publication.authors,
                journal=test_publication.journal,
                publication_year=test_publication.publication_year,
                doi=test_publication.doi,
                pmid=test_publication.pmid,
                abstract=test_publication.abstract,
            )
        return None

    def list_all(self) -> list[Publication]:
        """Mock list all method."""
        self.list_publications()
        return [
            Publication(
                title=test_publication.title,
                authors=test_publication.authors,
                journal=test_publication.journal,
                publication_year=test_publication.publication_year,
                doi=test_publication.doi,
                pmid=test_publication.pmid,
                abstract=test_publication.abstract,
            )
            for test_publication in self._publications.values()
        ]

    def update(self, publication_id: int, updates: PublicationUpdate) -> Publication:
        """Mock update method."""
        self.update_publication(publication_id, updates)
        if publication_id in self._publications:
            test_publication = self._publications[publication_id]
            return Publication(
                title=updates.get("title", test_publication.title),
                authors=updates.get("authors", test_publication.authors),
                journal=updates.get("journal", test_publication.journal),
                publication_year=updates.get(
                    "publication_year",
                    test_publication.publication_year,
                ),
                doi=updates.get("doi", test_publication.doi),
                pmid=updates.get("pmid", test_publication.pmid),
                abstract=updates.get("abstract", test_publication.abstract),
            )
        raise ValueError(f"Publication {publication_id} not found")

    def delete(self, publication_id: int) -> None:
        """Mock delete method."""
        self.delete_publication(publication_id)
        if publication_id in self._publications:
            del self._publications[publication_id]

    def find_recent_publications(self, days: int = 30) -> list[Publication]:
        """Return recent publications (mocked as entire dataset)."""
        return self.list_all()

    def find_med13_relevant(
        self,
        min_relevance: int = 3,
        limit: int | None = None,
    ) -> list[Publication]:
        """Return MED13-relevant publications (mocked subset)."""
        publications = self.list_all()
        if limit is not None:
            publications = publications[:limit]
        return publications


# Factory functions for creating mock services


# Data Discovery mock repositories and services
class MockDataDiscoverySessionRepository:
    """Mock data discovery session repository for testing."""

    def __init__(self):
        self.sessions = {}
        self.save = MagicMock()
        self.find_by_id = MagicMock()
        self.find_by_owner = MagicMock(return_value=[])
        self.find_by_space = MagicMock(return_value=[])
        self.delete = MagicMock(return_value=True)

    def setup_default_behavior(self):
        """Set up default mock behaviors."""
        self.save.side_effect = lambda session: session
        self.find_by_id.side_effect = lambda session_id: self.sessions.get(session_id)
        self.find_by_owner.return_value = list(self.sessions.values())
        self.find_by_space.return_value = list(self.sessions.values())


class MockSourceCatalogRepository:
    """Mock source catalog repository for testing."""

    def __init__(self):
        self.entries = {}
        self.save = MagicMock()
        self.find_by_id = MagicMock()
        self.find_all_active = MagicMock(return_value=[])
        self.find_by_category = MagicMock(return_value=[])
        self.search = MagicMock(return_value=[])
        self.update_usage_stats = MagicMock(return_value=True)

    def setup_default_behavior(self):
        """Set up default mock behaviors."""
        self.save.side_effect = lambda entry: entry
        self.find_by_id.side_effect = lambda entry_id: self.entries.get(entry_id)


class MockQueryTestResultRepository:
    """Mock query test result repository for testing."""

    def __init__(self):
        self.results = {}
        self.save = MagicMock()
        self.find_by_session = MagicMock(return_value=[])
        self.find_by_source = MagicMock(return_value=[])
        self.find_by_id = MagicMock()
        self.delete_session_results = MagicMock(return_value=0)

    def setup_default_behavior(self):
        """Set up default mock behaviors."""
        self.save.side_effect = lambda result: result
        self.find_by_id.side_effect = lambda result_id: self.results.get(result_id)


class MockSourceQueryClient:
    """Mock source query client for testing."""

    def __init__(self):
        self.execute_query = MagicMock()
        self.generate_url = MagicMock()
        self.validate_parameters = MagicMock(return_value=True)

    def setup_success_behavior(self, response_data: JSONObject | None = None):
        """Set up successful query behavior."""
        self.execute_query.return_value = response_data or {"result": "success"}
        self.generate_url.return_value = "https://example.com/test"
        self.validate_parameters.return_value = True

    def setup_failure_behavior(self, error_message: str = "Query failed"):
        """Set up failed query behavior."""
        from src.infrastructure.queries.source_query_client import QueryExecutionError

        self.execute_query.side_effect = QueryExecutionError(
            error_message,
            "test-source",
        )
        self.validate_parameters.return_value = False


class DataDiscoveryRepositoryMocks(TypedDict):
    """Typed mapping for mock data discovery repositories."""

    session_repo: MockDataDiscoverySessionRepository
    catalog_repo: MockSourceCatalogRepository
    query_repo: MockQueryTestResultRepository
    search_job_repo: "MockDiscoverySearchJobRepository"


class MockDiscoverySearchJobRepository:
    """Mock repository for discovery search jobs."""

    def __init__(self):
        self.jobs: dict[UUID, object] = {}
        self.create = MagicMock(side_effect=self._store_job)
        self.update = MagicMock(side_effect=self._store_job)
        self.get = MagicMock(side_effect=self.jobs.get)
        self.list_for_owner = MagicMock(return_value=[])
        self.list_for_session = MagicMock(return_value=[])

    def _store_job(self, job):
        self.jobs[job.id] = job
        return job


def create_mock_data_discovery_repositories() -> DataDiscoveryRepositoryMocks:
    """
    Create a set of mock data discovery repositories for testing.

    Returns:
        Dictionary containing mock repositories
    """
    session_repo = MockDataDiscoverySessionRepository()
    catalog_repo = MockSourceCatalogRepository()
    query_repo = MockQueryTestResultRepository()
    search_job_repo = MockDiscoverySearchJobRepository()

    # Don't set up default behaviors - let individual tests configure mocks as needed
    # This allows tests to have full control over mock behavior

    return {
        "session_repo": session_repo,
        "catalog_repo": catalog_repo,
        "query_repo": query_repo,
        "search_job_repo": search_job_repo,
    }


def create_mock_query_client() -> MockSourceQueryClient:
    """
    Create a mock source query client for testing.

    Returns:
        Mock query client with success behavior
    """
    client = MockSourceQueryClient()
    client.setup_success_behavior()
    return client
