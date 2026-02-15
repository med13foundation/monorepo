"""Graph search output contract for read-only graph query workflows."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.domain.agents.contracts.base import BaseAgentContract


class EvidenceChainItem(BaseModel):
    """One provenance-linked evidence reference backing a search result."""

    provenance_id: str | None = Field(default=None, min_length=1, max_length=64)
    relation_id: str | None = Field(default=None, min_length=1, max_length=64)
    observation_id: str | None = Field(default=None, min_length=1, max_length=64)
    evidence_tier: str | None = Field(default=None, min_length=1, max_length=32)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_ref: str | None = Field(default=None, max_length=1024)


class GraphSearchResultEntry(BaseModel):
    """One ranked graph search result."""

    entity_id: str = Field(..., min_length=1, max_length=64)
    entity_type: str = Field(..., min_length=1, max_length=64)
    display_label: str | None = Field(default=None, max_length=512)
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    matching_observation_ids: list[str] = Field(default_factory=list)
    matching_relation_ids: list[str] = Field(default_factory=list)
    evidence_chain: list[EvidenceChainItem] = Field(default_factory=list)
    explanation: str = Field(..., min_length=1, max_length=4000)
    support_summary: str = Field(..., min_length=1, max_length=1000)


class GraphSearchContract(BaseAgentContract):
    """Contract for Graph Search Agent outputs."""

    decision: Literal["generated", "fallback", "escalate"] = Field(
        ...,
        description="Outcome of the graph-search run",
    )
    research_space_id: str = Field(..., min_length=1, max_length=64)
    original_query: str = Field(..., min_length=1, max_length=2000)
    interpreted_intent: str = Field(..., min_length=1, max_length=2000)
    query_plan_summary: str = Field(..., min_length=1, max_length=4000)
    total_results: int = Field(default=0, ge=0)
    results: list[GraphSearchResultEntry] = Field(default_factory=list)
    executed_path: Literal["deterministic", "agent", "agent_fallback"] = Field(
        default="deterministic",
    )
    warnings: list[str] = Field(default_factory=list)
    agent_run_id: str | None = Field(default=None, max_length=128)


__all__ = [
    "EvidenceChainItem",
    "GraphSearchContract",
    "GraphSearchResultEntry",
]
