"""
Tests for storage integration in application services.

Verifies that:
1. PubMedIngestionService persists raw records when storage is configured.
2. BulkExportService streams exports to storage backends.
3. PubMedDiscoveryService logs observability events.
"""

import pathlib
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from src.application.export.export_service import BulkExportService
from src.application.export.export_types import ExportFormat
from src.application.services.pubmed_discovery_service import (
    PubMedDiscoveryService,
    PubmedDownloadRequest,
    RunPubmedSearchRequest,
)
from src.application.services.pubmed_ingestion_service import PubMedIngestionService
from src.application.services.storage_configuration_service import (
    StorageConfigurationService,
)
from src.domain.entities.data_discovery_parameters import AdvancedQueryParameters
from src.domain.entities.discovery_search_job import DiscoverySearchStatus
from src.domain.entities.storage_configuration import StorageConfiguration
from src.domain.entities.user_data_source import (
    SourceConfiguration,
    SourceType,
    UserDataSource,
)
from src.domain.services.pubmed_ingestion import PubMedGateway
from src.type_definitions.storage import (
    StorageOperationRecord,
    StorageProviderName,
    StorageUseCase,
)


@pytest.fixture
def mock_storage_service() -> Mock:
    service = Mock(spec=StorageConfigurationService)
    # Setup default behavior
    service.resolve_backend_for_use_case.return_value = Mock(spec=StorageConfiguration)
    return service


@pytest.fixture
def mock_storage_backend() -> Mock:
    backend = Mock(spec=StorageConfiguration)
    backend.provider = StorageProviderName.LOCAL_FILESYSTEM
    return backend


@pytest.fixture
def mock_gateway() -> Mock:
    gateway = Mock(spec=PubMedGateway)
    gateway.fetch_records.return_value = [{"pmid": "123", "title": "Test"}]
    return gateway


@pytest.fixture
def mock_repo() -> Mock:
    repo = Mock()
    repo.find_by_pmid.return_value = None
    return repo


class TestPubMedIngestionStorage:
    @pytest.mark.asyncio
    async def test_ingest_persists_raw_records(
        self,
        mock_gateway: Mock,
        mock_repo: Mock,
        mock_storage_service: Mock,
        mock_storage_backend: Mock,
    ) -> None:
        # Arrange
        mock_storage_service.resolve_backend_for_use_case.return_value = (
            mock_storage_backend
        )
        service = PubMedIngestionService(
            gateway=mock_gateway,
            publication_repository=mock_repo,
            storage_service=mock_storage_service,
            pipeline=Mock(),
        )
        source = UserDataSource(
            id=uuid4(),
            owner_id=uuid4(),
            name="Test Source",
            source_type=SourceType.PUBMED,
            configuration=SourceConfiguration(metadata={"query": "test"}),
        )

        # Act
        await service.ingest(source)

        # Assert
        # Verify storage resolution
        mock_storage_service.resolve_backend_for_use_case.assert_called_with(
            StorageUseCase.RAW_SOURCE,
        )
        # Verify record operation
        mock_storage_service.record_store_operation.assert_called_once()
        call_kwargs = mock_storage_service.record_store_operation.call_args.kwargs
        assert call_kwargs["configuration"] == mock_storage_backend
        assert call_kwargs["key"].startswith(f"pubmed/{source.id}/raw/")
        assert call_kwargs["content_type"] == "application/json"
        assert call_kwargs["metadata"]["record_count"] == 1

        file_path = call_kwargs["file_path"]
        assert isinstance(file_path, pathlib.Path)
        assert file_path.exists() is False  # Should be cleaned up
        # Note: We can't easily check content after cleanup unless we mock tempfile,
        # but the logic flow is verified by the call args.

    @pytest.mark.asyncio
    async def test_ingest_skips_storage_if_service_missing(
        self,
        mock_gateway: Mock,
        mock_repo: Mock,
    ) -> None:
        service = PubMedIngestionService(
            gateway=mock_gateway,
            publication_repository=mock_repo,
            storage_service=None,
            pipeline=Mock(),
        )
        source = UserDataSource(
            id=uuid4(),
            owner_id=uuid4(),
            name="Test Source",
            source_type=SourceType.PUBMED,
            configuration=SourceConfiguration(metadata={"query": "test"}),
        )

        await service.ingest(source)
        # No error should be raised


