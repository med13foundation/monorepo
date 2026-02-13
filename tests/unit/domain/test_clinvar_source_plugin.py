"""Unit tests for ClinVar source plugin validation."""

from __future__ import annotations

import pytest

from src.domain.entities.user_data_source import SourceConfiguration
from src.domain.services.source_plugins.plugins import ClinVarSourcePlugin


class TestClinVarSourcePlugin:
    """Validate ClinVarSourcePlugin behavior."""

    def setup_method(self) -> None:
        self.plugin = ClinVarSourcePlugin()

    def test_validate_configuration_sets_defaults(self) -> None:
        """Defaults should be applied for minimal ClinVar metadata."""
        config = SourceConfiguration(metadata={"gene_symbol": "med13"})

        validated = self.plugin.validate_configuration(config)

        assert validated.metadata["gene_symbol"] == "MED13"
        assert isinstance(validated.metadata.get("query"), str)
        assert validated.requests_per_minute == self.plugin.DEFAULT_REQUESTS_PER_MINUTE

    def test_validate_configuration_preserves_requests_per_minute(self) -> None:
        """Provided rate limits should be preserved."""
        config = SourceConfiguration(
            metadata={"gene_symbol": "MED13", "query": "MED13 pathogenic variant"},
            requests_per_minute=25,
        )

        validated = self.plugin.validate_configuration(config)

        assert validated.requests_per_minute == 25

    def test_validate_configuration_rejects_empty_gene_symbol(self) -> None:
        """Empty gene symbols should fail validation."""
        config = SourceConfiguration(
            metadata={"gene_symbol": "   ", "query": "MED13 pathogenic variant"},
        )

        with pytest.raises(ValueError):
            self.plugin.validate_configuration(config)
