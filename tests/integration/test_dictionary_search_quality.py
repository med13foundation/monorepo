"""Integration coverage for dictionary search quality on PubMed-derived queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import pytest

from src.application.services.kernel.dictionary_management_service import (
    DictionaryManagementService,
)
from src.domain.ports.dictionary_search_harness_port import DictionarySearchHarnessPort
from src.domain.ports.text_embedding_port import TextEmbeddingPort
from src.infrastructure.repositories.kernel import SqlAlchemyDictionaryRepository
from src.models.database.kernel.dictionary import DictionaryDomainContextModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.domain.entities.kernel.dictionary import DictionarySearchResult


class PubMedKeywordEmbeddingProvider(TextEmbeddingPort):
    """Deterministic embedding provider that clusters known PubMed concept axes."""

    _AXIS_KEYWORDS: tuple[tuple[str, ...], ...] = (
        ("thyroid", "hormone", "transcription"),
        ("energy", "homeostasis", "metabolism", "systemic", "whole-body"),
        ("stress", "growth", "load", "enlargement", "hypertrophy"),
    )

    def embed_text(
        self,
        text: str,
        *,
        model_name: str,
    ) -> list[float] | None:
        del model_name
        normalized = text.strip().casefold()
        if not normalized:
            return None

        vector: list[float] = []
        for axis_keywords in self._AXIS_KEYWORDS:
            has_axis_signal = any(keyword in normalized for keyword in axis_keywords)
            vector.append(1.0 if has_axis_signal else 0.0)
        return vector


class StagedDictionarySearchHarness(DictionarySearchHarnessPort):
    """Test harness implementing direct-then-vector search without LLM planning."""

    def __init__(
        self,
        *,
        dictionary_repo: SqlAlchemyDictionaryRepository,
        embedding_provider: TextEmbeddingPort,
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
        direct_results = self._dictionary.search_dictionary(
            terms=terms,
            dimensions=dimensions,
            domain_context=domain_context,
            limit=limit,
            query_embeddings=None,
            include_inactive=include_inactive,
        )
        if any(
            result.match_method in {"exact", "synonym"} for result in direct_results
        ):
            return direct_results

        normalized_terms = [term.strip().casefold() for term in terms if term.strip()]
        embeddings: dict[str, list[float]] = {}
        for index, embedding in enumerate(
            self._embedding_provider.embed_texts(
                normalized_terms,
                model_name="text-embedding-3-small",
            ),
        ):
            if embedding is None:
                continue
            embeddings[normalized_terms[index]] = embedding
        if not embeddings:
            return direct_results
        vector_results = self._dictionary.search_dictionary(
            terms=terms,
            dimensions=dimensions,
            domain_context=domain_context,
            limit=limit,
            query_embeddings=embeddings,
            include_inactive=include_inactive,
        )
        return vector_results if vector_results else direct_results


@dataclass(frozen=True)
class SearchQualityCase:
    """Top-1 search expectation for one PubMed-derived query."""

    pmid: str
    article_title: str
    query_term: str
    expected_variable_id: str
    expected_match_method: Literal["synonym", "vector"]


def _ensure_domain_context(db_session: Session, domain_context: str) -> None:
    normalized = domain_context.strip().lower()
    existing = db_session.get(DictionaryDomainContextModel, normalized)
    if existing is not None:
        return
    db_session.add(
        DictionaryDomainContextModel(
            id=normalized,
            display_name=normalized.replace("_", " ").title(),
            description="Integration test domain context",
        ),
    )
    db_session.flush()


@pytest.mark.integration
def test_dictionary_search_returns_high_precision_for_pubmed_title_queries(
    db_session: Session,
) -> None:
    """Verify top-1 quality using three real PubMed article titles."""
    repository = SqlAlchemyDictionaryRepository(db_session)
    embedding_provider = PubMedKeywordEmbeddingProvider()
    service = DictionaryManagementService(
        dictionary_repo=repository,
        dictionary_search_harness=StagedDictionarySearchHarness(
            dictionary_repo=repository,
            embedding_provider=embedding_provider,
        ),
        embedding_provider=embedding_provider,
    )
    _ensure_domain_context(db_session, "clinical")

    service.create_variable(
        variable_id="VAR_PUBMED_30769017",
        canonical_name="cardiac_transcription_axis",
        display_name="Cardiac Transcription Axis",
        data_type="STRING",
        domain_context="clinical",
        description="Regulation of cardiac transcription by thyroid hormone and Med13.",
        created_by="manual:test",
        source_ref="pubmed:30769017",
    )
    service.create_synonym(
        variable_id="VAR_PUBMED_30769017",
        synonym="thyroid hormone med13 axis",
        source="pubmed:title",
        created_by="manual:test",
        source_ref="pubmed:30769017",
    )

    service.create_variable(
        variable_id="VAR_PUBMED_22541436",
        canonical_name="systemic_energy_homeostasis_axis",
        display_name="Systemic Energy Homeostasis Axis",
        data_type="STRING",
        domain_context="clinical",
        description=(
            "A cardiac microRNA governs systemic energy homeostasis "
            "by regulation of MED13."
        ),
        created_by="manual:test",
        source_ref="pubmed:22541436",
    )
    service.create_variable(
        variable_id="VAR_PUBMED_17379774",
        canonical_name="stress_growth_response_axis",
        display_name="Stress Growth Response Axis",
        data_type="STRING",
        domain_context="clinical",
        description=(
            "Control of stress-dependent cardiac growth and gene expression "
            "by a microRNA."
        ),
        created_by="manual:test",
        source_ref="pubmed:17379774",
    )

    cases = [
        SearchQualityCase(
            pmid="30769017",
            article_title=(
                "Regulation of cardiac transcription by thyroid hormone and Med13."
            ),
            query_term="thyroid hormone med13 axis",
            expected_variable_id="VAR_PUBMED_30769017",
            expected_match_method="synonym",
        ),
        SearchQualityCase(
            pmid="22541436",
            article_title=(
                "A cardiac microRNA governs systemic energy homeostasis "
                "by regulation of MED13."
            ),
            query_term="whole-body metabolism control in cardiomyocytes",
            expected_variable_id="VAR_PUBMED_22541436",
            expected_match_method="vector",
        ),
        SearchQualityCase(
            pmid="17379774",
            article_title=(
                "Control of stress-dependent cardiac growth and gene expression "
                "by a microRNA."
            ),
            query_term="adverse load induced heart enlargement response",
            expected_variable_id="VAR_PUBMED_17379774",
            expected_match_method="vector",
        ),
    ]

    correct_top_hits = 0
    for case in cases:
        results = service.dictionary_search(
            terms=[case.query_term],
            dimensions=["variables"],
            domain_context="clinical",
            limit=3,
        )

        assert results, (
            "Dictionary search returned no candidates for "
            f"PMID {case.pmid}: {case.article_title}"
        )
        top_result = results[0]
        if top_result.entry_id == case.expected_variable_id:
            correct_top_hits += 1

        assert top_result.entry_id == case.expected_variable_id
        assert top_result.match_method == case.expected_match_method

    top1_accuracy = correct_top_hits / len(cases)
    assert top1_accuracy == 1.0
