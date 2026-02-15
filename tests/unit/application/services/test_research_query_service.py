"""Unit tests for interface-layer ResearchQueryService."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.services.research_query_service import ResearchQueryService
from src.domain.entities.kernel.dictionary import DictionarySearchResult


@dataclass
class StubDictionaryService:
    """Dictionary stub that returns fixed search responses."""

    results: list[DictionarySearchResult]

    def dictionary_search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
    ) -> list[DictionarySearchResult]:
        _ = terms
        _ = dimensions
        _ = domain_context
        _ = limit
        return self.results


def _build_search_results() -> list[DictionarySearchResult]:
    return [
        DictionarySearchResult(
            dimension="entity_types",
            entry_id="GENE",
            display_name="Gene",
            description="Gene entity",
            domain_context="genomics",
            match_method="exact",
            similarity_score=1.0,
            metadata={},
        ),
        DictionarySearchResult(
            dimension="relation_types",
            entry_id="ASSOCIATED_WITH",
            display_name="Associated With",
            description="Association relation",
            domain_context="genomics",
            match_method="exact",
            similarity_score=1.0,
            metadata={},
        ),
        DictionarySearchResult(
            dimension="variables",
            entry_id="VAR_CARDIAC_PHENOTYPE",
            display_name="Cardiac Phenotype",
            description="Cardiac phenotype flag",
            domain_context="clinical",
            match_method="vector",
            similarity_score=0.82,
            metadata={},
        ),
    ]


def test_parse_intent_resolves_dictionary_dimensions() -> None:
    service = ResearchQueryService(
        dictionary_service=StubDictionaryService(_build_search_results()),
    )

    intent = service.parse_intent(
        question="What genes are associated with cardiac phenotypes?",
        research_space_id="space-1",
    )

    assert "GENE" in intent.requested_entity_types
    assert intent.requested_relation_types == ["ASSOCIATED_WITH"]
    assert intent.requested_variable_ids == ["VAR_CARDIAC_PHENOTYPE"]
    assert intent.domain_context == "genomics"
    assert intent.ambiguous is False


def test_build_query_plan_clamps_defaults() -> None:
    service = ResearchQueryService(
        dictionary_service=StubDictionaryService(_build_search_results()),
    )
    intent = service.parse_intent(
        question="Find players traded to new teams in 2025",
        research_space_id="space-2",
    )

    plan = service.build_query_plan(intent=intent, max_depth=99, top_k=999)

    assert plan.max_depth == 4
    assert plan.top_k == 100
    assert "Deterministic plan" in plan.plan_summary
