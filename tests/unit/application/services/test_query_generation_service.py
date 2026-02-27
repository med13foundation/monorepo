"""Tests for QueryGenerationService orchestration behavior."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.application.services.query_generation_service import (
    QueryGenerationRequest,
    QueryGenerationService,
    QueryGenerationServiceDependencies,
)
from src.domain.agents.contracts.query_generation import QueryGenerationContract
from src.domain.agents.ports.query_agent_port import QueryAgentPort


@dataclass(frozen=True)
class QueryAgentScenario:
    """Configured contract/run metadata returned by the stub agent."""

    contract: QueryGenerationContract
    run_id: str | None


class StubQueryAgent(QueryAgentPort):
    """Stub query-generation agent that captures invocation context."""

    def __init__(self, scenario: QueryAgentScenario) -> None:
        self._scenario = scenario
        self.calls: list[dict[str, object]] = []

    async def generate_query(  # noqa: PLR0913
        self,
        research_space_description: str,
        user_instructions: str,
        source_type: str,
        *,
        model_id: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
    ) -> QueryGenerationContract:
        self.calls.append(
            {
                "research_space_description": research_space_description,
                "user_instructions": user_instructions,
                "source_type": source_type,
                "model_id": model_id,
                "user_id": user_id,
                "correlation_id": correlation_id,
            },
        )
        return self._scenario.contract

    async def close(self) -> None:
        return None

    def get_last_run_id(self) -> str | None:
        return self._scenario.run_id


def _build_contract(
    *,
    decision: str,
    query: str,
    rationale: str,
    confidence: float,
    source_type: str = "pubmed",
) -> QueryGenerationContract:
    return QueryGenerationContract(
        decision=decision,
        confidence_score=confidence,
        rationale=rationale,
        evidence=[],
        query=query,
        source_type=source_type,
        query_complexity="simple",
    )


@pytest.mark.asyncio
async def test_resolve_query_returns_deterministic_fallback_when_ai_disabled() -> None:
    service = QueryGenerationService(
        dependencies=QueryGenerationServiceDependencies(),
    )

    result = await service.resolve_query(
        QueryGenerationRequest(
            base_query="MED13",
            source_type="pubmed",
            is_ai_managed=False,
        ),
    )

    assert result.query == "MED13"
    assert result.decision == "skipped"
    assert result.execution_mode == "deterministic"
    assert result.fallback_reason == "ai_query_generation_disabled_or_unavailable"
    assert result.run_id is None


@pytest.mark.asyncio
async def test_resolve_query_uses_agent_query_with_normalized_source_type() -> None:
    scenario = QueryAgentScenario(
        contract=_build_contract(
            decision="generated",
            query="gene:MED13",
            rationale="Structured ClinVar query",
            confidence=0.92,
            source_type="clinvar",
        ),
        run_id="run-query-123",
    )
    agent = StubQueryAgent(scenario)
    service = QueryGenerationService(
        dependencies=QueryGenerationServiceDependencies(query_agent=agent),
    )

    result = await service.resolve_query(
        QueryGenerationRequest(
            base_query="MED13",
            source_type="  CLINVAR  ",
            is_ai_managed=True,
            agent_prompt="Find variants tied to MED13",
            model_id="openai:gpt-5",
            use_research_space_context=False,
        ),
    )

    assert result.query == "gene:MED13"
    assert result.decision == "generated"
    assert result.execution_mode == "ai"
    assert result.fallback_reason is None
    assert result.run_id == "run-query-123"
    assert len(agent.calls) == 1
    assert agent.calls[0]["source_type"] == "clinvar"
    assert agent.calls[0]["model_id"] == "openai:gpt-5"


@pytest.mark.asyncio
async def test_resolve_query_reports_fallback_reason_from_agent() -> None:
    scenario = QueryAgentScenario(
        contract=_build_contract(
            decision="fallback",
            query="MED13 OR MED13L",
            rationale="insufficient_recall_with_base_query",
            confidence=0.64,
        ),
        run_id="run-query-456",
    )
    service = QueryGenerationService(
        dependencies=QueryGenerationServiceDependencies(
            query_agent=StubQueryAgent(scenario),
        ),
    )

    result = await service.resolve_query(
        QueryGenerationRequest(
            base_query="MED13",
            source_type="pubmed",
            is_ai_managed=True,
        ),
    )

    assert result.query == "MED13 OR MED13L"
    assert result.decision == "fallback"
    assert result.execution_mode == "ai"
    assert result.fallback_reason == "insufficient_recall_with_base_query"
    assert result.run_id == "run-query-456"


@pytest.mark.asyncio
async def test_resolve_query_reports_default_fallback_reason_for_empty_rationale() -> (
    None
):
    scenario = QueryAgentScenario(
        contract=_build_contract(
            decision="fallback",
            query="MED13",
            rationale="",
            confidence=0.51,
        ),
        run_id="run-query-789",
    )
    service = QueryGenerationService(
        dependencies=QueryGenerationServiceDependencies(
            query_agent=StubQueryAgent(scenario),
        ),
    )

    result = await service.resolve_query(
        QueryGenerationRequest(
            base_query="MED13",
            source_type="pubmed",
            is_ai_managed=True,
        ),
    )

    assert result.fallback_reason == "agent_returned_fallback"
