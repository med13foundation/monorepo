"""
Tests for kernel-native BulkExportService.

Exports are research-space-scoped and support:
- entities
- observations
- relations
"""

import gzip
import json
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from src.application.export.export_service import BulkExportService
from src.application.export.export_types import CompressionFormat, ExportFormat
from src.application.export.utils import (
    get_entity_fields,
    get_observation_fields,
    get_relation_fields,
)
from src.application.services.storage_configuration_service import (
    StorageConfigurationService,
)
from src.domain.entities.storage_configuration import StorageConfiguration
from src.type_definitions.storage import StorageUseCase


class TestBulkExportService:
    @pytest.fixture
    def mock_entity_repo(self) -> Mock:
        repo = Mock()
        repo.find_by_research_space.return_value = [
            {
                "id": "ent-1",
                "research_space_id": "space-1",
                "entity_type": "GENE",
                "display_label": "MED13",
                "metadata_payload": {"foo": "bar"},
            },
        ]
        repo.count_by_type.return_value = {"GENE": 1}
        return repo

    @pytest.fixture
    def mock_observation_repo(self) -> Mock:
        repo = Mock()
        repo.find_by_research_space.return_value = [
            {
                "id": "obs-1",
                "research_space_id": "space-1",
                "subject_id": "ent-1",
                "variable_id": "VAR_GENE_SYMBOL",
                "value_text": "MED13",
                "unit": None,
                "confidence": 1.0,
            },
        ]
        repo.count_by_research_space.return_value = 1
        return repo

    @pytest.fixture
    def mock_relation_repo(self) -> Mock:
        repo = Mock()
        repo.find_by_research_space.return_value = [
            {
                "id": "rel-1",
                "research_space_id": "space-1",
                "source_id": "ent-1",
                "relation_type": "ASSOCIATED_WITH",
                "target_id": "ent-2",
                "confidence": 0.5,
                "curation_status": "DRAFT",
            },
        ]
        repo.count_by_research_space.return_value = 1
        return repo

    @pytest.fixture
    def export_service(
        self,
        mock_entity_repo: Mock,
        mock_observation_repo: Mock,
        mock_relation_repo: Mock,
    ) -> BulkExportService:
        return BulkExportService(
            entity_repo=mock_entity_repo,
            observation_repo=mock_observation_repo,
            relation_repo=mock_relation_repo,
        )

    def test_export_entities_json_format(
        self,
        export_service: BulkExportService,
    ) -> None:
        result = list(
            export_service.export_data(
                research_space_id="space-1",
                entity_type="entities",
                export_format=ExportFormat.JSON,
                compression=CompressionFormat.NONE,
            ),
        )

        assert len(result) == 1
        assert isinstance(result[0], str)

        data = json.loads(result[0])
        assert "entities" in data
        assert isinstance(data["entities"], list)
        assert data["entities"][0]["display_label"] == "MED13"

    def test_export_observations_csv_format(
        self,
        export_service: BulkExportService,
    ) -> None:
        result = list(
            export_service.export_data(
                research_space_id="space-1",
                entity_type="observations",
                export_format=ExportFormat.CSV,
                compression=CompressionFormat.NONE,
            ),
        )

        assert len(result) == 1
        assert isinstance(result[0], str)
        header = result[0].splitlines()[0].split(",")
        for field in ("id", "variable_id", "subject_id"):
            assert field in header

    def test_export_relations_compressed_json(
        self,
        export_service: BulkExportService,
    ) -> None:
        result = list(
            export_service.export_data(
                research_space_id="space-1",
                entity_type="relations",
                export_format=ExportFormat.JSON,
                compression=CompressionFormat.GZIP,
            ),
        )

        assert len(result) == 1
        assert isinstance(result[0], bytes)
        decompressed = gzip.decompress(result[0]).decode("utf-8")
        data = json.loads(decompressed)
        assert "relations" in data

    def test_export_invalid_entity_type_raises_error(
        self,
        export_service: BulkExportService,
    ) -> None:
        with pytest.raises(ValueError, match="Unsupported entity type"):
            list(
                export_service.export_data(
                    research_space_id="space-1",
                    entity_type="invalid",
                    export_format=ExportFormat.JSON,
                ),
            )

    def test_get_export_info_entities(
        self,
        export_service: BulkExportService,
    ) -> None:
        info = export_service.get_export_info(
            research_space_id="space-1",
            entity_type="entities",
        )
        assert info["entity_type"] == "entities"
        assert info["estimated_record_count"] == 1

    def test_kernel_field_lists_are_non_empty(self) -> None:
        assert "entity_type" in get_entity_fields()
        assert "variable_id" in get_observation_fields()
        assert "relation_type" in get_relation_fields()

    @pytest.mark.asyncio
    async def test_export_to_storage_orchestrates_operation(self) -> None:
        mock_storage_service = Mock(spec=StorageConfigurationService)
        mock_backend = Mock(spec=StorageConfiguration)
        mock_storage_service.resolve_backend_for_use_case.return_value = mock_backend
        mock_storage_service.record_store_operation = AsyncMock()

        service = BulkExportService(
            entity_repo=Mock(),
            observation_repo=Mock(),
            relation_repo=Mock(),
            storage_service=mock_storage_service,
        )
        # Mock internal export_data to return chunks
        service.export_data = Mock(return_value=iter(['{"test": 1}']))  # type: ignore[assignment]

        user_id = uuid4()
        space_id = "space-1"

        await service.export_to_storage(
            research_space_id=space_id,
            entity_type="entities",
            export_format=ExportFormat.JSON,
            user_id=user_id,
        )

        mock_storage_service.resolve_backend_for_use_case.assert_called_with(
            StorageUseCase.EXPORT,
        )
        mock_storage_service.record_store_operation.assert_called_once()
        kwargs = mock_storage_service.record_store_operation.call_args.kwargs
        assert f"research-spaces/{space_id}/entities/" in kwargs["key"]
        assert kwargs["content_type"] == "application/json"
        assert kwargs["user_id"] == user_id
