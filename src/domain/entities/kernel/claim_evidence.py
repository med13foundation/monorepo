"""Kernel relation-claim evidence domain entities."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Literal
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject  # noqa: TC001

ClaimEvidenceSentenceSource = Literal["verbatim_span", "artana_generated"]
ClaimEvidenceSentenceConfidence = Literal["low", "medium", "high"]


class KernelClaimEvidence(BaseModel):
    """One evidence row attached to a relation claim."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    claim_id: UUID
    source_document_id: UUID | None = None
    agent_run_id: str | None = Field(default=None, max_length=255)
    sentence: str | None = None
    sentence_source: ClaimEvidenceSentenceSource | None = None
    sentence_confidence: ClaimEvidenceSentenceConfidence | None = None
    sentence_rationale: str | None = None
    figure_reference: str | None = None
    table_reference: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata_payload: JSONObject = Field(default_factory=dict)
    created_at: datetime


__all__ = [
    "ClaimEvidenceSentenceConfidence",
    "ClaimEvidenceSentenceSource",
    "KernelClaimEvidence",
]
