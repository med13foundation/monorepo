"""Graph-core contracts for graph-connection prompt dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class GraphConnectorExtension(Protocol):
    """Pack-owned connector dispatch semantics for graph-connection adapters."""

    @property
    def default_source_type(self) -> str:
        """Return the default connector source type."""

    @property
    def system_prompts_by_source_type(self) -> dict[str, str]:
        """Return connector prompts keyed by source type."""

    def supported_source_types(self) -> frozenset[str]:
        """Return supported connector source types."""

    def resolve_source_type(self, source_type: str | None) -> str:
        """Resolve one optional source type into a connector source type."""

    def system_prompt_for(self, source_type: str) -> str | None:
        """Return the system prompt for one connector source type."""

    def step_key_for(self, source_type: str) -> str:
        """Return the replay step key for one connector source type."""


@dataclass(frozen=True)
class GraphConnectionPromptConfig:
    """Pack-owned prompt selection config for graph-connection adapters."""

    default_source_type: str
    system_prompts_by_source_type: dict[str, str]
    step_key_prefix: str = "graph.connection"

    def supported_source_types(self) -> frozenset[str]:
        return frozenset(self.system_prompts_by_source_type)

    def resolve_source_type(self, source_type: str | None) -> str:
        if isinstance(source_type, str):
            normalized = source_type.strip().lower()
            if normalized:
                return normalized
        return self.default_source_type

    def system_prompt_for(self, source_type: str) -> str | None:
        return self.system_prompts_by_source_type.get(source_type.strip().lower())

    def step_key_for(self, source_type: str) -> str:
        normalized = source_type.strip().lower()
        return f"{self.step_key_prefix}.{normalized}.v1"
