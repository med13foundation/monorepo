"""Repository contract for derived reasoning-path persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.domain.entities.kernel.reasoning_paths import (  # noqa: TC001
    KernelReasoningPath,
    KernelReasoningPathStep,
    ReasoningPathKind,
    ReasoningPathStatus,
)
from src.type_definitions.common import JSONObject  # noqa: TC001


@dataclass(frozen=True)
class ReasoningPathWrite:
    """Write payload for one reasoning path row."""

    research_space_id: str
    path_kind: ReasoningPathKind
    status: ReasoningPathStatus
    start_entity_id: str
    end_entity_id: str
    root_claim_id: str
    path_length: int
    confidence: float
    path_signature_hash: str
    generated_by: str | None
    metadata: JSONObject


@dataclass(frozen=True)
class ReasoningPathStepWrite:
    """Write payload for one reasoning path step row."""

    step_index: int
    source_claim_id: str
    target_claim_id: str
    claim_relation_id: str
    canonical_relation_id: str | None
    metadata: JSONObject


@dataclass(frozen=True)
class ReasoningPathWriteBundle:
    """Write bundle containing a path row and its ordered steps."""

    path: ReasoningPathWrite
    steps: tuple[ReasoningPathStepWrite, ...]


class KernelReasoningPathRepository(ABC):
    """Persistence contract for derived reasoning paths."""

    @abstractmethod
    def replace_for_space(
        self,
        *,
        research_space_id: str,
        bundles: list[ReasoningPathWriteBundle],
        replace_existing: bool,
    ) -> list[KernelReasoningPath]:
        """Replace or upsert reasoning paths for one space."""

    @abstractmethod
    def list_paths(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        start_entity_id: str | None = None,
        end_entity_id: str | None = None,
        status: ReasoningPathStatus | None = None,
        path_kind: ReasoningPathKind | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelReasoningPath]:
        """List reasoning paths for one space."""

    @abstractmethod
    def count_paths(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        start_entity_id: str | None = None,
        end_entity_id: str | None = None,
        status: ReasoningPathStatus | None = None,
        path_kind: ReasoningPathKind | None = None,
    ) -> int:
        """Count reasoning paths for one space."""

    @abstractmethod
    def get_path(
        self,
        *,
        path_id: str,
        research_space_id: str,
    ) -> KernelReasoningPath | None:
        """Fetch one reasoning path."""

    @abstractmethod
    def list_steps_for_path_ids(
        self,
        *,
        path_ids: list[str],
    ) -> dict[str, list[KernelReasoningPathStep]]:
        """List steps for one or more path IDs keyed by path ID."""

    @abstractmethod
    def mark_stale_for_claim_ids(
        self,
        *,
        research_space_id: str,
        claim_ids: list[str],
    ) -> int:
        """Mark any affected paths stale when claim rows change."""

    @abstractmethod
    def mark_stale_for_claim_relation_ids(
        self,
        *,
        research_space_id: str,
        relation_ids: list[str],
    ) -> int:
        """Mark any affected paths stale when claim-relation rows change."""


__all__ = [
    "KernelReasoningPathRepository",
    "ReasoningPathStepWrite",
    "ReasoningPathWrite",
    "ReasoningPathWriteBundle",
]
