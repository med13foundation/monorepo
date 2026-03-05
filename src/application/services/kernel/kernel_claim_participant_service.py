"""Kernel claim participant application service."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.kernel.claim_participants import (
        ClaimParticipantRole,
        KernelClaimParticipant,
    )
    from src.domain.repositories.kernel.claim_participant_repository import (
        KernelClaimParticipantRepository,
    )
    from src.type_definitions.common import JSONObject


class KernelClaimParticipantService:
    """Application service for claim participant writes and lookups."""

    def __init__(
        self,
        claim_participant_repo: KernelClaimParticipantRepository,
    ) -> None:
        self._participants = claim_participant_repo

    def create_participant(  # noqa: PLR0913
        self,
        *,
        claim_id: str,
        research_space_id: str,
        role: ClaimParticipantRole,
        label: str | None,
        entity_id: str | None,
        position: int | None = None,
        qualifiers: JSONObject | None = None,
    ) -> KernelClaimParticipant:
        """Create one participant row."""
        return self._participants.create(
            claim_id=claim_id,
            research_space_id=research_space_id,
            role=role,
            label=label,
            entity_id=entity_id,
            position=position,
            qualifiers=qualifiers,
        )

    def list_participants_for_claim(
        self,
        claim_id: str,
    ) -> list[KernelClaimParticipant]:
        """List participants for one claim."""
        return self._participants.find_by_claim_id(claim_id)

    def list_claim_ids_by_entity(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[str]:
        """List distinct claim IDs for one entity in participant rows."""
        return self._participants.list_claim_ids_by_entity(
            research_space_id=research_space_id,
            entity_id=entity_id,
            limit=limit,
            offset=offset,
        )

    def count_claims_by_entity(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> int:
        """Count distinct claim IDs for one entity in participant rows."""
        return self._participants.count_claims_by_entity(
            research_space_id=research_space_id,
            entity_id=entity_id,
        )


__all__ = ["KernelClaimParticipantService"]
