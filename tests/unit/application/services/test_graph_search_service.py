"""Unit tests for deterministic GraphSearchService orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from src.application.agents.services.graph_search_service import (
    GraphSearchService,
    GraphSearchServiceDependencies,
)
from src.application.services.research_query_service import ResearchQueryService
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_search import (
    GraphSearchContract,
    GraphSearchResultEntry,
)
from src.domain.entities.kernel.dictionary import DictionarySearchResult
from src.domain.entities.kernel.entities import KernelEntity
from src.domain.entities.kernel.observations import KernelObservation
from src.domain.entities.kernel.relations import KernelRelation, KernelRelationEvidence

if TYPE_CHECKING:
    from src.domain.agents.contexts.graph_search_context import GraphSearchContext


class StubDictionaryService:
    """Dictionary stub for search-term resolution."""

    def dictionary_search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        _ = terms
        _ = dimensions
        _ = domain_context
        _ = limit
        _ = include_inactive
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
                entry_id="VAR_CARDIOMYOPATHY",
                display_name="Cardiomyopathy",
                description="Cardiomyopathy indicator",
                domain_context="clinical",
                match_method="exact",
                similarity_score=1.0,
                metadata={},
            ),
        ]


class StubGraphQueryService:
    """Graph query stub with one valid and one rejected relation."""

    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.research_space_id = uuid4()
        self.entity = KernelEntity(
            id=uuid4(),
            research_space_id=self.research_space_id,
            entity_type="GENE",
            display_label="MED13",
            metadata_payload={},
            created_at=now,
            updated_at=now,
        )
        self.valid_relation = KernelRelation(
            id=uuid4(),
            research_space_id=self.research_space_id,
            source_id=self.entity.id,
            relation_type="ASSOCIATED_WITH",
            target_id=uuid4(),
            aggregate_confidence=0.91,
            source_count=2,
            highest_evidence_tier="LITERATURE",
            curation_status="APPROVED",
            provenance_id=uuid4(),
            reviewed_by=None,
            reviewed_at=None,
            created_at=now,
            updated_at=now,
        )
        self.rejected_relation = KernelRelation(
            id=uuid4(),
            research_space_id=self.research_space_id,
            source_id=self.entity.id,
            relation_type="ASSOCIATED_WITH",
            target_id=uuid4(),
            aggregate_confidence=0.4,
            source_count=1,
            highest_evidence_tier="COMPUTATIONAL",
            curation_status="REJECTED",
            provenance_id=uuid4(),
            reviewed_by=None,
            reviewed_at=None,
            created_at=now,
            updated_at=now,
        )
        self.observation = KernelObservation(
            id=uuid4(),
            research_space_id=self.research_space_id,
            subject_id=self.entity.id,
            variable_id="VAR_CARDIOMYOPATHY",
            value_numeric=None,
            value_text="present",
            value_date=None,
            value_coded=None,
            value_boolean=None,
            value_json=None,
            unit=None,
            observed_at=now,
            provenance_id=uuid4(),
            confidence=0.88,
            created_at=now,
            updated_at=now,
        )
        self.evidence = KernelRelationEvidence(
            id=uuid4(),
            relation_id=self.valid_relation.id,
            confidence=0.92,
            evidence_summary="Support from source document",
            evidence_sentence="MED13 is associated with cardiomyopathy in the cited cohort.",
            evidence_tier="LITERATURE",
            provenance_id=uuid4(),
            source_document_id=uuid4(),
            agent_run_id=None,
            created_at=now,
        )

    def graph_query_entities(
        self,
        *,
        research_space_id: str,
        entity_type: str | None = None,
        query_text: str | None = None,
        limit: int = 200,
    ) -> list[KernelEntity]:
        _ = entity_type
        _ = query_text
        _ = limit
        return [self.entity] if research_space_id == str(self.research_space_id) else []

    def graph_query_neighbourhood(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        depth: int = 1,
        relation_types: list[str] | None = None,
        limit: int = 200,
    ) -> list[KernelRelation]:
        _ = research_space_id
        _ = entity_id
        _ = depth
        _ = relation_types
        _ = limit
        return [self.valid_relation]

    def graph_query_shared_subjects(
        self,
        *,
        research_space_id: str,
        entity_id_a: str,
        entity_id_b: str,
        limit: int = 100,
    ) -> list[KernelEntity]:
        _ = research_space_id
        _ = entity_id_a
        _ = entity_id_b
        _ = limit
        return []

    def graph_query_observations(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        variable_ids: list[str] | None = None,
        limit: int = 200,
    ) -> list[KernelObservation]:
        _ = variable_ids
        _ = limit
        if research_space_id != str(self.research_space_id) or entity_id != str(
            self.entity.id,
        ):
            return []
        return [self.observation]

    def graph_query_relation_evidence(
        self,
        *,
        research_space_id: str,
        relation_id: str,
        limit: int = 200,
    ) -> list[KernelRelationEvidence]:
        _ = limit
        if research_space_id == str(self.research_space_id) and relation_id == str(
            self.valid_relation.id,
        ):
            return [self.evidence]
        return []

    def graph_query_relations(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        relation_types: list[str] | None = None,
        curation_statuses: list[str] | None = None,
        direction: str = "both",
        depth: int = 1,
        limit: int = 200,
    ) -> list[KernelRelation]:
        _ = relation_types
        _ = direction
        _ = depth
        _ = limit
        if research_space_id != str(self.research_space_id) or entity_id != str(
            self.entity.id,
        ):
            return []
        relations = [self.valid_relation, self.rejected_relation]
        if curation_statuses:
            allowed_statuses = {
                status.strip().upper() for status in curation_statuses if status.strip()
            }
            relations = [
                relation
                for relation in relations
                if relation.curation_status.strip().upper() in allowed_statuses
            ]
        return relations

    def graph_query_by_observation(
        self,
        *,
        research_space_id: str,
        variable_id: str,
        operator: str = "eq",
        value: object = None,
        limit: int = 200,
    ) -> list[KernelEntity]:
        _ = variable_id
        _ = operator
        _ = value
        _ = limit
        if research_space_id != str(self.research_space_id):
            return []
        return [self.entity]

    def graph_aggregate(
        self,
        *,
        research_space_id: str,
        variable_id: str,
        entity_type: str | None = None,
        aggregation: str = "count",
    ) -> dict[str, int | float | str | None]:
        _ = variable_id
        _ = entity_type
        if research_space_id != str(self.research_space_id):
            return {"aggregation": aggregation, "value": 0}
        return {"aggregation": aggregation, "value": 1}


class StubGraphSearchAgent:
    """Simple async graph-search port stub used by service tests."""

    def __init__(self, contract: GraphSearchContract) -> None:
        self._contract = contract
        self.calls = 0

    async def search(
        self,
        context: GraphSearchContext,
        *,
        model_id: str | None = None,
    ) -> GraphSearchContract:
        _ = context
        _ = model_id
        self.calls += 1
        return self._contract

    async def close(self) -> None:
        return None


def _build_agent_contract(research_space_id: str) -> GraphSearchContract:
    return GraphSearchContract(
        decision="generated",
        confidence_score=0.92,
        rationale="Agent synthesized graph evidence for the query.",
        evidence=[
            EvidenceItem(
                source_type="tool",
                locator=f"research_space:{research_space_id}",
                excerpt="Tool-backed graph traversal and evidence synthesis.",
                relevance=0.9,
            ),
        ],
        research_space_id=research_space_id,
        original_query="What evidence links MED13 to cardiomyopathy?",
        interpreted_intent="Find MED13 evidence linked to cardiomyopathy phenotypes.",
        query_plan_summary="Agent traversed MED13 neighborhood and ranked supports.",
        total_results=1,
        results=[
            GraphSearchResultEntry(
                entity_id=str(uuid4()),
                entity_type="GENE",
                display_label="MED13",
                relevance_score=0.95,
                matching_observation_ids=[],
                matching_relation_ids=[],
                evidence_chain=[],
                explanation="Strong matching relation and observation evidence.",
                support_summary="well_supported: independent_sources=1, confidence=0.95",
            ),
        ],
        executed_path="agent",
        warnings=[],
        agent_run_id="run-graph-search-1",
    )


async def test_graph_search_service_returns_ranked_results() -> None:
    graph_query_service = StubGraphQueryService()
    search_service = GraphSearchService(
        dependencies=GraphSearchServiceDependencies(
            research_query_service=ResearchQueryService(
                dictionary_service=StubDictionaryService(),
            ),
            graph_query_service=graph_query_service,
            graph_search_agent=None,
        ),
    )

    contract = await search_service.search(
        question="What genes are associated with cardiomyopathy?",
        research_space_id=str(graph_query_service.research_space_id),
        include_evidence_chains=True,
    )

    assert contract.decision == "generated"
    assert contract.executed_path == "deterministic"
    assert contract.total_results == 1
    assert contract.results[0].entity_id == str(graph_query_service.entity.id)
    assert contract.results[0].evidence_chain
    assert (
        contract.results[0].evidence_chain[0].evidence_sentence
        == "MED13 is associated with cardiomyopathy in the cited cohort."
    )


async def test_graph_search_force_agent_falls_back_when_unconfigured() -> None:
    graph_query_service = StubGraphQueryService()
    search_service = GraphSearchService(
        dependencies=GraphSearchServiceDependencies(
            research_query_service=ResearchQueryService(
                dictionary_service=StubDictionaryService(),
            ),
            graph_query_service=graph_query_service,
            graph_search_agent=None,
        ),
    )

    contract = await search_service.search(
        question="Find MED13 evidence",
        research_space_id=str(graph_query_service.research_space_id),
        force_agent=True,
    )

    assert contract.executed_path == "agent_fallback"
    assert contract.results
    assert (
        "force_agent was requested but no graph search agent is configured"
        in " ".join(
            contract.warnings,
        )
    )


async def test_graph_search_applies_curation_status_filters() -> None:
    graph_query_service = StubGraphQueryService()
    search_service = GraphSearchService(
        dependencies=GraphSearchServiceDependencies(
            research_query_service=ResearchQueryService(
                dictionary_service=StubDictionaryService(),
            ),
            graph_query_service=graph_query_service,
            graph_search_agent=None,
        ),
    )

    contract = await search_service.search(
        question="Find MED13 evidence",
        research_space_id=str(graph_query_service.research_space_id),
        curation_statuses=["APPROVED"],
    )

    assert contract.results
    matching_relation_ids = {
        relation_id
        for result in contract.results
        for relation_id in result.matching_relation_ids
    }
    assert str(graph_query_service.valid_relation.id) in matching_relation_ids
    assert str(graph_query_service.rejected_relation.id) not in matching_relation_ids


async def test_graph_search_uses_agent_when_deterministic_has_no_results() -> None:
    class EmptyGraphQueryService(StubGraphQueryService):
        def graph_query_entities(
            self,
            *,
            research_space_id: str,
            entity_type: str | None = None,
            query_text: str | None = None,
            limit: int = 200,
        ) -> list[KernelEntity]:
            _ = research_space_id
            _ = entity_type
            _ = query_text
            _ = limit
            return []

        def graph_query_by_observation(
            self,
            *,
            research_space_id: str,
            variable_id: str,
            operator: str = "eq",
            value: object = None,
            limit: int = 200,
        ) -> list[KernelEntity]:
            _ = research_space_id
            _ = variable_id
            _ = operator
            _ = value
            _ = limit
            return []

    graph_query_service = EmptyGraphQueryService()
    agent = StubGraphSearchAgent(
        _build_agent_contract(str(graph_query_service.research_space_id)),
    )
    search_service = GraphSearchService(
        dependencies=GraphSearchServiceDependencies(
            research_query_service=ResearchQueryService(
                dictionary_service=StubDictionaryService(),
            ),
            graph_query_service=graph_query_service,
            graph_search_agent=agent,
        ),
    )

    contract = await search_service.search(
        question="What evidence links MED13 to cardiomyopathy?",
        research_space_id=str(graph_query_service.research_space_id),
    )

    assert contract.executed_path == "agent"
    assert contract.total_results == 1
    assert agent.calls == 1


async def test_graph_search_force_agent_prefers_agent_results() -> None:
    graph_query_service = StubGraphQueryService()
    agent = StubGraphSearchAgent(
        _build_agent_contract(str(graph_query_service.research_space_id)),
    )
    search_service = GraphSearchService(
        dependencies=GraphSearchServiceDependencies(
            research_query_service=ResearchQueryService(
                dictionary_service=StubDictionaryService(),
            ),
            graph_query_service=graph_query_service,
            graph_search_agent=agent,
        ),
    )

    contract = await search_service.search(
        question="Find MED13 evidence",
        research_space_id=str(graph_query_service.research_space_id),
        force_agent=True,
    )

    assert contract.executed_path == "agent"
    assert contract.total_results == 1
    assert agent.calls == 1
