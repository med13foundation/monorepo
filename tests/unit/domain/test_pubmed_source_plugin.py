"""Unit tests for PubMed source plugin validation."""

import pytest

from src.domain.entities.user_data_source import SourceConfiguration
from src.domain.services.source_plugins.plugins import PubMedSourcePlugin


class TestPubMedSourcePlugin:
    """Validate PubMedSourcePlugin behavior."""

    def setup_method(self) -> None:
        self.plugin = PubMedSourcePlugin()
        self.base_config = SourceConfiguration(
            url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
            metadata={
                "query": "MED13 AND (mutation OR variant)",
                "date_from": "2020/01/01",
                "date_to": "2024/01/01",
                "publication_types": ["journal_article", "review"],
                "max_results": 500,
                "relevance_threshold": 7,
            },
        )

    def test_validate_configuration_sets_defaults(self) -> None:
        """Ensure valid configs are returned with defaults applied."""
        validated = self.plugin.validate_configuration(self.base_config)

        assert validated.metadata["query"] == "MED13 AND (mutation OR variant)"
        assert validated.metadata["domain_context"] == "clinical"
        assert validated.metadata["max_results"] == 500
        assert validated.requests_per_minute == self.plugin.DEFAULT_REQUESTS_PER_MINUTE

    def test_validate_configuration_preserves_requests_per_minute(self) -> None:
        """Provided rate limits should be preserved."""
        config = self.base_config.model_copy(
            update={"requests_per_minute": 20},
        )
        validated = self.plugin.validate_configuration(config)

        assert validated.requests_per_minute == 20

    def test_validate_configuration_requires_query(self) -> None:
        """Missing query should raise a validation error."""
        config = self.base_config.model_copy(
            update={"metadata": {**self.base_config.metadata, "query": ""}},
        )
        with pytest.raises(ValueError):
            self.plugin.validate_configuration(config)

    def test_validate_configuration_rejects_invalid_date_format(self) -> None:
        """Dates must follow YYYY/MM/DD format."""
        config = self.base_config.model_copy(
            update={
                "metadata": {**self.base_config.metadata, "date_from": "2020-01-01"},
            },
        )
        with pytest.raises(ValueError):
            self.plugin.validate_configuration(config)

    def test_validate_configuration_rejects_invalid_range(self) -> None:
        """date_from must be before date_to."""
        config = self.base_config.model_copy(
            update={
                "metadata": {
                    **self.base_config.metadata,
                    "date_from": "2024/02/01",
                    "date_to": "2024/01/01",
                },
            },
        )
        with pytest.raises(ValueError):
            self.plugin.validate_configuration(config)

    def test_validate_configuration_normalizes_domain_context(self) -> None:
        """Domain context should be normalized and persisted."""
        config = self.base_config.model_copy(
            update={
                "metadata": {
                    **self.base_config.metadata,
                    "domain_context": "  Cardiology  ",
                },
            },
        )

        validated = self.plugin.validate_configuration(config)

        assert validated.metadata["domain_context"] == "cardiology"
