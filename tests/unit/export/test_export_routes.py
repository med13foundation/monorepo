"""
Tests for Bulk Export Routes with type safety patterns.

Kernel-native exports are research-space-scoped and support:
- entities
- observations
- relations
"""

import json
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.export.export_types import CompressionFormat, ExportFormat
from src.domain.entities.user import User, UserRole, UserStatus
from src.routes.export import router


class TestExportRoutes:
    """Test suite for export routes with comprehensive type safety."""

    @pytest.fixture
    def mock_export_service(self) -> Mock:
        """Create typed mock export service."""
        mock_service = Mock()

        def mock_export_data(
            research_space_id: str,
            entity_type: str,
            export_format: ExportFormat,
            compression: CompressionFormat,
            **kwargs: object,
        ):
            _ = research_space_id
            _ = compression
            _ = kwargs
            if export_format == ExportFormat.JSON:
                test_data = {f"{entity_type}": [{"id": 1, "name": "Test Item"}]}
                yield json.dumps(test_data)
            elif export_format == ExportFormat.CSV:
                yield "id,name\n1,Test Item\n"
            else:
                yield "test data"

        mock_service.export_data.side_effect = mock_export_data

        mock_service.get_export_info.return_value = {
            "entity_type": "entities",
            "supported_formats": ["json", "csv"],
            "supported_compression": ["none", "gzip"],
            "estimated_record_count": 100,
        }

        return mock_service

    @pytest.fixture
    def test_user(self) -> User:
        """Admin user bypasses membership checks in verify_space_membership."""
        return User(
            id=uuid4(),
            email="admin@example.com",
            username="admin",
            full_name="Admin User",
            hashed_password="hashed",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )

    @pytest.fixture
    def test_client(
        self,
        mock_export_service: Mock,
        test_user: User,
    ) -> TestClient:
        """Create test client with mocked export service and auth dependencies."""
        from src.database.session import get_session
        from src.routes.auth import get_current_active_user
        from src.routes.export import get_export_service
        from src.routes.research_spaces.dependencies import get_membership_service

        app = FastAPI()
        app.include_router(router)

        app.dependency_overrides[get_export_service] = lambda: mock_export_service
        app.dependency_overrides[get_current_active_user] = lambda: test_user
        app.dependency_overrides[get_membership_service] = lambda: Mock()
        app.dependency_overrides[get_session] = lambda: Mock()

        return TestClient(app)

    def test_export_entities_json_format(
        self,
        test_client: TestClient,
        mock_export_service: Mock,
    ) -> None:
        """Test exporting entities in JSON format returns correct response."""
        space_id = uuid4()

        response = test_client.get(f"/export/entities?space_id={space_id}&format=json")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert "content-disposition" in response.headers

        mock_export_service.export_data.assert_called_once_with(
            research_space_id=str(space_id),
            entity_type="entities",
            export_format=ExportFormat.JSON,
            compression=CompressionFormat.NONE,
            filters=None,
        )

        data = response.json()
        assert "entities" in data
        assert isinstance(data["entities"], list)
        assert len(data["entities"]) == 1
        assert data["entities"][0]["id"] == 1

    def test_export_observations_csv_format(
        self,
        test_client: TestClient,
    ) -> None:
        """Test exporting observations in CSV format returns correct response."""
        space_id = uuid4()

        response = test_client.get(
            f"/export/observations?space_id={space_id}&format=csv",
        )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert (
            response.headers["content-disposition"]
            == "attachment; filename=observations.csv"
        )

        content = response.text
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert lines[0] == "id,name"

    def test_export_with_gzip_compression(
        self,
        test_client: TestClient,
        mock_export_service: Mock,
    ) -> None:
        """Test exporting with gzip compression."""
        space_id = uuid4()

        response = test_client.get(
            f"/export/relations?space_id={space_id}&format=json&compression=gzip",
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/gzip"
        assert "relations.json.gz" in response.headers["content-disposition"]

        mock_export_service.export_data.assert_called_once_with(
            research_space_id=str(space_id),
            entity_type="relations",
            export_format=ExportFormat.JSON,
            compression=CompressionFormat.GZIP,
            filters=None,
        )

    def test_export_with_limit_parameter(
        self,
        test_client: TestClient,
        mock_export_service: Mock,
    ) -> None:
        """Test exporting with limit parameter."""
        space_id = uuid4()

        response = test_client.get(
            f"/export/entities?space_id={space_id}&format=json&limit=50",
        )

        assert response.status_code == 200
        mock_export_service.export_data.assert_called_once_with(
            research_space_id=str(space_id),
            entity_type="entities",
            export_format=ExportFormat.JSON,
            compression=CompressionFormat.NONE,
            filters={"limit": 50},
        )

    def test_invalid_entity_type_returns_400(self, test_client: TestClient) -> None:
        """Test that invalid export entity types return 400 error."""
        space_id = uuid4()

        response = test_client.get(
            f"/export/invalid_entity?space_id={space_id}&format=json",
        )

        assert response.status_code == 400
        error_data = response.json()
        assert "detail" in error_data
        assert "Invalid entity type" in error_data["detail"]

    def test_get_export_info_returns_correct_structure(
        self,
        test_client: TestClient,
        mock_export_service: Mock,
    ) -> None:
        """Test get export info endpoint returns typed structure."""
        space_id = uuid4()

        response = test_client.get(f"/export/entities/info?space_id={space_id}")

        assert response.status_code == 200
        data = response.json()

        assert data["entity_type"] == "entities"
        assert isinstance(data["export_formats"], list)
        assert isinstance(data["compression_formats"], list)
        assert "json" in data["export_formats"]
        assert "csv" in data["export_formats"]
        assert "none" in data["compression_formats"]
        assert "gzip" in data["compression_formats"]

        mock_export_service.get_export_info.assert_called_once_with(
            research_space_id=str(space_id),
            entity_type="entities",
            filters=None,
        )

    def test_list_exportable_entities_returns_complete_list(
        self,
        test_client: TestClient,
    ) -> None:
        """Test list exportable entities endpoint returns all supported entities."""
        response = test_client.get("/export/")

        assert response.status_code == 200
        data = response.json()

        assert "exportable_entities" in data
        assert isinstance(data["exportable_entities"], list)
        assert len(data["exportable_entities"]) == 3

        entity_types = [entity["type"] for entity in data["exportable_entities"]]
        assert "entities" in entity_types
        assert "observations" in entity_types
        assert "relations" in entity_types

        assert "usage" in data
        assert "endpoint" in data["usage"]

    def test_invalid_format_parameter_returns_422(
        self,
        test_client: TestClient,
    ) -> None:
        space_id = uuid4()
        response = test_client.get(
            f"/export/entities?space_id={space_id}&format=invalid",
        )
        assert response.status_code == 422

    def test_invalid_compression_parameter_returns_422(
        self,
        test_client: TestClient,
    ) -> None:
        space_id = uuid4()
        response = test_client.get(
            f"/export/entities?space_id={space_id}&format=json&compression=invalid",
        )
        assert response.status_code == 422

    def test_streaming_response_headers_are_correct(
        self,
        test_client: TestClient,
    ) -> None:
        space_id = uuid4()
        response = test_client.get(f"/export/entities?space_id={space_id}&format=json")

        required_headers = [
            "content-type",
            "content-disposition",
            "x-entity-type",
            "x-export-format",
            "x-compression",
        ]
        for header in required_headers:
            assert header in response.headers

        assert response.headers["x-entity-type"] == "entities"
        assert response.headers["x-export-format"] == "json"
        assert response.headers["x-compression"] == "none"
        assert "entities.json" in response.headers["content-disposition"]

    def test_export_service_error_returns_error_content(
        self,
        test_client: TestClient,
        mock_export_service: Mock,
    ) -> None:
        """StreamingResponse still returns 200 but includes error content."""
        space_id = uuid4()
        mock_export_service.export_data.side_effect = Exception("Service error")

        response = test_client.get(f"/export/entities?space_id={space_id}&format=json")

        response_text = response.text
        assert (
            "Error during export" in response_text or "Service error" in response_text
        )
