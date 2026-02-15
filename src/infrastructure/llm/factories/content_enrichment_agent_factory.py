"""Factory for content-enrichment agents."""

from __future__ import annotations

from flujo.agents import make_agent_async

from src.domain.agents.contracts.content_enrichment import ContentEnrichmentContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.factories.base_factory import BaseAgentFactory, FlujoAgent
from src.infrastructure.llm.prompts.content_enrichment import (
    CONTENT_ENRICHMENT_SYSTEM_PROMPT,
)


def _get_model_spec(model_id: str | None = None) -> ModelSpec:
    """Resolve model spec for content enrichment."""
    registry = get_model_registry()
    if model_id:
        try:
            return registry.get_model(model_id)
        except KeyError:
            return registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
    return registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)


def create_content_enrichment_agent(
    model: str | None = None,
    max_retries: int = 3,
    system_prompt: str | None = None,
    tools: list[object] | None = None,
) -> FlujoAgent:
    """Create content-enrichment agent configured for tool-driven acquisition."""
    prompt = system_prompt or CONTENT_ENRICHMENT_SYSTEM_PROMPT
    model_spec = _get_model_spec(model)
    reasoning_settings = model_spec.get_reasoning_settings()

    if reasoning_settings:
        return make_agent_async(
            model=model_spec.model_id,
            system_prompt=prompt,
            output_type=ContentEnrichmentContract,
            max_retries=model_spec.max_retries,
            timeout=int(model_spec.timeout_seconds),
            model_settings=reasoning_settings,
            tools=tools or [],
        )

    return make_agent_async(
        model=model_spec.model_id,
        system_prompt=prompt,
        output_type=ContentEnrichmentContract,
        max_retries=max_retries,
        tools=tools or [],
    )


class ContentEnrichmentAgentFactory(BaseAgentFactory[ContentEnrichmentContract]):
    """Class-based factory for content-enrichment agents."""

    @property
    def output_type(self) -> type[ContentEnrichmentContract]:
        return ContentEnrichmentContract

    def get_system_prompt(self) -> str:
        return CONTENT_ENRICHMENT_SYSTEM_PROMPT


__all__ = ["ContentEnrichmentAgentFactory", "create_content_enrichment_agent"]
