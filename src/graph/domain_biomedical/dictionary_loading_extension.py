"""Biomedical dictionary loading extension wiring."""

from __future__ import annotations

from src.graph.core.dictionary_loading_extension import (
    GraphDictionaryLoadingConfig,
    GraphDictionaryLoadingExtension,
)
from src.graph.domain_biomedical.dictionary_domain_contexts import (
    BIOMEDICAL_DICTIONARY_DOMAIN_CONTEXTS,
)

BIOMEDICAL_DICTIONARY_LOADING_EXTENSION = GraphDictionaryLoadingConfig(
    builtin_domain_contexts=BIOMEDICAL_DICTIONARY_DOMAIN_CONTEXTS,
)


def get_biomedical_dictionary_loading_extension() -> GraphDictionaryLoadingExtension:
    """Return the biomedical-pack dictionary loading extension."""
    return BIOMEDICAL_DICTIONARY_LOADING_EXTENSION
