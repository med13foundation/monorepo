"""Unit tests for LLM judge ingestion mapper behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.mapping_judge import (
    MappingJudgeCandidate,
    MappingJudgeContract,
)
from src.domain.entities.kernel.dictionary import DictionarySearchResult
from src.infrastructure.ingestion.mapping.llm_judge_mapper import LLMJudgeMapper
from src.type_definitions.ingestion import RawRecord

if TYPE_CHECKING:
    from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext


class StubDictionaryService:
    """Dictionary stub returning configured search results per field key."""

    def __init__(
        self,
        *,
        search_results_by_term: dict[str, list[DictionarySearchResult]],
    ) -> None:
        self._search_results_by_term = search_results_by_term
        self.search_calls: list[dict[str, object]] = []

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
        self.search_calls.append(
            {
                "terms": list(terms),
                "dimensions": list(dimensions) if dimensions is not None else None,
                "domain_context": domain_context,
                "limit": limit,
            },
        )
        first_term = terms[0] if terms else ""
        return list(self._search_results_by_term.get(first_term, []))


class StubMappingJudgeAgent:
    """Mapping judge stub returning preconfigured decisions."""

    def __init__(self, *, decision: MappingJudgeContract) -> None:
        self._decision = decision
        self.seen_contexts: list[MappingJudgeContext] = []

    def judge(
        self,
        context: MappingJudgeContext,
        *,
        model_id: str | None = None,
    ) -> MappingJudgeContract:
        _ = model_id
        self.seen_contexts.append(context)
        return self._decision

    def close(self) -> None:
        return None


def _build_search_result(
    *,
    variable_id: str,
    method: Literal["fuzzy", "vector"],
    score: float,
) -> DictionarySearchResult:
    return DictionarySearchResult(
        dimension="variables",
        entry_id=variable_id,
        display_name="Cardiomegaly Marker",
        description="Marker for cardiomegaly",
        domain_context="clinical",
        match_method=method,
        similarity_score=score,
        metadata={"canonical_name": "cardiomegaly_marker"},
    )


def test_llm_judge_mapper_maps_when_judge_selects_candidate() -> None:
    dictionary_service = StubDictionaryService(
        search_results_by_term={
            "cardiomegaly markr": [
                _build_search_result(
                    variable_id="VAR_CARDIOMEGALY_MARKER",
                    method="fuzzy",
                    score=0.62,
                ),
            ],
        },
    )
    judge_decision = MappingJudgeContract(
        decision="matched",
        selected_variable_id="VAR_CARDIOMEGALY_MARKER",
        candidate_count=1,
        selection_rationale="Candidate best matches typo variant.",
        selected_candidate=MappingJudgeCandidate(
            variable_id="VAR_CARDIOMEGALY_MARKER",
            display_name="Cardiomegaly Marker",
            match_method="fuzzy",
            similarity_score=0.62,
            description="Marker for cardiomegaly",
            metadata={},
        ),
        confidence_score=0.84,
        rationale="Strong lexical match after typo correction.",
        evidence=[
            EvidenceItem(
                source_type="note",
                locator="mapping-judge:test",
                excerpt="Single candidate above floor.",
                relevance=0.8,
            ),
        ],
        agent_run_id="run-123",
    )
    mapper = LLMJudgeMapper(
        dictionary_service,
        StubMappingJudgeAgent(decision=judge_decision),
        candidate_floor=0.4,
        vector_threshold=0.7,
        top_k=5,
    )
    record = RawRecord(
        source_id="source-1",
        data={"pmid": "123456", "cardiomegaly markr": True},
        metadata={
            "type": "pubmed",
            "entity_type": "PUBLICATION",
            "domain_context": "clinical",
        },
    )

    observations = mapper.map(record)

    assert len(observations) == 1
    observation = observations[0]
    assert observation.variable_id == "VAR_CARDIOMEGALY_MARKER"
    assert observation.subject_anchor == {"pmid": "123456"}
    assert observation.provenance["method"] == "llm_judge"
    assert observation.provenance["judge_agent_run_id"] == "run-123"


def test_llm_judge_mapper_returns_empty_when_judge_declines_match() -> None:
    dictionary_service = StubDictionaryService(
        search_results_by_term={
            "cardiomegaly markr": [
                _build_search_result(
                    variable_id="VAR_CARDIOMEGALY_MARKER",
                    method="fuzzy",
                    score=0.62,
                ),
            ],
        },
    )
    judge_decision = MappingJudgeContract(
        decision="no_match",
        selected_variable_id=None,
        candidate_count=1,
        selection_rationale="Insufficient semantic confidence.",
        selected_candidate=None,
        confidence_score=0.31,
        rationale="No safe match.",
        evidence=[],
        agent_run_id="run-456",
    )
    mapper = LLMJudgeMapper(
        dictionary_service,
        StubMappingJudgeAgent(decision=judge_decision),
        candidate_floor=0.4,
        vector_threshold=0.7,
        top_k=5,
    )
    record = RawRecord(
        source_id="source-1",
        data={"cardiomegaly markr": True},
        metadata={"entity_type": "PUBLICATION", "domain_context": "clinical"},
    )

    observations = mapper.map(record)

    assert observations == []


def test_llm_judge_mapper_inferrs_domain_from_source_type() -> None:
    dictionary_service = StubDictionaryService(
        search_results_by_term={
            "cardiomegaly markr": [
                _build_search_result(
                    variable_id="VAR_CARDIOMEGALY_MARKER",
                    method="fuzzy",
                    score=0.62,
                ),
            ],
        },
    )
    judge_decision = MappingJudgeContract(
        decision="no_match",
        selected_variable_id=None,
        candidate_count=1,
        selection_rationale="No confident selection.",
        selected_candidate=None,
        confidence_score=0.2,
        rationale="Declined for safety.",
        evidence=[],
        agent_run_id="run-789",
    )
    mapper = LLMJudgeMapper(
        dictionary_service,
        StubMappingJudgeAgent(decision=judge_decision),
        candidate_floor=0.4,
        vector_threshold=0.7,
        top_k=5,
    )
    record = RawRecord(
        source_id="source-1",
        data={"cardiomegaly markr": True},
        metadata={"type": "pubmed", "entity_type": "PUBLICATION"},
    )

    _ = mapper.map(record)

    assert dictionary_service.search_calls[0]["domain_context"] == "clinical"
