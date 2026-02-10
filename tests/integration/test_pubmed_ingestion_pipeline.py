"""
Integration test for PubMed ingestion pipeline refactor.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.services.pubmed_ingestion_service import PubMedIngestionService
from src.domain.entities.user_data_source import SourceType, UserDataSource
from src.domain.services.pubmed_ingestion import PubMedGateway
from src.infrastructure.ingestion.pipeline import IngestionPipeline
from src.type_definitions.ingestion import IngestResult


@pytest.fixture
def mock_gateway():
    gateway = MagicMock(spec=PubMedGateway)
    gateway.fetch_records = AsyncMock(
        return_value=[
            {
                "pmid": "123456",
                "title": "Test Study",
                "abstract": "This is a test abstract.",
                "doi": "10.1000/123456",
                "publication_date": "2023-01-01",
            },
        ],
    )
    return gateway


@pytest.fixture
def mock_pipeline():
    pipeline = MagicMock(spec=IngestionPipeline)
    pipeline.run = MagicMock(
        return_value=IngestResult(
            success=True,
            observations_created=1,
            entities_created=1,
            errors=[],
        ),
    )
    return pipeline


@pytest.fixture
def service(mock_gateway, mock_pipeline):
    return PubMedIngestionService(
        gateway=mock_gateway,
        pipeline=mock_pipeline,
        # Other deps can be None for this test as we mocking dependencies
    )


@pytest.mark.asyncio
async def test_pubmed_ingestion_success(service, mock_gateway, mock_pipeline):
    # Arrange
    import uuid

    source_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    space_id = str(uuid.uuid4())

    source = UserDataSource(
        id=source_id,
        name="Test Source",
        source_type=SourceType.PUBMED,
        configuration={"query": "test query"},
        owner_id=user_id,
        research_space_id=space_id,
    )

    # Act
    summary = await service.ingest(source)

    # Assert
    # 1. Gateway called
    mock_gateway.fetch_records.assert_called_once()

    # 2. Pipeline called
    mock_pipeline.run.assert_called_once()
    call_args = mock_pipeline.run.call_args
    assert call_args is not None
    records = call_args[0][0]
    research_space_id = call_args[1]["research_space_id"]

    assert len(records) == 1
    assert records[0].source_id == "123456"
    assert records[0].data["pmid"] == "123456"
    assert research_space_id == space_id

    # 3. Summary correct
    assert summary.fetched_records == 1
    assert summary.created_publications == 1
