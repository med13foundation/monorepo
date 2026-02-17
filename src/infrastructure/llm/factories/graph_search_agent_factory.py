"""Factory for Graph Search agents."""

from __future__ import annotations

import os
from inspect import isawaitable

from flujo.agents import make_agent_async
from pydantic_ai.usage import UsageLimits as PydanticAIUsageLimits

from src.domain.agents.contracts.graph_search import GraphSearchContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.factories.base_factory import BaseAgentFactory, FlujoAgent
from src.infrastructure.llm.prompts.graph_search import GRAPH_SEARCH_SYSTEM_PROMPT

_DEFAULT_GRAPH_SEARCH_REQUEST_LIMIT = 80
_DEFAULT_GRAPH_SEARCH_TOOL_CALL_LIMIT = 160
_ENV_GRAPH_SEARCH_REQUEST_LIMIT = "MED13_GRAPH_SEARCH_REQUEST_LIMIT"
_ENV_GRAPH_SEARCH_TOOL_CALL_LIMIT = "MED13_GRAPH_SEARCH_TOOL_CALL_LIMIT"


class _GraphSearchUsageGuard:
    """Wrap graph-search agents with explicit per-run usage limits."""

    def __init__(
        self,
        delegate: FlujoAgent,
        *,
        request_limit: int,
        tool_calls_limit: int,
    ) -> None:
        self._delegate = delegate
        self._request_limit = request_limit
        self._tool_calls_limit = tool_calls_limit

    @property
    def _agent(self) -> object:
        """Prevent Flujo runner unwrapping from bypassing this guard."""
        return self

    async def run(self, *args: object, **kwargs: object) -> object:
        if kwargs.get("usage_limits") is None:
            kwargs["usage_limits"] = PydanticAIUsageLimits(
                request_limit=self._request_limit,
                tool_calls_limit=self._tool_calls_limit,
            )
        run_callable = getattr(self._delegate, "run", None)
        if not callable(run_callable):
            msg = "Graph-search delegate does not expose a callable run method"
            raise TypeError(msg)
        result = run_callable(*args, **kwargs)
        if isawaitable(result):
            result = await result
        return result

    async def run_async(self, *args: object, **kwargs: object) -> object:
        return await self.run(*args, **kwargs)

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)


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
    request_limit, tool_calls_limit = _resolve_graph_search_usage_limits()
    reasoning_settings = model_spec.get_reasoning_settings()

    if reasoning_settings:
        agent = make_agent_async(
            model=model_spec.model_id,
            system_prompt=prompt,
            output_type=GraphSearchContract,
            max_retries=model_spec.max_retries,
            timeout=int(model_spec.timeout_seconds),
            model_settings=reasoning_settings,
            tools=tools or [],
        )
        return _GraphSearchUsageGuard(
            agent,
            request_limit=request_limit,
            tool_calls_limit=tool_calls_limit,
        )

    agent = make_agent_async(
        model=model_spec.model_id,
        system_prompt=prompt,
        output_type=GraphSearchContract,
        max_retries=max_retries,
        tools=tools or [],
    )
    return _GraphSearchUsageGuard(
        agent,
        request_limit=request_limit,
        tool_calls_limit=tool_calls_limit,
    )


def _resolve_graph_search_usage_limits() -> tuple[int, int]:
    request_limit = _read_positive_int_from_env(
        name=_ENV_GRAPH_SEARCH_REQUEST_LIMIT,
        default=_DEFAULT_GRAPH_SEARCH_REQUEST_LIMIT,
    )
    tool_calls_limit = _read_positive_int_from_env(
        name=_ENV_GRAPH_SEARCH_TOOL_CALL_LIMIT,
        default=_DEFAULT_GRAPH_SEARCH_TOOL_CALL_LIMIT,
    )
    return request_limit, tool_calls_limit


def _read_positive_int_from_env(*, name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip()
    if not normalized:
        return default
    if normalized.isdigit():
        parsed = int(normalized)
        return parsed if parsed > 0 else default
    return default


class GraphSearchAgentFactory(BaseAgentFactory[GraphSearchContract]):
    """Class-based factory for Graph Search agents."""

    @property
    def output_type(self) -> type[GraphSearchContract]:
        return GraphSearchContract

    def get_system_prompt(self) -> str:
        return GRAPH_SEARCH_SYSTEM_PROMPT


__all__ = ["GraphSearchAgentFactory", "create_graph_search_agent"]
