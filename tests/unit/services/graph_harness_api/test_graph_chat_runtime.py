"""Unit tests for graph-chat verification and answer synthesis."""

from __future__ import annotations

import asyncio

from services.graph_harness_api.graph_chat_runtime import (
    HarnessGraphChatRequest,
    HarnessGraphChatRunner,
)
from services.graph_harness_api.graph_search_runtime import HarnessGraphSearchResult
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_search import (
    GraphSearchContract,
    GraphSearchResultEntry,
)


class _StubGraphSearchRunner:
    def __init__(self, result: GraphSearchContract) -> None:
        self._result = result

    async def run(self, request: object) -> HarnessGraphSearchResult:
        del request
        return HarnessGraphSearchResult(
            contract=self._result,
            agent_run_id=self._result.agent_run_id,
            active_skill_names=("graph_harness.graph_grounding",),
        )


def _graph_chat_request() -> HarnessGraphChatRequest:
    return HarnessGraphChatRequest(
        question="What does MED13 do?",
        research_space_id="space-1",
        model_id=None,
        max_depth=2,
        top_k=10,
        include_evidence_chains=True,
        objective="Map MED13 mechanism evidence.",
        current_hypotheses=("MED13 regulates a transcriptional program.",),
        pending_questions=("What evidence should we review next?",),
        graph_snapshot_summary={"claim_count": 1},
    )


def _graph_search_result(
    *,
    relevance_score: float,
    warnings: list[str],
    matching_relation_ids: list[str],
) -> GraphSearchContract:
    return GraphSearchContract(
        decision="generated",
        confidence_score=relevance_score,
        rationale="Synthetic graph-search result.",
        evidence=[
            EvidenceItem(
                source_type="db",
                locator="entity:med13",
                excerpt="Synthetic MED13 evidence",
                relevance=relevance_score,
            ),
        ],
        research_space_id="space-1",
        original_query="What does MED13 do?",
        interpreted_intent="What does MED13 do?",
        query_plan_summary="Synthetic query plan.",
        total_results=1,
        results=[
            GraphSearchResultEntry(
                entity_id="entity-1",
                entity_type="gene",
                display_label="MED13",
                relevance_score=relevance_score,
                matching_observation_ids=["obs-1"],
                matching_relation_ids=matching_relation_ids,
                evidence_chain=[],
                explanation="Synthetic explanation.",
                support_summary="Synthetic support summary.",
            ),
        ],
        executed_path="agent",
        warnings=warnings,
        agent_run_id="graph_chat:test-search",
    )


def test_graph_chat_runner_marks_grounded_answers_verified() -> None:
    runner = HarnessGraphChatRunner(
        graph_search_runner=_StubGraphSearchRunner(
            _graph_search_result(
                relevance_score=0.91,
                warnings=[],
                matching_relation_ids=["rel-1"],
            ),
        ),
    )

    result = asyncio.run(runner.run(_graph_chat_request()))

    assert result.verification.status == "verified"
    assert result.verification.allows_graph_write is True
    assert result.graph_write_candidates == []
    assert result.fresh_literature is None
    assert result.answer_text.startswith("Grounded graph answer:")
    assert result.warnings == []


def test_graph_chat_runner_marks_warning_backed_answers_needs_review() -> None:
    runner = HarnessGraphChatRunner(
        graph_search_runner=_StubGraphSearchRunner(
            _graph_search_result(
                relevance_score=0.78,
                warnings=["Synthetic graph-search warning."],
                matching_relation_ids=["rel-1"],
            ),
        ),
    )

    result = asyncio.run(runner.run(_graph_chat_request()))

    assert result.verification.status == "needs_review"
    assert result.verification.allows_graph_write is False
    assert result.graph_write_candidates == []
    assert result.fresh_literature is None
    assert result.answer_text.startswith("Preliminary graph answer:")
    assert any(
        warning.startswith("Grounded-answer verification:")
        for warning in result.warnings
    )


def test_graph_chat_runner_marks_empty_results_unverified() -> None:
    runner = HarnessGraphChatRunner(
        graph_search_runner=_StubGraphSearchRunner(
            GraphSearchContract(
                decision="generated",
                confidence_score=0.22,
                rationale="Synthetic empty graph-search result.",
                evidence=[],
                research_space_id="space-1",
                original_query="What does MED13 do?",
                interpreted_intent="What does MED13 do?",
                query_plan_summary="Synthetic query plan.",
                total_results=0,
                results=[],
                executed_path="agent",
                warnings=[],
                agent_run_id="graph_chat:test-search-empty",
            ),
        ),
    )

    result = asyncio.run(runner.run(_graph_chat_request()))

    assert result.verification.status == "unverified"
    assert result.verification.allows_graph_write is False
    assert result.graph_write_candidates == []
    assert result.fresh_literature is None
    assert result.answer_text.startswith("I did not find grounded graph results")
