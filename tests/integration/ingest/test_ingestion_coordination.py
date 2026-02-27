"""
Integration tests for data ingestion coordination.
Tests parallel execution, error handling, and result aggregation.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.value_objects import DataSource, Provenance
from src.infrastructure.ingest.base_ingestor import IngestionResult, IngestionStatus
from src.infrastructure.ingest.coordinator import (
    IngestionCoordinator,
    IngestionPhase,
    IngestionTask,
)


class TestIngestionCoordinator:
    """Test cases for ingestion coordination."""

    @pytest.fixture
    def coordinator(self):
        """Create test coordinator instance."""
        return IngestionCoordinator(max_concurrent_ingestors=2, enable_parallel=True)

    @pytest.fixture
    def mock_ingestor_result(self):
        """Create mock ingestor result."""
        return IngestionResult(
            source="test_source",
            status=IngestionStatus.COMPLETED,
            records_processed=10,
            records_failed=0,
            data=[{"id": 1}, {"id": 2}],
            provenance=Provenance(
                source=DataSource.CLINVAR,
                acquired_at=datetime.now(UTC),
                acquired_by="test",
                processing_steps=["Test step"],
                validation_status="valid",
                quality_score=1.0,
            ),
            errors=[],
            duration_seconds=1.5,
            timestamp=datetime.now(UTC),
        )

    def test_coordinator_initialization(self, coordinator):
        """Test coordinator initializes correctly."""
        assert coordinator.max_concurrent_ingestors == 2
        assert coordinator.enable_parallel is True
        assert coordinator.results == {}

    @pytest.mark.asyncio
    async def test_coordinate_single_task(self, coordinator, mock_ingestor_result):
        """Test coordination with single task."""
        # Create mock ingestor class
        mock_ingestor_class = MagicMock()
        mock_ingestor_instance = AsyncMock()
        mock_ingestor_instance.__aenter__ = AsyncMock(
            return_value=mock_ingestor_instance,
        )
        mock_ingestor_instance.__aexit__ = AsyncMock(return_value=None)
        mock_ingestor_instance.ingest = AsyncMock(return_value=mock_ingestor_result)
        mock_ingestor_class.return_value = mock_ingestor_instance

        # Create task
        task = IngestionTask(
            source="test_source",
            ingestor_class=mock_ingestor_class,
            parameters={"param1": "value1"},
        )

        # Execute coordination
        result = await coordinator.coordinate_ingestion([task])

        # Verify results
        assert result.total_sources == 1
        assert result.completed_sources == 1
        assert result.failed_sources == 0
        assert result.total_records == 10
        assert result.total_errors == 0
        assert result.phase == IngestionPhase.COMPLETED
        assert "test_source" in result.source_results

    @pytest.mark.asyncio
    async def test_coordinate_multiple_tasks_parallel(self, coordinator):
        """Test coordination with multiple tasks in parallel."""
        # Create multiple mock results
        results = []
        for i in range(3):
            result = IngestionResult(
                source=f"source_{i}",
                status=IngestionStatus.COMPLETED,
                records_processed=5,
                records_failed=0,
                data=[{"id": j} for j in range(5)],
                provenance=Provenance(
                    source=DataSource.CLINVAR,
                    acquired_at=datetime.now(UTC),
                    acquired_by="test",
                    processing_steps=["Test step"],
                    validation_status="valid",
                    quality_score=1.0,
                ),
                errors=[],
                duration_seconds=1.0,
                timestamp=datetime.now(UTC),
            )
            results.append(result)

        # Create mock ingestor classes
        mock_classes = []
        for i, result in enumerate(results):
            mock_class = MagicMock()
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.ingest = AsyncMock(return_value=result)
            mock_class.return_value = mock_instance
            mock_classes.append(mock_class)

        # Create tasks
        tasks = [
            IngestionTask(
                source=f"source_{i}",
                ingestor_class=mock_class,
                parameters={},
            )
            for i, mock_class in enumerate(mock_classes)
        ]

        # Execute coordination
        result = await coordinator.coordinate_ingestion(tasks)

        # Verify results
        assert result.total_sources == 3
        assert result.completed_sources == 3
        assert result.failed_sources == 0
        assert result.total_records == 15  # 3 sources * 5 records each
        assert result.total_errors == 0

    @pytest.mark.asyncio
    async def test_coordinate_with_failures(self, coordinator):
        """Test coordination handles task failures gracefully."""
        # Create success result
        success_result = IngestionResult(
            source="clinvar",
            status=IngestionStatus.COMPLETED,
            records_processed=5,
            records_failed=0,
            data=[{"id": 1}],
            provenance=Provenance(
                source=DataSource.CLINVAR,
                acquired_at=datetime.now(UTC),
                acquired_by="test",
                processing_steps=["Success"],
                validation_status="valid",
                quality_score=1.0,
            ),
            errors=[],
            duration_seconds=1.0,
            timestamp=datetime.now(UTC),
        )

        # Create mock classes
        success_class = MagicMock()
        success_instance = AsyncMock()
        success_instance.__aenter__ = AsyncMock(return_value=success_instance)
        success_instance.__aexit__ = AsyncMock(return_value=None)
        success_instance.ingest = AsyncMock(return_value=success_result)
        success_class.return_value = success_instance

        failure_class = MagicMock()
        failure_instance = AsyncMock()
        failure_instance.__aenter__ = AsyncMock(return_value=failure_instance)
        failure_instance.__aexit__ = AsyncMock(return_value=None)
        failure_instance.ingest = AsyncMock(side_effect=Exception("Test failure"))
        failure_class.return_value = failure_instance

        # Create tasks
        tasks = [
            IngestionTask(
                source="clinvar",
                ingestor_class=success_class,
                parameters={},
            ),
            IngestionTask(source="pubmed", ingestor_class=failure_class, parameters={}),
        ]

        # Execute coordination
        result = await coordinator.coordinate_ingestion(tasks)

        # Verify results handle partial failures
        assert result.total_sources == 2
        assert result.completed_sources == 1
        assert result.failed_sources == 1
        assert result.total_records == 5  # Only success records counted
        assert result.total_errors == 1

    @pytest.mark.asyncio
    async def test_sequential_execution(self, coordinator):
        """Test sequential execution mode."""
        coordinator.enable_parallel = False

        # Create mock results
        results = []
        for i in range(2):
            result = IngestionResult(
                source=f"source_{i}",
                status=IngestionStatus.COMPLETED,
                records_processed=3,
                records_failed=0,
                data=[{"id": j} for j in range(3)],
                provenance=Provenance(
                    source=DataSource.CLINVAR,
                    acquired_at=datetime.now(UTC),
                    acquired_by="test",
                    processing_steps=["Sequential test"],
                    validation_status="valid",
                    quality_score=1.0,
                ),
                errors=[],
                duration_seconds=0.5,
                timestamp=datetime.now(UTC),
            )
            results.append(result)

        # Create mock classes
        mock_classes = []
        for result in results:
            mock_class = MagicMock()
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.ingest = AsyncMock(return_value=result)
            mock_class.return_value = mock_instance
            mock_classes.append(mock_class)

        # Create tasks
        tasks = [
            IngestionTask(
                source=f"source_{i}",
                ingestor_class=mock_class,
                parameters={},
            )
            for i, mock_class in enumerate(mock_classes)
        ]

        # Execute coordination
        result = await coordinator.coordinate_ingestion(tasks)

        # Verify sequential execution
        assert result.total_sources == 2
        assert result.completed_sources == 2
        assert result.total_records == 6

    def test_ingestion_summary_generation(self, coordinator):
        """Test generation of ingestion summary."""
        # Create mock result
        result = MagicMock()
        result.total_sources = 3
        result.completed_sources = 2
        result.failed_sources = 1
        result.total_records = 150
        result.total_errors = 2
        result.duration_seconds = 30.0
        result.source_results = {
            "clinvar": MagicMock(
                status=MagicMock(name="COMPLETED"),
                records_processed=50,
                records_failed=0,
                errors=[],
                duration_seconds=10.0,
            ),
            "pubmed": MagicMock(
                status=MagicMock(name="COMPLETED"),
                records_processed=75,
                records_failed=0,
                errors=[],
                duration_seconds=15.0,
            ),
            "uniprot": MagicMock(
                status=MagicMock(name="FAILED"),
                records_processed=0,
                records_failed=1,
                errors=["error"],
                duration_seconds=5.0,
            ),
        }

        summary = coordinator.get_ingestion_summary(result)

        assert summary["total_sources"] == 3
        assert summary["completed_sources"] == 2
        assert summary["failed_sources"] == 1
        assert summary["success_rate"] == pytest.approx(66.67, rel=1e-2)
        assert summary["total_records"] == 150
        assert summary["total_errors"] == 2
        assert summary["records_per_second"] == 5.0  # 150 / 30

        # Check source details
        assert len(summary["source_details"]) == 3
        assert summary["source_details"]["clinvar"]["records_processed"] == 50
        assert summary["source_details"]["uniprot"]["errors_count"] == 1

    @pytest.mark.asyncio
    async def test_ingest_all_sources_convenience_method(self, coordinator):
        """Test convenience method for ingesting all sources."""
        # Mock the coordinate_ingestion method
        mock_result = MagicMock()
        mock_result.total_sources = 4
        mock_result.completed_sources = 4
        mock_result.failed_sources = 0
        mock_result.total_records = 200
        mock_result.total_errors = 0
        mock_result.duration_seconds = 45.0
        mock_result.source_results = {}

        with patch.object(
            coordinator,
            "coordinate_ingestion",
            return_value=mock_result,
        ) as mock_coord:
            await coordinator.ingest_all_sources("MED13", max_results=100)

            # Verify coordinate_ingestion was called with correct tasks
            mock_coord.assert_called_once()
            call_args = mock_coord.call_args
            tasks = call_args[0][0]  # First positional argument

            # Verify all 4 sources are included
            source_names = {task.source for task in tasks}
            assert source_names == {"clinvar", "pubmed", "hpo", "uniprot"}

            # Verify parameters were passed through
            assert call_args[1]["max_results"] == 100

    @pytest.mark.asyncio
    async def test_ingest_critical_sources_only(self, coordinator):
        """Test convenience method for critical sources only."""
        mock_result = MagicMock()
        mock_result.total_sources = 2
        mock_result.completed_sources = 2

        with patch.object(
            coordinator,
            "coordinate_ingestion",
            return_value=mock_result,
        ) as mock_coord:
            await coordinator.ingest_critical_sources_only("MED13")

            # Verify only critical sources are included
            mock_coord.assert_called_once()
            tasks = mock_coord.call_args[0][0]
            source_names = {task.source for task in tasks}
            assert source_names == {"clinvar", "uniprot"}
