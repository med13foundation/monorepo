"""Contract models for LLM-based mapper disambiguation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.domain.agents.contracts.base import BaseAgentContract
from src.type_definitions.common import JSONObject  # noqa: TC001


class MappingJudgeCandidate(BaseModel):
    """Candidate variable definition presented to the mapping judge."""

    variable_id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=255)
    match_method: Literal["exact", "synonym", "fuzzy", "vector"]
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    description: str | None = None
    metadata: JSONObject = Field(default_factory=dict)


class MappingJudgeContract(BaseAgentContract):
    """Structured output for one mapper disambiguation decision."""

    decision: Literal["matched", "no_match", "ambiguous"]
    selected_variable_id: str | None = Field(default=None, min_length=1, max_length=64)
    candidate_count: int = Field(default=0, ge=0)
    selection_rationale: str = Field(..., min_length=1, max_length=4000)
    selected_candidate: MappingJudgeCandidate | None = None
    agent_run_id: str | None = Field(default=None, max_length=128)


__all__ = ["MappingJudgeCandidate", "MappingJudgeContract"]
