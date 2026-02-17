"""Factory for extraction agents."""

from __future__ import annotations

import os
from inspect import isawaitable

from flujo.agents import make_agent_async
from pydantic_ai.usage import UsageLimits as PydanticAIUsageLimits

from src.domain.agents.contracts.extraction import ExtractionContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.factories.base_factory import BaseAgentFactory, FlujoAgent
from src.infrastructure.llm.prompts.extraction import (
    CLINVAR_EXTRACTION_SYSTEM_PROMPT,
    PUBMED_EXTRACTION_SYSTEM_PROMPT,
)

_EXTRACTION_PROMPTS: dict[str, str] = {
    "clinvar": CLINVAR_EXTRACTION_SYSTEM_PROMPT,
    "pubmed": PUBMED_EXTRACTION_SYSTEM_PROMPT,
}
SUPPORTED_EXTRACTION_SOURCES = frozenset(_EXTRACTION_PROMPTS)
_DEFAULT_EXTRACTION_REQUEST_LIMIT = 120
_DEFAULT_EXTRACTION_TOOL_CALL_LIMIT = 240
_ENV_EXTRACTION_REQUEST_LIMIT = "MED13_EXTRACTION_REQUEST_LIMIT"
_ENV_EXTRACTION_TOOL_CALL_LIMIT = "MED13_EXTRACTION_TOOL_CALL_LIMIT"


class _ExtractionUsageGuard:
    """Wrap extraction agents with explicit per-run usage limits."""

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
            msg = "Extraction delegate does not expose a callable run method"
            raise TypeError(msg)
        result = run_callable(*args, **kwargs)
        if isawaitable(result):
            result = await result
        return result

    async def run_async(self, *args: object, **kwargs: object) -> object:
        return await self.run(*args, **kwargs)

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)


def get_extraction_system_prompt(source_type: str) -> str:
    """Return the registered prompt for an extraction source."""
    return _EXTRACTION_PROMPTS.get(source_type.lower(), "")


def _get_model_spec(model_id: str | None = None) -> ModelSpec:
    """Resolve the model spec for extraction."""
    registry = get_model_registry()
    if model_id:
        try:
            return registry.get_model(model_id)
        except KeyError:
            return registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
    return registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)


def create_extraction_agent_for_source(
    source_type: str,
    model: str | None = None,
    max_retries: int = 3,
    system_prompt: str | None = None,
    tools: list[object] | None = None,
) -> FlujoAgent:
    """Create an extraction agent for a supported source type."""
    normalized_source = source_type.lower()
    prompt = system_prompt or get_extraction_system_prompt(normalized_source)
    if not prompt:
        msg = f"Unsupported source type for extraction: {normalized_source}"
        raise ValueError(msg)

    model_spec = _get_model_spec(model)
    request_limit, tool_calls_limit = _resolve_extraction_usage_limits()
    reasoning_settings = model_spec.get_reasoning_settings()
    if reasoning_settings:
        agent = make_agent_async(
            model=model_spec.model_id,
            system_prompt=prompt,
            output_type=ExtractionContract,
            max_retries=model_spec.max_retries,
            timeout=int(model_spec.timeout_seconds),
            model_settings=reasoning_settings,
            tools=tools or [],
        )
        return _ExtractionUsageGuard(
            agent,
            request_limit=request_limit,
            tool_calls_limit=tool_calls_limit,
        )
    agent = make_agent_async(
        model=model_spec.model_id,
        system_prompt=prompt,
        output_type=ExtractionContract,
        max_retries=max_retries,
        tools=tools or [],
    )
    return _ExtractionUsageGuard(
        agent,
        request_limit=request_limit,
        tool_calls_limit=tool_calls_limit,
    )


def _resolve_extraction_usage_limits() -> tuple[int, int]:
    request_limit = _read_positive_int_from_env(
        name=_ENV_EXTRACTION_REQUEST_LIMIT,
        default=_DEFAULT_EXTRACTION_REQUEST_LIMIT,
    )
    tool_calls_limit = _read_positive_int_from_env(
        name=_ENV_EXTRACTION_TOOL_CALL_LIMIT,
        default=_DEFAULT_EXTRACTION_TOOL_CALL_LIMIT,
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


def create_clinvar_extraction_agent(
    model: str | None = None,
    max_retries: int = 3,
    tools: list[object] | None = None,
) -> FlujoAgent:
    """Create a ClinVar extraction agent."""
    return create_extraction_agent_for_source(
        source_type="clinvar",
        model=model,
        max_retries=max_retries,
        tools=tools,
    )


def create_pubmed_extraction_agent(
    model: str | None = None,
    max_retries: int = 3,
    tools: list[object] | None = None,
) -> FlujoAgent:
    """Create a PubMed extraction agent."""
    return create_extraction_agent_for_source(
        source_type="pubmed",
        model=model,
        max_retries=max_retries,
        tools=tools,
    )


class ExtractionAgentFactory(BaseAgentFactory[ExtractionContract]):
    """Class-based factory for extraction agents."""

    def __init__(
        self,
        source_type: str = "clinvar",
        model: str | None = None,
        max_retries: int = 3,
    ) -> None:
        super().__init__(default_model=model, max_retries=max_retries)
        self._source_type = source_type
        self._prompts = dict(_EXTRACTION_PROMPTS)

    @property
    def output_type(self) -> type[ExtractionContract]:
        return ExtractionContract

    def get_system_prompt(self) -> str:
        return self._prompts.get(
            self._source_type.lower(),
            self._prompts["clinvar"],
        )
