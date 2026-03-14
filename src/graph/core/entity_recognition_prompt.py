"""Graph-core contracts for entity-recognition prompt dispatch."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntityRecognitionPromptConfig:
    """Pack-owned prompt selection config for entity-recognition adapters."""

    system_prompts_by_source_type: dict[str, str]

    def supported_source_types(self) -> frozenset[str]:
        return frozenset(self.system_prompts_by_source_type)

    def system_prompt_for(self, source_type: str) -> str | None:
        return self.system_prompts_by_source_type.get(source_type)
