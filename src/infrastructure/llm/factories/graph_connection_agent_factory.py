"""Factory for graph-connection agents."""

from __future__ import annotations

import json
import logging
import time
from inspect import isawaitable
from typing import TYPE_CHECKING, TypeGuard

from flujo.agents import make_agent_async
from flujo.domain.agent_result import FlujoAgentResult
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits as PydanticAIUsageLimits

from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_connection import GraphConnectionContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.factories._graph_connection_env_helpers import (
    resolve_graph_connection_max_retries,
    resolve_graph_connection_timeout_seconds,
    resolve_graph_connection_usage_limits,
)
from src.infrastructure.llm.factories.base_factory import BaseAgentFactory, FlujoAgent
from src.infrastructure.llm.prompts.graph_connection import (
    CLINVAR_GRAPH_CONNECTION_SYSTEM_PROMPT,
    PUBMED_GRAPH_CONNECTION_SYSTEM_PROMPT,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_GRAPH_CONNECTION_PROMPTS: dict[str, str] = {
    "clinvar": CLINVAR_GRAPH_CONNECTION_SYSTEM_PROMPT,
    "pubmed": PUBMED_GRAPH_CONNECTION_SYSTEM_PROMPT,
}
SUPPORTED_GRAPH_CONNECTION_SOURCES = frozenset(_GRAPH_CONNECTION_PROMPTS)
logger = logging.getLogger(__name__)
_GRAPH_CONNECTION_REQUEST_LIMIT = 960
_GRAPH_CONNECTION_TOOL_CALL_LIMIT = 1920
_ENV_GRAPH_CONNECTION_REQUEST_LIMIT = "MED13_GRAPH_CONNECTION_REQUEST_LIMIT"
_ENV_GRAPH_CONNECTION_TOOL_CALL_LIMIT = "MED13_GRAPH_CONNECTION_TOOL_CALL_LIMIT"
_ENV_GRAPH_CONNECTION_TIMEOUT_SECONDS = "MED13_GRAPH_CONNECTION_TIMEOUT_SECONDS"
_ENV_GRAPH_CONNECTION_MAX_RETRIES = "MED13_GRAPH_CONNECTION_MAX_RETRIES"


class _GraphConnectionUsageGuard:
    """Wrap graph-connection agents with conservative per-run usage limits."""

    def __init__(  # noqa: PLR0913
        self,
        delegate: FlujoAgent,
        *,
        request_limit: int = _GRAPH_CONNECTION_REQUEST_LIMIT,
        tool_calls_limit: int = _GRAPH_CONNECTION_TOOL_CALL_LIMIT,
        timeout_seconds: int = 30,
        max_retries: int = 1,
        source_type: str = "unknown",
        model_id: str | None = None,
    ) -> None:
        self._delegate = delegate
        self._request_limit = request_limit
        self._tool_calls_limit = tool_calls_limit
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._source_type = source_type
        self._model_id = model_id

    @property
    def _agent(self) -> object:
        """Prevent Flujo runner unwrapping from bypassing this guard."""
        return self

    async def run(self, *args: object, **kwargs: object) -> object:
        diagnostics = self._build_run_diagnostics(args=args, kwargs=kwargs)
        started_at = time.monotonic()
        logger.info(
            "Graph-connection agent invocation started",
            extra=diagnostics,
        )
        self._ensure_usage_limits(kwargs)
        run_callable = self._resolve_delegate_run_callable()
        try:
            result = run_callable(*args, **kwargs)
            if isawaitable(result):
                result = await result
        except UsageLimitExceeded as exc:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            logger.warning(
                "Graph-connection agent invocation exceeded usage limits",
                extra={
                    **diagnostics,
                    "graph_run_scenario": "usage_limit_exceeded",
                    "graph_run_duration_ms": duration_ms,
                    "graph_run_error": str(exc),
                },
            )
            return self._handle_usage_limit_exception(kwargs.get("context"), exc)
        except Exception as exc:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            scenario = self._classify_runtime_exception(exc)
            logger.warning(
                "Graph-connection agent invocation raised runtime exception",
                extra={
                    **diagnostics,
                    "graph_run_scenario": scenario,
                    "graph_run_duration_ms": duration_ms,
                    "graph_run_exception_type": type(exc).__name__,
                    "graph_run_error": str(exc),
                },
            )
            if self._is_control_flow_exception(exc):
                raise
            return self._handle_runtime_exception(kwargs.get("context"), exc)
        else:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            logger.info(
                "Graph-connection agent invocation completed",
                extra={
                    **diagnostics,
                    "graph_run_scenario": "completed",
                    "graph_run_duration_ms": duration_ms,
                },
            )
            return self._normalize_output_for_flujo(result)

    async def run_async(self, *args: object, **kwargs: object) -> object:
        return await self.run(*args, **kwargs)

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)

    def _ensure_usage_limits(self, kwargs: dict[str, object]) -> None:
        if kwargs.get("usage_limits") is not None:
            return
        kwargs["usage_limits"] = PydanticAIUsageLimits(
            request_limit=self._request_limit,
            tool_calls_limit=self._tool_calls_limit,
        )

    def _resolve_delegate_run_callable(self) -> Callable[..., object]:
        run_callable = getattr(self._delegate, "run", None)
        if _is_run_callable(run_callable):
            return run_callable
        msg = "Graph-connection delegate does not expose a callable run method"
        raise TypeError(msg)

    def _handle_usage_limit_exception(
        self,
        context_obj: object,
        exc: UsageLimitExceeded,
    ) -> object:
        fallback = self._build_usage_limit_fallback(context_obj, str(exc))
        if fallback is None:
            raise exc
        logger.info(
            "Graph-connection usage cap reached; returning fallback contract. %s",
            exc,
        )
        return self._normalize_graph_output(fallback)

    def _handle_runtime_exception(
        self,
        context_obj: object,
        exc: Exception,
    ) -> object:
        message = str(exc)
        if self._is_usage_limit_error(exc, message):
            fallback = self._build_usage_limit_fallback(context_obj, message)
            if fallback is not None:
                logger.info(
                    "Graph-connection usage cap reached via wrapped runner; "
                    "returning fallback contract. %s",
                    exc,
                )
                return self._normalize_graph_output(fallback)
        fallback = self._build_runtime_fallback(context_obj, message)
        if fallback is not None:
            logger.info(
                "Graph-connection agent failed; returning fallback contract. %s",
                exc,
            )
            return self._normalize_graph_output(fallback)
        raise exc

    def _normalize_output_for_flujo(self, result: object) -> object:
        if isinstance(result, FlujoAgentResult):
            return self._normalize_graph_output(result.output)
        return self._normalize_graph_output(result)

    @staticmethod
    def _normalize_graph_output(output: object) -> object:
        if isinstance(output, GraphConnectionContract):
            payload = output.model_dump(mode="json")
            return json.dumps(payload, ensure_ascii=True, sort_keys=True)
        return output

    @staticmethod
    def _is_control_flow_exception(exc: Exception) -> bool:
        return type(exc).__name__ in {"PausedException", "PipelineAbortSignal"}

    @staticmethod
    def _is_usage_limit_error(exc: Exception, message: str) -> bool:
        exception_name = type(exc).__name__
        if exception_name in {"UsageLimitExceeded", "UsageLimitExceededError"}:
            return True
        lowered = message.lower()
        return any(
            token in lowered
            for token in (
                "usagelimitexceeded",
                "request_limit",
                "tool_calls_limit",
                "usage limit",
                "would exceed the",
            )
        )

    @staticmethod
    def _classify_runtime_exception(exc: Exception) -> str:
        if isinstance(exc, TimeoutError):
            return "timeout_error"
        exception_name = type(exc).__name__
        lowered = str(exc).lower()
        if "timeout" in lowered or "deadline" in lowered:
            return "timeout_error"
        if exception_name in {"UsageLimitExceeded", "UsageLimitExceededError"}:
            return "usage_limit_exceeded"
        if exception_name == "ValidationError":
            return "output_validation_error"
        return "runtime_exception"

    def _build_run_diagnostics(
        self,
        *,
        args: tuple[object, ...],
        kwargs: dict[str, object],
    ) -> dict[str, object]:
        first_arg = args[0] if args else None
        input_chars = len(first_arg) if isinstance(first_arg, str) else 0
        context_obj = kwargs.get("context")
        relation_types_obj = getattr(context_obj, "relation_types", None)
        relation_type_count = (
            len(relation_types_obj) if isinstance(relation_types_obj, list) else 0
        )
        return {
            "graph_source_type": self._source_type,
            "graph_model_id": self._model_id,
            "graph_timeout_seconds": self._timeout_seconds,
            "graph_max_retries": self._max_retries,
            "graph_request_limit": self._request_limit,
            "graph_tool_calls_limit": self._tool_calls_limit,
            "graph_input_chars": input_chars,
            "graph_seed_entity_id": getattr(context_obj, "seed_entity_id", None),
            "graph_research_space_id": getattr(context_obj, "research_space_id", None),
            "graph_shadow_mode": getattr(context_obj, "shadow_mode", None),
            "graph_max_depth": getattr(context_obj, "max_depth", None),
            "graph_relation_type_count": relation_type_count,
            "graph_usage_limits_injected": kwargs.get("usage_limits") is None,
        }

    @classmethod
    def _build_runtime_fallback(
        cls,
        context_obj: object,
        reason: str,
    ) -> GraphConnectionContract | None:
        fallback = cls._build_usage_limit_fallback(context_obj, reason)
        if fallback is None:
            return None
        fallback.confidence_score = 0.2
        fallback.rationale = (
            "Graph-connection agent failed; returning deterministic fallback "
            "without writes."
        )
        return fallback

    @staticmethod
    def _build_usage_limit_fallback(
        context_obj: object,
        reason: str,
    ) -> GraphConnectionContract | None:
        source_type = getattr(context_obj, "source_type", None)
        research_space_id = getattr(context_obj, "research_space_id", None)
        seed_entity_id = getattr(context_obj, "seed_entity_id", None)
        shadow_mode = getattr(context_obj, "shadow_mode", None)
        run_id = getattr(context_obj, "run_id", None)

        if not isinstance(source_type, str) or not source_type.strip():
            return None
        if not isinstance(research_space_id, str) or not research_space_id.strip():
            return None
        if not isinstance(seed_entity_id, str) or not seed_entity_id.strip():
            return None
        if not isinstance(shadow_mode, bool):
            shadow_mode = True

        agent_run_id = None
        if isinstance(run_id, str):
            normalized_run_id = run_id.strip()
            if normalized_run_id:
                agent_run_id = normalized_run_id

        return GraphConnectionContract(
            decision="fallback",
            confidence_score=0.25,
            rationale=(
                "Graph-connection request budget reached; "
                "returning deterministic fallback without writes."
            ),
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator="graph_connection_usage_guard",
                    excerpt=f"Usage limit reached: {reason}",
                    relevance=0.8,
                ),
            ],
            source_type=source_type.strip(),
            research_space_id=research_space_id.strip(),
            seed_entity_id=seed_entity_id.strip(),
            proposed_relations=[],
            rejected_candidates=[],
            shadow_mode=shadow_mode,
            agent_run_id=agent_run_id,
        )


