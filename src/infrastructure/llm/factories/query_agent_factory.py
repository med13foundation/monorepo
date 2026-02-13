"""
Factory for query generation agents.

Creates agents optimized for generating search queries
for various data sources (PubMed, ClinVar, etc.).
"""

from __future__ import annotations

from flujo.agents import make_agent_async

from src.domain.agents.contracts.query_generation import QueryGenerationContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.factories.base_factory import BaseAgentFactory, FlujoAgent
from src.infrastructure.llm.prompts.query import CLINVAR_QUERY_SYSTEM_PROMPT
from src.infrastructure.llm.prompts.query.pubmed import PUBMED_QUERY_SYSTEM_PROMPT

_QUERY_SYSTEM_PROMPTS: dict[str, str] = {
    "pubmed": PUBMED_QUERY_SYSTEM_PROMPT,
    "clinvar": CLINVAR_QUERY_SYSTEM_PROMPT,
}
SUPPORTED_QUERY_SOURCES = frozenset(_QUERY_SYSTEM_PROMPTS)


def get_query_system_prompt(source_type: str) -> str:
    """Return the registered system prompt for a source type."""
    return _QUERY_SYSTEM_PROMPTS.get(source_type.lower(), "")


def _get_model_spec(model_id: str | None = None) -> ModelSpec:
    """Return a model spec by ID, falling back to defaults if unavailable."""
    registry = get_model_registry()
    if model_id:
        try:
            return registry.get_model(model_id)
        except KeyError:
            return registry.get_default_model(ModelCapability.QUERY_GENERATION)
    return registry.get_default_model(ModelCapability.QUERY_GENERATION)


def create_query_agent_for_source(
    source_type: str,
    model: str | None = None,
    max_retries: int = 3,
    system_prompt: str | None = None,
) -> FlujoAgent:
    """
    Create a query-generation agent for a specific source type.

    This centralizes source-specific prompt selection and allows easy
    extension when adding new connectors.

    Args:
        source_type: Data source type (e.g., "pubmed")
        model: Optional model ID override
        max_retries: Retry count
        system_prompt: Optional direct prompt override

    Returns:
        Configured agent for the selected source type

    Raises:
        ValueError: If source_type is unknown
    """
    normalized_source = source_type.lower()
    prompt = system_prompt or get_query_system_prompt(normalized_source)

    if not prompt:
        error_message = f"Unsupported source type for query agent: {normalized_source}"
        raise ValueError(error_message)

    model_spec = _get_model_spec(model)

    # Handle reasoning models with special settings
    reasoning_settings = model_spec.get_reasoning_settings()

    if reasoning_settings:
        return make_agent_async(
            model=model_spec.model_id,
            system_prompt=prompt,
            output_type=QueryGenerationContract,
            max_retries=model_spec.max_retries,
            timeout=int(model_spec.timeout_seconds),
            model_settings=reasoning_settings,
        )

    return make_agent_async(
        model=model_spec.model_id,
        system_prompt=prompt,
        output_type=QueryGenerationContract,
        max_retries=max_retries,
    )


def create_pubmed_query_agent(
    model: str | None = None,
    max_retries: int = 3,
) -> FlujoAgent:
    """
    Factory function for PubMed query generation agent.

    Creates an agent optimized for generating PubMed Boolean queries
    with evidence-first output schema.

    Args:
        model: Optional model ID override (defaults to registry default)
        max_retries: Number of retries for failed calls

    Returns:
        Configured agent for PubMed query generation
    """
    return create_query_agent_for_source(
        source_type="pubmed",
        model=model,
        max_retries=max_retries,
    )


def create_clinvar_query_agent(
    model: str | None = None,
    max_retries: int = 3,
) -> FlujoAgent:
    """
    Factory function for ClinVar query generation agent.

    Creates an agent optimized for generating ClinVar variant queries.

    Args:
        model: Optional model ID override (defaults to registry default)
        max_retries: Number of retries for failed calls

    Returns:
        Configured agent for ClinVar query generation
    """
    return create_query_agent_for_source(
        source_type="clinvar",
        model=model,
        max_retries=max_retries,
    )


class QueryAgentFactory(BaseAgentFactory[QueryGenerationContract]):
    """
    Factory for query generation agents.

    Provides class-based factory pattern for creating query agents
    with configurable source-specific prompts.
    """

    def __init__(
        self,
        source_type: str = "pubmed",
        model: str | None = None,
        max_retries: int = 3,
    ) -> None:
        """
        Initialize the query agent factory.

        Args:
            source_type: Data source type (pubmed, clinvar, etc.)
            model: Default model ID to use (loads from registry if None)
            max_retries: Default retry count for agent calls
        """
        super().__init__(
            default_model=model,  # Base class handles registry lookup
            max_retries=max_retries,
        )
        self._source_type = source_type
        self._prompts = dict(_QUERY_SYSTEM_PROMPTS)

    @property
    def output_type(self) -> type[QueryGenerationContract]:
        """Return the output type for query agents."""
        return QueryGenerationContract

    def get_system_prompt(self) -> str:
        """Return the system prompt for the configured source type."""
        return self._prompts.get(
            self._source_type.lower(),
            self._prompts["pubmed"],  # Default to PubMed
        )

    @classmethod
    def for_pubmed(cls, model: str | None = None) -> QueryAgentFactory:
        """Create a factory for PubMed query agents."""
        return cls(source_type="pubmed", model=model)

    @classmethod
    def for_source(
        cls,
        source_type: str,
        model: str | None = None,
    ) -> QueryAgentFactory:
        """Create a factory for a specific source type."""
        return cls(source_type=source_type, model=model)
