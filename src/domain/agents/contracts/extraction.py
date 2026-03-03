"""
Extraction output contract for Tier-3 structured fact mapping.

The Extraction Agent maps content to existing dictionary definitions and
returns validated observations/relations plus rejected candidates.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.domain.agents.contracts.base import BaseAgentContract
from src.type_definitions.common import JSONObject, JSONValue  # noqa: TC001


class ExtractedObservation(BaseModel):
    """Validated observation mapped to an existing dictionary variable."""

    field_name: str = Field(..., min_length=1, max_length=128)
    variable_id: str = Field(..., min_length=1, max_length=64)
    value: JSONValue
    unit: str | None = Field(default=None, max_length=64)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ExtractedRelation(BaseModel):
    """Validated relation triple mapped to dictionary relation constraints."""

    source_type: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_type: str = Field(..., min_length=1, max_length=64)
    source_label: str | None = Field(default=None, max_length=255)
    target_label: str | None = Field(default=None, max_length=255)
    evidence_excerpt: str | None = Field(
        default=None,
        max_length=1200,
        description="Relation-level supporting text span excerpt from the source.",
    )
    evidence_locator: str | None = Field(
        default=None,
        max_length=255,
        description="Locator for the evidence span (sentence id, section, etc.).",
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class RejectedFact(BaseModel):
    """Candidate fact rejected during tool-assisted extraction validation."""

    fact_type: Literal["observation", "relation"]
    reason: str = Field(..., min_length=1, max_length=255)
    payload: JSONObject = Field(default_factory=dict)


class ExtractionContract(BaseAgentContract):
    """Contract for Extraction Agent outputs."""

    decision: Literal["generated", "fallback", "escalate"] = Field(
        ...,
        description="Outcome of the extraction run",
    )
    source_type: str = Field(..., min_length=1, max_length=64)
    document_id: str = Field(..., min_length=1, max_length=64)
    observations: list[ExtractedObservation] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
    rejected_facts: list[RejectedFact] = Field(default_factory=list)
    pipeline_payloads: list[JSONObject] = Field(
        default_factory=list,
        description="Payloads suitable for kernel ingestion",
    )
    shadow_mode: bool = Field(
        default=True,
        description="Whether side effects should be suppressed",
    )
    agent_run_id: str | None = Field(
        default=None,
        description="Orchestration run identifier when available",
    )


__all__ = [
    "ExtractedObservation",
    "ExtractedRelation",
    "ExtractionContract",
    "RejectedFact",
]