def _is_run_callable(value: object) -> TypeGuard[Callable[..., object]]:
    return callable(value)


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
    resolved_timeout_seconds = resolve_graph_connection_timeout_seconds(
        model_spec=model_spec,
        timeout_env=_ENV_GRAPH_CONNECTION_TIMEOUT_SECONDS,
    )
    resolved_max_retries = resolve_graph_connection_max_retries(
        model_spec=model_spec,
        fallback=max_retries,
        retries_env=_ENV_GRAPH_CONNECTION_MAX_RETRIES,
    )
    request_limit, tool_calls_limit = resolve_graph_connection_usage_limits(
        request_limit_default=_GRAPH_CONNECTION_REQUEST_LIMIT,
        tool_calls_limit_default=_GRAPH_CONNECTION_TOOL_CALL_LIMIT,
        request_limit_env=_ENV_GRAPH_CONNECTION_REQUEST_LIMIT,
        tool_calls_limit_env=_ENV_GRAPH_CONNECTION_TOOL_CALL_LIMIT,
    )
    reasoning_settings = model_spec.get_reasoning_settings()
    if reasoning_settings:
        agent = make_agent_async(
            model=model_spec.model_id,
            system_prompt=prompt,
            output_type=GraphConnectionContract,
            max_retries=resolved_max_retries,
            timeout=resolved_timeout_seconds,
            model_settings=reasoning_settings,
            tools=tools or [],
        )
        return _GraphConnectionUsageGuard(
            agent,
            request_limit=request_limit,
            tool_calls_limit=tool_calls_limit,
            timeout_seconds=resolved_timeout_seconds,
            max_retries=resolved_max_retries,
            source_type=normalized_source,
            model_id=model_spec.model_id,
        )
    agent = make_agent_async(
        model=model_spec.model_id,
        system_prompt=prompt,
        output_type=GraphConnectionContract,
        max_retries=resolved_max_retries,
        timeout=resolved_timeout_seconds,
        tools=tools or [],
    )
    return _GraphConnectionUsageGuard(
        agent,
        request_limit=request_limit,
        tool_calls_limit=tool_calls_limit,
        timeout_seconds=resolved_timeout_seconds,
        max_retries=resolved_max_retries,
        source_type=normalized_source,
        model_id=model_spec.model_id,
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


def create_pubmed_graph_connection_agent(
    model: str | None = None,
    max_retries: int = 3,
    tools: list[object] | None = None,
) -> FlujoAgent:
    """Create a PubMed graph-connection agent."""
    return create_graph_connection_agent_for_source(
        source_type="pubmed",
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
    "create_pubmed_graph_connection_agent",
    "create_graph_connection_agent_for_source",
    "get_graph_connection_system_prompt",
]
