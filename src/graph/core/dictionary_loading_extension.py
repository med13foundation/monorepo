"""Extension contracts for pack-owned dictionary loading semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.graph.core.dictionary_domain_contexts import (
        DictionaryDomainContextDefinition,
    )


class GraphDictionaryLoadingExtension(Protocol):
    """Pack-owned dictionary loading semantics used by governance builders."""

    @property
    def builtin_domain_contexts(self) -> tuple[DictionaryDomainContextDefinition, ...]:
        """Return builtin dictionary domain contexts seeded by the pack."""


@dataclass(frozen=True)
class GraphDictionaryLoadingConfig:
    """Default dictionary loading extension configuration."""

    builtin_domain_contexts: tuple[DictionaryDomainContextDefinition, ...]
