"""Factory for extraction relation-policy agents."""

from __future__ import annotations

from flujo.agents import make_agent_async

from src.domain.agents.contracts.extraction_policy import ExtractionPolicyContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.factories.base_factory import BaseAgentFactory, FlujoAgent
from src.infrastructure.llm.prompts.extraction import EXTRACTION_POLICY_SYSTEM_PROMPT


def _get_model_spec(model_id: str | None = None) -> ModelSpec:
    registry = get_model_registry()
    if model_id:
        try:
            return registry.get_model(model_id)
        except KeyError:
            return registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
    return registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)


def create_extraction_policy_agent(
    model: str | None = None,
    max_retries: int = 2,
    system_prompt: str | None = None,
) -> FlujoAgent:
    """Create the policy agent used for undefined relation patterns."""
    prompt = system_prompt or EXTRACTION_POLICY_SYSTEM_PROMPT
    model_spec = _get_model_spec(model)
    reasoning_settings = model_spec.get_reasoning_settings()

    if reasoning_settings:
        return make_agent_async(
            model=model_spec.model_id,
            system_prompt=prompt,
            output_type=ExtractionPolicyContract,
            max_retries=model_spec.max_retries,
            timeout=int(model_spec.timeout_seconds),
            model_settings=reasoning_settings,
        )

    return make_agent_async(
        model=model_spec.model_id,
        system_prompt=prompt,
        output_type=ExtractionPolicyContract,
        max_retries=max_retries,
    )


class ExtractionPolicyAgentFactory(BaseAgentFactory[ExtractionPolicyContract]):
    """Class-based factory for extraction policy agents."""

    @property
    def output_type(self) -> type[ExtractionPolicyContract]:
        return ExtractionPolicyContract

    def get_system_prompt(self) -> str:
        return EXTRACTION_POLICY_SYSTEM_PROMPT


__all__ = ["ExtractionPolicyAgentFactory", "create_extraction_policy_agent"]
