"""Backfill and coverage service for structured claim participants."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.application.services.claim_first_metrics import increment_metric
from src.application.services.kernel._kernel_claim_participant_backfill_support import (
    ClaimParticipantBackfillGlobalSummary,
    ClaimParticipantBackfillSummary,
    ClaimParticipantCoverageSummary,
    _Anchor,
    list_projection_relevant_claim_models,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.application.services.kernel.kernel_claim_participant_service import (
        KernelClaimParticipantService,
    )
    from src.application.services.kernel.kernel_relation_claim_service import (
        KernelRelationClaimService,
    )
    from src.domain.entities.kernel.concepts import ConceptMember
    from src.domain.ports import ConceptPort
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
    from src.type_definitions.common import JSONObject


class KernelClaimParticipantBackfillService:
    """Populate and audit claim participants for existing relation claims."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        session: Session,
        relation_claim_service: KernelRelationClaimService,
        claim_participant_service: KernelClaimParticipantService,
        entity_repository: KernelEntityRepository,
        concept_service: ConceptPort,
    ) -> None:
        self._session = session
        self._claims = relation_claim_service
        self._participants = claim_participant_service
        self._entities = entity_repository
        self._concepts = concept_service

    def backfill_for_space(
        self,
        *,
        research_space_id: str,
        dry_run: bool,
        limit: int,
        offset: int,
    ) -> ClaimParticipantBackfillSummary:
        claims = self._claims.list_by_research_space(
            research_space_id,
            limit=max(1, min(limit, 5000)),
            offset=max(0, offset),
        )

        created_participants = 0
        skipped_existing = 0
        unresolved_endpoints = 0

        for claim in claims:
            existing = self._participants.list_participants_for_claim(str(claim.id))
            existing_roles = {participant.role for participant in existing}

            source_anchor = self._resolve_claim_anchor(
                research_space_id=research_space_id,
                claim_metadata=claim.metadata_payload,
                endpoint="source",
                fallback_label=claim.source_label,
            )
            target_anchor = self._resolve_claim_anchor(
                research_space_id=research_space_id,
                claim_metadata=claim.metadata_payload,
                endpoint="target",
                fallback_label=claim.target_label,
            )

            if "SUBJECT" in existing_roles:
                skipped_existing += 1
            elif source_anchor is None:
                unresolved_endpoints += 1
            else:
                if not dry_run:
                    self._participants.create_participant(
                        claim_id=str(claim.id),
                        research_space_id=research_space_id,
                        role="SUBJECT",
                        label=source_anchor.label,
                        entity_id=source_anchor.entity_id,
                        position=0,
                        qualifiers={"origin": "participant_backfill_v1"},
                    )
                created_participants += 1

            if "OBJECT" in existing_roles:
                skipped_existing += 1
            elif target_anchor is None:
                unresolved_endpoints += 1
            else:
                if not dry_run:
                    self._participants.create_participant(
                        claim_id=str(claim.id),
                        research_space_id=research_space_id,
                        role="OBJECT",
                        label=target_anchor.label,
                        entity_id=target_anchor.entity_id,
                        position=1,
                        qualifiers={"origin": "participant_backfill_v1"},
                    )
                created_participants += 1

        if created_participants > 0:
            increment_metric(
                "claim_participants_backfilled_total",
                delta=created_participants,
                tags={"research_space_id": research_space_id},
            )
        if unresolved_endpoints > 0:
            increment_metric(
                "claim_participants_backfill_unresolved_total",
                delta=unresolved_endpoints,
                tags={"research_space_id": research_space_id},
            )

        return ClaimParticipantBackfillSummary(
            scanned_claims=len(claims),
            created_participants=created_participants,
            skipped_existing=skipped_existing,
            unresolved_endpoints=unresolved_endpoints,
            dry_run=dry_run,
        )

    def backfill_globally(
        self,
        *,
        dry_run: bool,
        limit: int,
        offset: int,
    ) -> ClaimParticipantBackfillGlobalSummary:
        claims = list_projection_relevant_claim_models(
            self._session,
            limit=max(1, min(limit, 10000)),
            offset=max(0, offset),
        )

        created_participants = 0
        skipped_existing = 0
        unresolved_endpoints = 0
        research_space_ids: set[str] = set()

        for claim in claims:
            research_space_id = str(claim.research_space_id)
            research_space_ids.add(research_space_id)
            existing = self._participants.list_participants_for_claim(str(claim.id))
            existing_roles = {participant.role for participant in existing}

            source_anchor = self._resolve_claim_anchor(
                research_space_id=research_space_id,
                claim_metadata=claim.metadata_payload,
                endpoint="source",
                fallback_label=claim.source_label,
            )
            target_anchor = self._resolve_claim_anchor(
                research_space_id=research_space_id,
                claim_metadata=claim.metadata_payload,
                endpoint="target",
                fallback_label=claim.target_label,
            )

            if "SUBJECT" in existing_roles:
                skipped_existing += 1
            elif source_anchor is None or source_anchor.entity_id is None:
                unresolved_endpoints += 1
            else:
                if not dry_run:
                    self._participants.create_participant(
                        claim_id=str(claim.id),
                        research_space_id=research_space_id,
                        role="SUBJECT",
                        label=source_anchor.label,
                        entity_id=source_anchor.entity_id,
                        position=0,
                        qualifiers={"origin": "participant_backfill_global_v1"},
                    )
                created_participants += 1

            if "OBJECT" in existing_roles:
                skipped_existing += 1
            elif target_anchor is None or target_anchor.entity_id is None:
                unresolved_endpoints += 1
            else:
                if not dry_run:
                    self._participants.create_participant(
                        claim_id=str(claim.id),
                        research_space_id=research_space_id,
                        role="OBJECT",
                        label=target_anchor.label,
                        entity_id=target_anchor.entity_id,
                        position=1,
                        qualifiers={"origin": "participant_backfill_global_v1"},
                    )
                created_participants += 1

        if created_participants > 0:
            increment_metric(
                "claim_participants_backfilled_total",
                delta=created_participants,
                tags={"scope": "global_projection_repair"},
            )
        if unresolved_endpoints > 0:
            increment_metric(
                "claim_participants_backfill_unresolved_total",
                delta=unresolved_endpoints,
                tags={"scope": "global_projection_repair"},
            )

        return ClaimParticipantBackfillGlobalSummary(
            scanned_claims=len(claims),
            created_participants=created_participants,
            skipped_existing=skipped_existing,
            unresolved_endpoints=unresolved_endpoints,
            research_spaces=len(research_space_ids),
            dry_run=dry_run,
        )

    def coverage_for_space(
        self,
        *,
        research_space_id: str,
        limit: int,
        offset: int,
    ) -> ClaimParticipantCoverageSummary:
        claims = self._claims.list_by_research_space(
            research_space_id,
            limit=max(1, min(limit, 5000)),
            offset=max(0, offset),
        )

        claims_with_any_participants = 0
        claims_with_subject = 0
        claims_with_object = 0
        unresolved_subject_endpoints = 0
        unresolved_object_endpoints = 0

        for claim in claims:
            participants = self._participants.list_participants_for_claim(str(claim.id))
            roles = {participant.role for participant in participants}
            if participants:
                claims_with_any_participants += 1
            if "SUBJECT" in roles:
                claims_with_subject += 1
            else:
                unresolved_subject_endpoints += 1
            if "OBJECT" in roles:
                claims_with_object += 1
            else:
                unresolved_object_endpoints += 1

        return ClaimParticipantCoverageSummary(
            total_claims=len(claims),
            claims_with_any_participants=claims_with_any_participants,
            claims_with_subject=claims_with_subject,
            claims_with_object=claims_with_object,
            unresolved_subject_endpoints=unresolved_subject_endpoints,
            unresolved_object_endpoints=unresolved_object_endpoints,
        )

    def _resolve_claim_anchor(
        self,
        *,
        research_space_id: str,
        claim_metadata: JSONObject,
        endpoint: str,
        fallback_label: str | None,
    ) -> _Anchor | None:
        entity_id = self._resolve_entity_id_from_metadata(
            research_space_id=research_space_id,
            claim_metadata=claim_metadata,
            endpoint=endpoint,
        )
        if entity_id is not None:
            entity = self._entities.get_by_id(entity_id)
            if (
                entity is not None
                and str(entity.research_space_id) == research_space_id
            ):
                entity_label = (
                    entity.display_label.strip()
                    if isinstance(entity.display_label, str)
                    else ""
                )
                return _Anchor(
                    entity_id=str(entity.id),
                    label=entity_label or None,
                )

        concept_anchor = self._resolve_concept_member_anchor_from_metadata(
            research_space_id=research_space_id,
            claim_metadata=claim_metadata,
            endpoint=endpoint,
        )
        if concept_anchor is not None:
            return concept_anchor

        normalized_fallback = (
            fallback_label.strip() if isinstance(fallback_label, str) else ""
        )
        if normalized_fallback:
            return _Anchor(entity_id=None, label=normalized_fallback)
        return None

    def _resolve_entity_id_from_metadata(
        self,
        *,
        research_space_id: str,
        claim_metadata: JSONObject,
        endpoint: str,
    ) -> str | None:
        entity_key = f"{endpoint}_entity_id"
        raw_entity_id = claim_metadata.get(entity_key)
        if not isinstance(raw_entity_id, str):
            return None
        return self._resolve_entity_id_in_space(
            research_space_id=research_space_id,
            candidate_entity_id=raw_entity_id,
        )

    def _resolve_concept_member_anchor_from_metadata(
        self,
        *,
        research_space_id: str,
        claim_metadata: JSONObject,
        endpoint: str,
    ) -> _Anchor | None:
        raw_refs = claim_metadata.get("concept_refs")
        if not isinstance(raw_refs, dict):
            return None
        member_key = f"{endpoint}_member_id"
        raw_member_id = raw_refs.get(member_key)
        if not isinstance(raw_member_id, str):
            return None
        normalized_member_id = raw_member_id.strip()
        if not normalized_member_id:
            return None

        concept_set_id = raw_refs.get("concept_set_id")
        if not isinstance(concept_set_id, str) or not concept_set_id.strip():
            return None

        members = self._concepts.list_concept_members(
            research_space_id=research_space_id,
            concept_set_id=concept_set_id.strip(),
            include_inactive=True,
            offset=0,
            limit=1000,
        )
        for member in members:
            if member.id != normalized_member_id:
                continue
            return self._build_anchor_from_concept_member(
                research_space_id=research_space_id,
                member=member,
            )
        return None

    def _build_anchor_from_concept_member(
        self,
        *,
        research_space_id: str,
        member: ConceptMember,
    ) -> _Anchor:
        resolved_entity_id = self._resolve_entity_id_from_concept_member(
            research_space_id=research_space_id,
            member=member,
        )
        label = (
            member.canonical_label.strip()
            if isinstance(member.canonical_label, str)
            else ""
        )
        if resolved_entity_id is None:
            return _Anchor(entity_id=None, label=label or None)

        entity = self._entities.get_by_id(resolved_entity_id)
        if entity is not None and str(entity.research_space_id) == research_space_id:
            entity_label = (
                entity.display_label.strip()
                if isinstance(entity.display_label, str)
                else ""
            )
            return _Anchor(
                entity_id=resolved_entity_id,
                label=entity_label or label or None,
            )

        return _Anchor(entity_id=resolved_entity_id, label=label or None)

    def _resolve_entity_id_from_concept_member(
        self,
        *,
        research_space_id: str,
        member: ConceptMember,
    ) -> str | None:
        candidate_ids: list[str] = []

        dimension_raw = (
            member.dictionary_dimension.strip().lower()
            if isinstance(member.dictionary_dimension, str)
            else ""
        )
        dictionary_entry_id = (
            member.dictionary_entry_id.strip()
            if isinstance(member.dictionary_entry_id, str)
            else ""
        )
        if dictionary_entry_id and dimension_raw in {
            "entity",
            "entity_id",
            "kernel_entity",
            "kernel_entity_id",
            "kernel.entities",
        }:
            candidate_ids.append(dictionary_entry_id)

        metadata_payload = member.metadata_payload
        if isinstance(metadata_payload, dict):
            for key in (
                "entity_id",
                "kernel_entity_id",
                "linked_entity_id",
                "resolved_entity_id",
            ):
                raw_value = metadata_payload.get(key)
                if isinstance(raw_value, str) and raw_value.strip():
                    candidate_ids.append(raw_value)

            raw_entity = metadata_payload.get("entity")
            if isinstance(raw_entity, dict):
                raw_nested_id = raw_entity.get("id")
                if isinstance(raw_nested_id, str) and raw_nested_id.strip():
                    candidate_ids.append(raw_nested_id)

        for candidate_id in candidate_ids:
            normalized = self._resolve_entity_id_in_space(
                research_space_id=research_space_id,
                candidate_entity_id=candidate_id,
            )
            if normalized is not None:
                return normalized
        return None

    def _resolve_entity_id_in_space(
        self,
        *,
        research_space_id: str,
        candidate_entity_id: str,
    ) -> str | None:
        candidate = candidate_entity_id.strip()
        if not candidate:
            return None
        try:
            canonical = str(UUID(candidate))
        except ValueError:
            return None
        entity = self._entities.get_by_id(canonical)
        if entity is None:
            return None
        if str(entity.research_space_id) != research_space_id:
            return None
        return canonical


__all__ = [
    "ClaimParticipantBackfillSummary",
    "ClaimParticipantCoverageSummary",
    "ClaimParticipantBackfillGlobalSummary",
    "KernelClaimParticipantBackfillService",
]
