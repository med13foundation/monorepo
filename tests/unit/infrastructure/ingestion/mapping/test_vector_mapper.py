"""Unit tests for vector-based ingestion mapping."""

from __future__ import annotations

from src.domain.entities.kernel.dictionary import DictionarySearchResult
from src.infrastructure.ingestion.mapping import ExactMapper, HybridMapper, VectorMapper
from src.type_definitions.ingestion import RawRecord


class StubDictionaryService:
    """Dictionary stub for exact and vector mapping paths."""

    def __init__(
        self,
        *,
        search_results_by_term: dict[str, list[DictionarySearchResult]],
    ) -> None:
        self._search_results_by_term = search_results_by_term
        self.resolve_synonym_calls: list[str] = []
        self.dictionary_search_calls: list[dict[str, object]] = []

    def resolve_synonym(
        self,
        synonym: str,
        *,
        domain_context: str | None = None,
        include_inactive: bool = False,
    ) -> None:
        _ = domain_context
        _ = include_inactive
        self.resolve_synonym_calls.append(synonym)

    def dictionary_search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        _ = include_inactive
        self.dictionary_search_calls.append(
            {
                "terms": list(terms),
                "dimensions": list(dimensions) if dimensions is not None else None,
                "domain_context": domain_context,
                "limit": limit,
            },
        )
        first_term = terms[0] if terms else ""
        return list(self._search_results_by_term.get(first_term, []))


def _build_vector_result(
    *,
    variable_id: str,
    similarity: float,
) -> DictionarySearchResult:
    return DictionarySearchResult(
        dimension="variables",
        entry_id=variable_id,
        display_name="Cardiomegaly Indicator",
        description="Indicator for enlarged heart findings",
        domain_context="clinical",
        match_method="vector",
        similarity_score=similarity,
        metadata={"canonical_name": "cardiomegaly_indicator"},
    )


def test_vector_mapper_maps_when_similarity_meets_threshold() -> None:
    dictionary_service = StubDictionaryService(
        search_results_by_term={
            "enlarged heart": [
                _build_vector_result(variable_id="VAR_CARDIOMEGALY", similarity=0.92),
            ],
        },
    )
    mapper = VectorMapper(
        dictionary_service,
        similarity_threshold=0.7,
        top_k=5,
    )
    record = RawRecord(
        source_id="source-1",
        data={"pmid": "123456", "enlarged heart": True},
        metadata={"type": "pubmed", "entity_type": "PUBLICATION"},
    )

    observations = mapper.map(record)

    assert len(observations) == 1
    observation = observations[0]
    assert observation.variable_id == "VAR_CARDIOMEGALY"
    assert observation.subject_anchor == {"pmid": "123456"}
    assert observation.provenance["method"] == "vector_match"
    assert observation.provenance["similarity_score"] == 0.92
    assert dictionary_service.dictionary_search_calls[0]["limit"] == 5
    assert dictionary_service.dictionary_search_calls[0]["domain_context"] == "clinical"


def test_vector_mapper_skips_when_similarity_is_below_threshold() -> None:
    dictionary_service = StubDictionaryService(
        search_results_by_term={
            "enlarged heart": [
                _build_vector_result(variable_id="VAR_CARDIOMEGALY", similarity=0.61),
            ],
        },
    )
    mapper = VectorMapper(
        dictionary_service,
        similarity_threshold=0.7,
        top_k=5,
    )
    record = RawRecord(
        source_id="source-1",
        data={"enlarged heart": True},
        metadata={"entity_type": "PUBLICATION"},
    )

    observations = mapper.map(record)

    assert observations == []


def test_hybrid_mapper_falls_back_from_exact_to_vector() -> None:
    dictionary_service = StubDictionaryService(
        search_results_by_term={
            "enlarged heart": [
                _build_vector_result(variable_id="VAR_CARDIOMEGALY", similarity=0.88),
            ],
        },
    )
    hybrid_mapper = HybridMapper(
        [
            ExactMapper(dictionary_service),
            VectorMapper(dictionary_service, similarity_threshold=0.7, top_k=5),
        ],
    )
    record = RawRecord(
        source_id="source-1",
        data={"pmid": "123456", "enlarged heart": True},
        metadata={"type": "pubmed", "entity_type": "PUBLICATION"},
    )

    observations = hybrid_mapper.map(record)

    assert len(observations) == 1
    assert observations[0].variable_id == "VAR_CARDIOMEGALY"
    assert "enlarged heart" in dictionary_service.resolve_synonym_calls
    assert dictionary_service.dictionary_search_calls


def test_vector_mapper_skips_low_value_pubmed_metadata_fields() -> None:
    dictionary_service = StubDictionaryService(
        search_results_by_term={},
    )
    mapper = VectorMapper(dictionary_service, similarity_threshold=0.7, top_k=5)
    record = RawRecord(
        source_id="source-1",
        data={
            "pmid": "123456",
            "title": "Mediator kinase module paper",
            "abstract": "Long abstract text",
            "publication_date": "2024-01-01",
            "journal": "Nature",
        },
        metadata={"type": "pubmed", "entity_type": "PUBLICATION"},
    )

    observations = mapper.map(record)
    metrics = mapper.consume_run_metrics()

    assert observations == []
    assert dictionary_service.dictionary_search_calls == []
    assert metrics is not None
    assert metrics["searched_field_count"] == 0
    assert metrics["skipped_field_count"] == 5


def test_vector_mapper_caches_dictionary_searches_across_records() -> None:
    dictionary_service = StubDictionaryService(
        search_results_by_term={
            "enlarged heart": [
                _build_vector_result(variable_id="VAR_CARDIOMEGALY", similarity=0.92),
            ],
        },
    )
    mapper = VectorMapper(dictionary_service, similarity_threshold=0.7, top_k=5)
    record = RawRecord(
        source_id="source-1",
        data={"enlarged heart": True},
        metadata={"entity_type": "PUBLICATION"},
    )

    first_observations = mapper.map(record)
    first_metrics = mapper.consume_run_metrics()
    second_observations = mapper.map(record)
    second_metrics = mapper.consume_run_metrics()

    assert len(first_observations) == 1
    assert len(second_observations) == 1
    assert len(dictionary_service.dictionary_search_calls) == 1
    assert first_metrics is not None
    assert second_metrics is not None
    assert first_metrics["cache_hit_count"] == 0
    assert first_metrics["cache_miss_count"] == 1
    assert second_metrics["cache_hit_count"] == 1
    assert second_metrics["cache_miss_count"] == 0
