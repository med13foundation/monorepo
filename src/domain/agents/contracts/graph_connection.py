"""
Graph connection output contract for graph-layer reasoning workflows.

The Graph Connection Agent proposes relation candidates inferred from
cross-document/cross-edge patterns in the existing kernel graph.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.domain.agents.contracts.base import BaseAgentContract


class ProposedRelation(BaseModel):
    """One relation candidate proposed by graph-level reasoning."""

    source_id: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_id: str = Field(..., min_length=1, max_length=64)
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_summary: str = Field(..., min_length=1, max_length=2000)
    evidence_tier: Literal["COMPUTATIONAL"] = "COMPUTATIONAL"
    supporting_provenance_ids: list[str] = Field(default_factory=list)
    supporting_document_count: int = Field(default=0, ge=0)
    reasoning: str = Field(..., min_length=1, max_length=4000)


class RejectedCandidate(BaseModel):
    """A candidate relation that was considered but not proposed."""

    source_id: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_id: str = Field(..., min_length=1, max_length=64)
    reason: str = Field(..., min_length=1, max_length=512)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class GraphConnectionContract(BaseAgentContract):
    """Contract for Graph Connection Agent outputs."""

    decision: Literal["generated", "fallback", "escalate"] = Field(
        ...,
        description="Outcome of the graph-connection run",
    )
    source_type: str = Field(..., min_length=1, max_length=64)
    research_space_id: str = Field(..., min_length=1, max_length=64)
    seed_entity_id: str = Field(..., min_length=1, max_length=64)
    proposed_relations: list[ProposedRelation] = Field(default_factory=list)
    rejected_candidates: list[RejectedCandidate] = Field(default_factory=list)
    shadow_mode: bool = Field(
        default=True,
        description="Whether persistence side effects should be suppressed",
    )
    agent_run_id: str | None = Field(
        default=None,
        description="Orchestration run identifier when available",
    )


__all__ = [
    "GraphConnectionContract",
    "ProposedRelation",
    "RejectedCandidate",
]
