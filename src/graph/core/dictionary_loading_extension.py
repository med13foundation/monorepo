"""Extension contracts for pack-owned dictionary loading semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from src.graph.core.dictionary_domain_contexts import (
        DictionaryDomainContextDefinition,
    )


BuiltinRelationCategory = Literal[
    "core_causal",
    "extended_scientific",
    "document_governance",
]


@dataclass(frozen=True)
class BuiltinRelationTypeDefinition:
    """One pack-owned canonical relation type definition.

    The category is pack-owned classification metadata. It is not stored in the
    dictionary tables yet, but callers can use it to present simpler grouped
    views of relation vocabularies.
    """

    relation_type: str
    display_name: str
    description: str
    domain_context: str
    category: BuiltinRelationCategory
    is_directional: bool = True
    inverse_label: str | None = None


@dataclass(frozen=True)
class BuiltinRelationSynonymDefinition:
    """One pack-owned relation synonym definition."""

    relation_type: str
    synonym: str
    source: str | None = None


class GraphDictionaryLoadingExtension(Protocol):
    """Pack-owned dictionary loading semantics used by governance builders."""

    @property
    def builtin_domain_contexts(self) -> tuple[DictionaryDomainContextDefinition, ...]:
        """Return builtin dictionary domain contexts seeded by the pack."""

    @property
    def builtin_relation_types(self) -> tuple[BuiltinRelationTypeDefinition, ...]:
        """Return builtin canonical relation types seeded by the pack."""

    @property
    def builtin_relation_synonyms(
        self,
    ) -> tuple[BuiltinRelationSynonymDefinition, ...]:
        """Return builtin relation synonyms seeded by the pack."""


@dataclass(frozen=True)
class GraphDictionaryLoadingConfig:
    """Default dictionary loading extension configuration."""

    builtin_domain_contexts: tuple[DictionaryDomainContextDefinition, ...]
    builtin_relation_types: tuple[BuiltinRelationTypeDefinition, ...] = ()
    builtin_relation_synonyms: tuple[BuiltinRelationSynonymDefinition, ...] = ()
