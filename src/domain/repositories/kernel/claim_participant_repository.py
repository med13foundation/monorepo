"""Kernel claim-participant repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.kernel.claim_participants import (  # noqa: TC001
    ClaimParticipantRole,
    KernelClaimParticipant,
)
from src.type_definitions.common import JSONObject  # noqa: TC001


class KernelClaimParticipantRepository(ABC):
    """Repository contract for claim participant CRUD/query operations."""

    @abstractmethod
    def create(  # noqa: PLR0913
        self,
        *,
        claim_id: str,
        research_space_id: str,
        role: ClaimParticipantRole,
        label: str | None,
        entity_id: str | None,
        position: int | None,
        qualifiers: JSONObject | None = None,
    ) -> KernelClaimParticipant:
        """Create one claim participant row."""

    @abstractmethod
    def find_by_claim_id(self, claim_id: str) -> list[KernelClaimParticipant]:
        """List participants for one claim."""

    @abstractmethod
    def find_by_claim_ids(
        self,
        claim_ids: list[str],
    ) -> dict[str, list[KernelClaimParticipant]]:
        """List participants for multiple claims keyed by claim ID."""

    @abstractmethod
    def find_by_entity(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelClaimParticipant]:
        """List participant rows in one space bound to one entity."""

    @abstractmethod
    def list_claim_ids_by_entity(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[str]:
        """List distinct claim IDs in recency order for one entity participant."""

    @abstractmethod
    def count_claims_by_entity(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> int:
        """Count distinct claims referencing an entity via participants."""


__all__ = ["KernelClaimParticipantRepository"]
