"""
Kernel relation domain entity (graph edges).

Represents kernel relations as domain objects without ORM coupling.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Literal
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject  # noqa: TC001

EvidenceSentenceSource = Literal["verbatim_span", "artana_generated"]
EvidenceSentenceConfidence = Literal["low", "medium", "high"]
EvidenceSentenceHarnessOutcome = Literal["generated", "failed"]


class KernelRelation(BaseModel):
    """Domain representation of a kernel relation (graph edge)."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    research_space_id: UUID
    source_id: UUID
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_id: UUID

    aggregate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_count: int = Field(default=0, ge=0)
    highest_evidence_tier: str | None = Field(None, max_length=32)
    curation_status: str = Field(default="DRAFT", min_length=1, max_length=32)

    provenance_id: UUID | None = None
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None

    created_at: datetime
    updated_at: datetime


class KernelRelationEvidence(BaseModel):
    """Domain representation of one supporting evidence row for a relation."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    relation_id: UUID
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_summary: str | None = None
    evidence_sentence: str | None = None
    evidence_sentence_source: EvidenceSentenceSource | None = None
    evidence_sentence_confidence: EvidenceSentenceConfidence | None = None
    evidence_sentence_rationale: str | None = None
    evidence_tier: str = Field(..., min_length=1, max_length=32)
    provenance_id: UUID | None = None
    source_document_id: UUID | None = None
    agent_run_id: str | None = Field(default=None, max_length=255)
    created_at: datetime


class EvidenceSentenceGenerationRequest(BaseModel):
    """Input payload for optional AI evidence-sentence generation."""

    model_config = ConfigDict(frozen=True)

    research_space_id: str = Field(..., min_length=1)
    source_type: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=128)
    source_label: str | None = None
    target_label: str | None = None
    evidence_summary: str = Field(..., min_length=1, max_length=2000)
    evidence_excerpt: str | None = None
    evidence_locator: str | None = None
    document_text: str | None = None
    document_id: str | None = None
    run_id: str | None = None
    metadata: JSONObject = Field(default_factory=dict)


class EvidenceSentenceGenerationResult(BaseModel):
    """Normalized result for evidence-sentence generation harness."""

    model_config = ConfigDict(frozen=True)

    outcome: EvidenceSentenceHarnessOutcome
    sentence: str | None = None
    source: EvidenceSentenceSource | None = None
    confidence: EvidenceSentenceConfidence | None = None
    rationale: str | None = None
    failure_reason: str | None = None
    metadata: JSONObject = Field(default_factory=dict)


__all__ = [
    "EvidenceSentenceConfidence",
    "EvidenceSentenceGenerationRequest",
    "EvidenceSentenceGenerationResult",
    "EvidenceSentenceHarnessOutcome",
    "EvidenceSentenceSource",
    "KernelRelation",
    "KernelRelationEvidence",
]
