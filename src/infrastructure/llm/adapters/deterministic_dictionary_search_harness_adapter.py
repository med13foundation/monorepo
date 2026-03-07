"""Deterministic dictionary search harness used when AI orchestration is disabled."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.ports.dictionary_search_harness_port import DictionarySearchHarnessPort

if TYPE_CHECKING:
    from src.domain.entities.kernel.dictionary import DictionarySearchResult
    from src.domain.ports.text_embedding_port import TextEmbeddingPort
    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )


class DeterministicDictionarySearchHarnessAdapter(DictionarySearchHarnessPort):
    """Use repository-backed dictionary search without Artana orchestration."""

    def __init__(
        self,
        *,
        dictionary_repo: DictionaryRepository,
        embedding_provider: TextEmbeddingPort | None = None,
    ) -> None:
        self._dictionary = dictionary_repo
        self._embedding_provider = embedding_provider

    def search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        normalized_terms = [
            term.strip() for term in terms if isinstance(term, str) and term.strip()
        ]
        if not normalized_terms:
            return []

        return self._dictionary.search_dictionary(
            terms=normalized_terms,
            dimensions=dimensions,
            domain_context=domain_context,
            limit=limit,
            query_embeddings=None,
            include_inactive=include_inactive,
        )
