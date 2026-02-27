"""
Unit tests for provenance value object.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.domain.value_objects.provenance import DataSource, Provenance

QUALITY_SCORE_VALID = 0.95
QUALITY_SCORE_UPDATE = 0.85
QUALITY_SCORE_ABOVE_MAX = 1.5
QUALITY_SCORE_BELOW_MIN = -0.5


class TestProvenance:
    """Test Provenance value object."""

    def test_create_provenance(self):
        """Test creating a valid Provenance."""
        acquired_at = datetime.now(UTC)
        provenance = Provenance(
            source=DataSource.CLINVAR,
            source_version="2023.01",
            source_url="https://www.ncbi.nlm.nih.gov/clinvar/",
            acquired_by="test_system",
            acquired_at=acquired_at,
            processing_steps=["normalized", "validated"],
            quality_score=QUALITY_SCORE_VALID,
            validation_status="validated",
            metadata={"key": "value"},
        )

        assert provenance.source == DataSource.CLINVAR
        assert provenance.source_version == "2023.01"
        assert provenance.source_url == "https://www.ncbi.nlm.nih.gov/clinvar/"
        assert provenance.acquired_by == "test_system"
        assert provenance.acquired_at == acquired_at
        assert provenance.processing_steps == ("normalized", "validated")
        assert provenance.quality_score == QUALITY_SCORE_VALID
        assert provenance.validation_status == "validated"
        assert provenance.metadata == {"key": "value"}

    def test_default_values(self):
        """Test default values for Provenance."""
        provenance = Provenance(source=DataSource.PUBMED, acquired_by="test_system")

        assert provenance.processing_steps == ()
        assert provenance.validation_status == "pending"
        assert provenance.metadata == {}
        assert provenance.quality_score is None
        assert isinstance(provenance.acquired_at, datetime)

    def test_add_processing_step(self):
        """Test adding a processing step."""
        provenance = Provenance(source=DataSource.CLINVAR, acquired_by="test_system")

        new_provenance = provenance.add_processing_step("normalized")

        assert new_provenance.processing_steps == ("normalized",)
        assert provenance.processing_steps == ()  # Original unchanged

    def test_update_quality_score(self):
        """Test updating quality score."""
        provenance = Provenance(source=DataSource.CLINVAR, acquired_by="test_system")

        new_provenance = provenance.update_quality_score(QUALITY_SCORE_UPDATE)

        assert new_provenance.quality_score == QUALITY_SCORE_UPDATE
        assert provenance.quality_score is None  # Original unchanged

    def test_mark_validated(self):
        """Test marking as validated."""
        provenance = Provenance(
            source=DataSource.CLINVAR,
            acquired_by="test_system",
            validation_status="pending",
        )

        new_provenance = provenance.mark_validated("approved")

        assert new_provenance.validation_status == "approved"
        assert provenance.validation_status == "pending"  # Original unchanged

    def test_is_validated(self):
        """Test validation status checking."""
        valid_provenance = Provenance(
            source=DataSource.CLINVAR,
            acquired_by="test_system",
            validation_status="validated",
        )

        approved_provenance = Provenance(
            source=DataSource.CLINVAR,
            acquired_by="test_system",
            validation_status="approved",
        )

        pending_provenance = Provenance(
            source=DataSource.CLINVAR,
            acquired_by="test_system",
            validation_status="pending",
        )

        assert valid_provenance.is_validated is True
        assert approved_provenance.is_validated is True
        assert pending_provenance.is_validated is False

    def test_processing_summary(self):
        """Test processing summary generation."""
        provenance = Provenance(
            source=DataSource.CLINVAR,
            acquired_by="test_system",
            processing_steps=["ingested", "normalized", "validated"],
        )

        assert provenance.processing_summary == "ingested → normalized → validated"

    def test_processing_summary_empty(self):
        """Test processing summary with no steps."""
        provenance = Provenance(source=DataSource.CLINVAR, acquired_by="test_system")

        assert provenance.processing_summary == "No processing steps recorded"

    def test_string_representation(self):
        """Test string representation."""
        acquired_at = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        provenance = Provenance(
            source=DataSource.CLINVAR,
            acquired_by="test_system",
            acquired_at=acquired_at,
            validation_status="validated",
        )

        assert str(provenance) == "clinvar (2023-01-01) - validated"

    def test_immutable(self):
        """Test that Provenance is immutable."""
        provenance = Provenance(source=DataSource.CLINVAR, acquired_by="test_system")

        with pytest.raises(
            ValidationError,
            match="Instance is frozen",
        ):
            provenance.source = DataSource.PUBMED

    def test_invalid_quality_score(self):
        """Test invalid quality score."""
        with pytest.raises(
            ValidationError,
            match="less than or equal to 1",
        ):
            Provenance(
                source=DataSource.CLINVAR,
                acquired_by="test_system",
                quality_score=QUALITY_SCORE_ABOVE_MAX,
            )

        with pytest.raises(
            ValidationError,
            match="greater than or equal to 0",
        ):
            Provenance(
                source=DataSource.CLINVAR,
                acquired_by="test_system",
                quality_score=QUALITY_SCORE_BELOW_MIN,
            )
