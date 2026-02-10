"""
Statement of Understanding entity for MED13 Resource Library.

Represents hypothesis-stage mechanistic explanations prior to promotion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.domain.value_objects.confidence import EvidenceLevel
from src.domain.value_objects.protein_structure import ProteinDomain  # noqa: TC001
from src.domain.value_objects.statement_status import StatementStatus


class StatementOfUnderstanding(BaseModel):
    """
    Represents a hypothesis-stage mechanistic statement for a research space.
    """

    research_space_id: UUID
    title: str
    summary: str
    evidence_tier: EvidenceLevel = EvidenceLevel.SUPPORTING
    confidence_score: float = 0.5
    status: StatementStatus = StatementStatus.DRAFT
    source: str = "manual_curation"

    protein_domains: list[ProteinDomain] = Field(default_factory=list)
    phenotype_ids: list[int] = Field(default_factory=list)
    promoted_mechanism_id: int | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    id: int | None = None

    model_config = ConfigDict(
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    @field_validator("confidence_score")
    @classmethod
    def _validate_confidence(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            msg = "confidence_score must be between 0.0 and 1.0"
            raise ValueError(msg)
        return value

    @field_validator("summary")
    @classmethod
    def _validate_summary(cls, value: str) -> str:
        if not value.strip():
            msg = "Statement summary cannot be empty"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _validate_statement(self) -> StatementOfUnderstanding:
        if not self.title.strip():
            msg = "Statement title cannot be empty"
            raise ValueError(msg)
        return self


__all__ = ["StatementOfUnderstanding"]
