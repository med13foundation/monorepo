"""
Entity recognition output contract for Tier-3 extraction workflows.

This contract captures what the recognizer inferred from a source document and
what semantic-layer mutations were proposed or applied.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.domain.agents.contracts.base import BaseAgentContract
from src.type_definitions.common import JSONObject, JSONValue  # noqa: TC001


class RecognizedEntityCandidate(BaseModel):
    """Entity candidate recognized from a source document."""

    entity_type: str = Field(..., min_length=1, max_length=64)
    display_label: str = Field(..., min_length=1, max_length=255)
    identifiers: JSONObject = Field(default_factory=dict)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class RecognizedObservationCandidate(BaseModel):
    """Observation candidate recognized from a source document field."""

    field_name: str = Field(..., min_length=1, max_length=128)
    variable_id: str | None = Field(default=None, max_length=64)
    value: JSONValue
    unit: str | None = Field(default=None, max_length=64)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class EntityRecognitionContract(BaseAgentContract):
    """
    Contract for Entity Recognition Agent outputs.

    `decision` follows the same governance pattern used by query generation.
    """

    decision: Literal["generated", "fallback", "escalate"] = Field(
        ...,
        description="Outcome of the entity-recognition run",
    )
    source_type: str = Field(..., min_length=1, max_length=64)
    document_id: str = Field(..., min_length=1, max_length=64)
    primary_entity_type: str = Field(default="VARIANT", min_length=1, max_length=64)
    field_candidates: list[str] = Field(default_factory=list)
    recognized_entities: list[RecognizedEntityCandidate] = Field(default_factory=list)
    recognized_observations: list[RecognizedObservationCandidate] = Field(
        default_factory=list,
    )
    pipeline_payloads: list[JSONObject] = Field(
        default_factory=list,
        description="Raw payloads that can be forwarded to the kernel ingestion pipeline",
    )
    created_definitions: list[str] = Field(default_factory=list)
    created_synonyms: list[str] = Field(default_factory=list)
    created_entity_types: list[str] = Field(default_factory=list)
    created_relation_types: list[str] = Field(default_factory=list)
    created_relation_constraints: list[str] = Field(default_factory=list)
    shadow_mode: bool = Field(
        default=True,
        description="Whether persistence side effects should be suppressed",
    )
    agent_run_id: str | None = Field(
        default=None,
        description="Flujo run identifier when available",
    )


__all__ = [
    "EntityRecognitionContract",
    "RecognizedEntityCandidate",
    "RecognizedObservationCandidate",
]
