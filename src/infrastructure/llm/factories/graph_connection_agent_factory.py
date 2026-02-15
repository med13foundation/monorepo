"""Factory for graph-connection agents."""

from __future__ import annotations

from flujo.agents import make_agent_async

from src.domain.agents.contracts.graph_connection import GraphConnectionContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.factories.base_factory import BaseAgentFactory, FlujoAgent
from src.infrastructure.llm.prompts.graph_connection import (
    CLINVAR_GRAPH_CONNECTION_SYSTEM_PROMPT,
)

_GRAPH_CONNECTION_PROMPTS: dict[str, str] = {
    "clinvar": CLINVAR_GRAPH_CONNECTION_SYSTEM_PROMPT,
}
SUPPORTED_GRAPH_CONNECTION_SOURCES = frozenset(_GRAPH_CONNECTION_PROMPTS)


def get_graph_connection_system_prompt(source_type: str) -> str:
    """Return the registered prompt for a graph-connection source."""
    return _GRAPH_CONNECTION_PROMPTS.get(source_type.lower(), "")


def _get_model_spec(model_id: str | None = None) -> ModelSpec:
    """Resolve the model spec for graph-connection generation."""
    registry = get_model_registry()
    if model_id:
        try:
            return registry.get_model(model_id)
        except KeyError:
            return registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
    return registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)


def create_graph_connection_agent_for_source(
    source_type: str,
    model: str | None = None,
    max_retries: int = 3,
    system_prompt: str | None = None,
    tools: list[object] | None = None,
) -> FlujoAgent:
    """Create a graph-connection agent for a supported source type."""
    normalized_source = source_type.lower()
    prompt = system_prompt or get_graph_connection_system_prompt(normalized_source)
    if not prompt:
        msg = f"Unsupported source type for graph connection: {normalized_source}"
        raise ValueError(msg)

    model_spec = _get_model_spec(model)
    reasoning_settings = model_spec.get_reasoning_settings()
    if reasoning_settings:
        return make_agent_async(
            model=model_spec.model_id,
            system_prompt=prompt,
            output_type=GraphConnectionContract,
            max_retries=model_spec.max_retries,
            timeout=int(model_spec.timeout_seconds),
            model_settings=reasoning_settings,
            tools=tools or [],
        )
    return make_agent_async(
        model=model_spec.model_id,
        system_prompt=prompt,
        output_type=GraphConnectionContract,
        max_retries=max_retries,
        tools=tools or [],
    )


def create_clinvar_graph_connection_agent(
    model: str | None = None,
    max_retries: int = 3,
    tools: list[object] | None = None,
) -> FlujoAgent:
    """Create a ClinVar graph-connection agent."""
    return create_graph_connection_agent_for_source(
        source_type="clinvar",
        model=model,
        max_retries=max_retries,
        tools=tools,
    )


class GraphConnectionAgentFactory(BaseAgentFactory[GraphConnectionContract]):
    """Class-based factory for graph-connection agents."""

    def __init__(
        self,
        source_type: str = "clinvar",
        model: str | None = None,
        max_retries: int = 3,
    ) -> None:
        super().__init__(default_model=model, max_retries=max_retries)
        self._source_type = source_type
        self._prompts = dict(_GRAPH_CONNECTION_PROMPTS)

    @property
    def output_type(self) -> type[GraphConnectionContract]:
        return GraphConnectionContract

    def get_system_prompt(self) -> str:
        return self._prompts.get(
            self._source_type.lower(),
            self._prompts["clinvar"],
        )


__all__ = [
    "GraphConnectionAgentFactory",
    "SUPPORTED_GRAPH_CONNECTION_SOURCES",
    "create_clinvar_graph_connection_agent",
    "create_graph_connection_agent_for_source",
    "get_graph_connection_system_prompt",
]
