"""Factory helpers for selecting the dictionary search harness implementation."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from src.infrastructure.llm.adapters.deterministic_dictionary_search_harness_adapter import (
    DeterministicDictionarySearchHarnessAdapter,
)
from src.infrastructure.llm.adapters.dictionary_search_harness_adapter import (
    ArtanaDictionarySearchHarnessAdapter,
)

if TYPE_CHECKING:
    from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
    from src.domain.ports.dictionary_search_harness_port import (
        DictionarySearchHarnessPort,
    )
    from src.domain.ports.text_embedding_port import TextEmbeddingPort
    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )

_ENV_ENABLE_ARTANA_DICTIONARY_SEARCH_HARNESS = (
    "MED13_ENABLE_ARTANA_DICTIONARY_SEARCH_HARNESS"
)


def create_dictionary_search_harness(
    *,
    dictionary_repo: DictionaryRepository,
    embedding_provider: TextEmbeddingPort | None,
    mapping_judge_agent: MappingJudgePort | None = None,
) -> DictionarySearchHarnessPort:
    """Build the configured dictionary search harness implementation."""
    if os.getenv(_ENV_ENABLE_ARTANA_DICTIONARY_SEARCH_HARNESS, "1").strip() != "1":
        return DeterministicDictionarySearchHarnessAdapter(
            dictionary_repo=dictionary_repo,
            embedding_provider=embedding_provider,
        )

    return ArtanaDictionarySearchHarnessAdapter(
        dictionary_repo=dictionary_repo,
        embedding_provider=embedding_provider,
        mapping_judge_agent=mapping_judge_agent,
    )
