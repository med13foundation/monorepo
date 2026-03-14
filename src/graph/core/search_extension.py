"""Extension contracts for pack-owned graph search semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class GraphSearchExtension(Protocol):
    """Pack-owned graph search semantics consumed by runtime adapters."""

    @property
    def system_prompt(self) -> str:
        """Return the prompt used by graph-search adapters."""

    @property
    def step_key(self) -> str:
        """Return the step key emitted by graph-search execution."""


@dataclass(frozen=True)
class GraphSearchConfig:
    """Default graph search extension configuration."""

    system_prompt: str
    step_key: str = "graph.search.v1"
