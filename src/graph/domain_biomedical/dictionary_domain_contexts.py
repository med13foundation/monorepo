"""Biomedical dictionary domain-context defaults."""

from __future__ import annotations

from src.graph.core.dictionary_domain_contexts import (
    DictionaryDomainContextDefinition,
)

BIOMEDICAL_DICTIONARY_DOMAIN_CONTEXTS = (
    DictionaryDomainContextDefinition(
        id="general",
        display_name="General",
        description="Domain-agnostic defaults for shared dictionary terms.",
    ),
    DictionaryDomainContextDefinition(
        id="clinical",
        display_name="Clinical",
        description="Clinical and biomedical literature domain context.",
    ),
    DictionaryDomainContextDefinition(
        id="genomics",
        display_name="Genomics",
        description="Genomics and variant interpretation domain context.",
    ),
)
