"""Factory for Mapping Judge agents."""

from __future__ import annotations

from flujo.agents import make_agent_async

from src.domain.agents.contracts.mapping_judge import MappingJudgeContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.factories.base_factory import BaseAgentFactory, FlujoAgent
from src.infrastructure.llm.prompts.mapping_judge import MAPPING_JUDGE_SYSTEM_PROMPT


def _get_model_spec(model_id: str | None = None) -> ModelSpec:
    registry = get_model_registry()
    if model_id:
        try:
            return registry.get_model(model_id)
        except KeyError:
            return registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
    return registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)


def create_mapping_judge_agent(
    model: str | None = None,
    max_retries: int = 2,
    system_prompt: str | None = None,
) -> FlujoAgent:
    """Create a lightweight classification agent for ambiguous mapping decisions."""
    prompt = system_prompt or MAPPING_JUDGE_SYSTEM_PROMPT
    model_spec = _get_model_spec(model)
    reasoning_settings = model_spec.get_reasoning_settings()

    if reasoning_settings:
        return make_agent_async(
            model=model_spec.model_id,
            system_prompt=prompt,
            output_type=MappingJudgeContract,
            max_retries=model_spec.max_retries,
            timeout=int(model_spec.timeout_seconds),
            model_settings=reasoning_settings,
        )

    return make_agent_async(
        model=model_spec.model_id,
        system_prompt=prompt,
        output_type=MappingJudgeContract,
        max_retries=max_retries,
    )


class MappingJudgeAgentFactory(BaseAgentFactory[MappingJudgeContract]):
    """Class-based factory for Mapping Judge agents."""

    @property
    def output_type(self) -> type[MappingJudgeContract]:
        return MappingJudgeContract

    def get_system_prompt(self) -> str:
        return MAPPING_JUDGE_SYSTEM_PROMPT


__all__ = ["MappingJudgeAgentFactory", "create_mapping_judge_agent"]