class TestBulkExportStorage:
    @pytest.fixture
    def export_service(self, mock_storage_service: Mock) -> BulkExportService:
        return BulkExportService(
            entity_repo=Mock(),
            observation_repo=Mock(),
            relation_repo=Mock(),
            storage_service=mock_storage_service,
        )

    @pytest.mark.asyncio
    async def test_export_to_storage_success(
        self,
        export_service: BulkExportService,
        mock_storage_service: Mock,
        mock_storage_backend: Mock,
    ) -> None:
        # Arrange
        mock_storage_service.resolve_backend_for_use_case.return_value = (
            mock_storage_backend
        )
        # Mock internal export_data to return chunks
        export_service.export_data = Mock(
            return_value=iter(['{"test": 1}']),
        )  # type: ignore[assignment]
        user_id = uuid4()
        space_id = "space-1"

        # Act
        await export_service.export_to_storage(
            research_space_id=space_id,
            entity_type="entities",
            export_format=ExportFormat.JSON,
            user_id=user_id,
        )

        # Assert
        mock_storage_service.resolve_backend_for_use_case.assert_called_with(
            StorageUseCase.EXPORT,
        )
        mock_storage_service.record_store_operation.assert_called_once()
        kwargs = mock_storage_service.record_store_operation.call_args.kwargs
        assert f"exports/research-spaces/{space_id}/entities/" in kwargs["key"]
        assert kwargs["content_type"] == "application/json"
        assert kwargs["user_id"] == user_id

    @pytest.mark.asyncio
    async def test_export_to_storage_fails_without_backend(
        self,
        export_service: BulkExportService,
        mock_storage_service: Mock,
    ) -> None:
        mock_storage_service.resolve_backend_for_use_case.return_value = None
        with pytest.raises(ValueError, match="No storage backend configured"):
            await export_service.export_to_storage(
                research_space_id="space-1",
                entity_type="entities",
                export_format=ExportFormat.JSON,
                user_id=uuid4(),
            )


class TestPubMedDiscoveryLogging:
    @pytest.fixture
    def mock_search_gateway(self) -> Mock:
        gateway = Mock()
        gateway.run_search = MagicMock()
        return gateway

    @pytest.mark.asyncio
    async def test_search_failure_logs_error(self, mock_search_gateway: Mock) -> None:
        # Arrange
        mock_search_gateway.run_search.side_effect = Exception("API Error")
        repo = Mock()
        repo.create = Mock(side_effect=lambda x: x)
        repo.update = Mock(side_effect=lambda x: x)

        service = PubMedDiscoveryService(
            job_repository=repo,
            query_builder=Mock(validate=Mock(), build_query=Mock(return_value="query")),
            search_gateway=mock_search_gateway,
            pdf_gateway=Mock(),
        )

        # Act
        with patch(
            "src.application.services.pubmed_discovery_service.logger",
        ) as mock_logger:
            with pytest.raises(Exception, match="API Error"):
                await service.run_pubmed_search(
                    uuid4(),
                    RunPubmedSearchRequest(
                        parameters=AdvancedQueryParameters(search_term="test"),
                    ),
                )

            # Assert
            mock_logger.exception.assert_called_once()
            args, kwargs = mock_logger.exception.call_args
            assert args[0] == "PubMed search failed"
            assert kwargs["extra"]["metric_type"] == "discovery_search"
            assert kwargs["extra"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_download_success_logs_metric(self) -> None:
        # Arrange
        repo = Mock()
        job_id = uuid4()
        owner_id = uuid4()
        job = Mock()
        job.id = job_id
        job.owner_id = owner_id
        job.status = DiscoverySearchStatus.COMPLETED
        job.result_metadata = {"article_ids": ["123"]}
        job.model_copy.return_value = job
        repo.get.return_value = job

        coordinator = Mock()
        record = Mock(spec=StorageOperationRecord)
        record.key = "test.pdf"
        coordinator.store_for_use_case = AsyncMock(return_value=record)

        service = PubMedDiscoveryService(
            job_repository=repo,
            query_builder=Mock(),
            search_gateway=Mock(),
            pdf_gateway=Mock(fetch_pdf=AsyncMock(return_value=b"pdf")),
            storage_coordinator=coordinator,
        )

        # Act
        with patch(
            "src.application.services.pubmed_discovery_service.logger",
        ) as mock_logger:
            await service.download_article_pdf(
                owner_id,
                PubmedDownloadRequest(job_id=job_id, article_id="123"),
            )

            # Assert
            mock_logger.info.assert_called_once()
            args, kwargs = mock_logger.info.call_args
            assert args[0] == "PubMed PDF downloaded and stored"
            assert kwargs["extra"]["metric_type"] == "discovery_automation_coverage"
            assert kwargs["extra"]["article_id"] == "123"
