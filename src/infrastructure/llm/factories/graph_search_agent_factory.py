"""Factory for Graph Search agents."""

from __future__ import annotations

from flujo.agents import make_agent_async

from src.domain.agents.contracts.graph_search import GraphSearchContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.factories.base_factory import BaseAgentFactory, FlujoAgent
from src.infrastructure.llm.prompts.graph_search import GRAPH_SEARCH_SYSTEM_PROMPT


def _get_model_spec(model_id: str | None = None) -> ModelSpec:
    """Resolve model spec for graph-search reasoning."""
    registry = get_model_registry()
    if model_id:
        try:
            return registry.get_model(model_id)
        except KeyError:
            return registry.get_default_model(ModelCapability.QUERY_GENERATION)
    return registry.get_default_model(ModelCapability.QUERY_GENERATION)


def create_graph_search_agent(
    model: str | None = None,
    max_retries: int = 3,
    system_prompt: str | None = None,
    tools: list[object] | None = None,
) -> FlujoAgent:
    """Create a graph-search agent configured for tool-driven reasoning."""
    prompt = system_prompt or GRAPH_SEARCH_SYSTEM_PROMPT
    model_spec = _get_model_spec(model)
    reasoning_settings = model_spec.get_reasoning_settings()

    if reasoning_settings:
        return make_agent_async(
            model=model_spec.model_id,
            system_prompt=prompt,
            output_type=GraphSearchContract,
            max_retries=model_spec.max_retries,
            timeout=int(model_spec.timeout_seconds),
            model_settings=reasoning_settings,
            tools=tools or [],
        )

    return make_agent_async(
        model=model_spec.model_id,
        system_prompt=prompt,
        output_type=GraphSearchContract,
        max_retries=max_retries,
        tools=tools or [],
    )


class GraphSearchAgentFactory(BaseAgentFactory[GraphSearchContract]):
    """Class-based factory for Graph Search agents."""

    @property
    def output_type(self) -> type[GraphSearchContract]:
        return GraphSearchContract

    def get_system_prompt(self) -> str:
        return GRAPH_SEARCH_SYSTEM_PROMPT


__all__ = ["GraphSearchAgentFactory", "create_graph_search_agent"]
