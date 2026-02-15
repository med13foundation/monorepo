"""Factory for entity-recognition agents."""

from __future__ import annotations

from flujo.agents import make_agent_async

from src.domain.agents.contracts.entity_recognition import EntityRecognitionContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.factories.base_factory import BaseAgentFactory, FlujoAgent
from src.infrastructure.llm.prompts.entity_recognition import (
    CLINVAR_ENTITY_RECOGNITION_SYSTEM_PROMPT,
)

_ENTITY_RECOGNITION_PROMPTS: dict[str, str] = {
    "clinvar": CLINVAR_ENTITY_RECOGNITION_SYSTEM_PROMPT,
}
SUPPORTED_ENTITY_RECOGNITION_SOURCES = frozenset(_ENTITY_RECOGNITION_PROMPTS)


def get_entity_recognition_system_prompt(source_type: str) -> str:
    """Return the registered prompt for an entity-recognition source."""
    return _ENTITY_RECOGNITION_PROMPTS.get(source_type.lower(), "")


def _get_model_spec(model_id: str | None = None) -> ModelSpec:
    """Resolve the model spec for entity recognition."""
    registry = get_model_registry()
    if model_id:
        try:
            return registry.get_model(model_id)
        except KeyError:
            return registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
    return registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)


def create_entity_recognition_agent_for_source(
    source_type: str,
    model: str | None = None,
    max_retries: int = 3,
    system_prompt: str | None = None,
    tools: list[object] | None = None,
) -> FlujoAgent:
    """
    Create an entity-recognition agent for a supported source type.
    """
    normalized_source = source_type.lower()
    prompt = system_prompt or get_entity_recognition_system_prompt(normalized_source)

    if not prompt:
        msg = f"Unsupported source type for entity recognition: {normalized_source}"
        raise ValueError(msg)

    model_spec = _get_model_spec(model)
    reasoning_settings = model_spec.get_reasoning_settings()
    if reasoning_settings:
        return make_agent_async(
            model=model_spec.model_id,
            system_prompt=prompt,
            output_type=EntityRecognitionContract,
            max_retries=model_spec.max_retries,
            timeout=int(model_spec.timeout_seconds),
            model_settings=reasoning_settings,
            tools=tools or [],
        )

    return make_agent_async(
        model=model_spec.model_id,
        system_prompt=prompt,
        output_type=EntityRecognitionContract,
        max_retries=max_retries,
        tools=tools or [],
    )


def create_clinvar_entity_recognition_agent(
    model: str | None = None,
    max_retries: int = 3,
    tools: list[object] | None = None,
) -> FlujoAgent:
    """Create a ClinVar entity-recognition agent."""
    return create_entity_recognition_agent_for_source(
        source_type="clinvar",
        model=model,
        max_retries=max_retries,
        tools=tools,
    )


class EntityRecognitionAgentFactory(BaseAgentFactory[EntityRecognitionContract]):
    """Class-based factory for entity-recognition agents."""

    def __init__(
        self,
        source_type: str = "clinvar",
        model: str | None = None,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            default_model=model,
            max_retries=max_retries,
        )
        self._source_type = source_type
        self._prompts = dict(_ENTITY_RECOGNITION_PROMPTS)

    @property
    def output_type(self) -> type[EntityRecognitionContract]:
        return EntityRecognitionContract

    def get_system_prompt(self) -> str:
        return self._prompts.get(
            self._source_type.lower(),
            self._prompts["clinvar"],
        )
