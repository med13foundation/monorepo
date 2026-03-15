"""Biomedical dictionary loading extension wiring."""

from __future__ import annotations

from src.graph.core.dictionary_loading_extension import (
    GraphDictionaryLoadingConfig,
    GraphDictionaryLoadingExtension,
)
from src.graph.domain_biomedical.dictionary_domain_contexts import (
    BIOMEDICAL_DICTIONARY_DOMAIN_CONTEXTS,
)
from src.graph.domain_biomedical.dictionary_relations import (
    BIOMEDICAL_BUILTIN_RELATION_SYNONYMS,
    BIOMEDICAL_BUILTIN_RELATION_TYPES,
)

BIOMEDICAL_DICTIONARY_LOADING_EXTENSION = GraphDictionaryLoadingConfig(
    builtin_domain_contexts=BIOMEDICAL_DICTIONARY_DOMAIN_CONTEXTS,
    builtin_relation_types=BIOMEDICAL_BUILTIN_RELATION_TYPES,
    builtin_relation_synonyms=BIOMEDICAL_BUILTIN_RELATION_SYNONYMS,
)


def get_biomedical_dictionary_loading_extension() -> GraphDictionaryLoadingExtension:
    """Return the biomedical-pack dictionary loading extension."""
    return BIOMEDICAL_DICTIONARY_LOADING_EXTENSION
