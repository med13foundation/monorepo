"""Support types and helpers for kernel relation routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from fastapi import Depends
from sqlalchemy.orm import Session

from src.database.session import get_session
from src.routes.research_spaces.dependencies import get_membership_service
from src.routes.research_spaces.kernel_dependencies import (
    get_dictionary_service,
    get_kernel_claim_participant_service,
    get_kernel_entity_service,
    get_kernel_relation_claim_service,
    get_kernel_relation_projection_invariant_service,
    get_kernel_relation_projection_source_service,
    get_kernel_relation_service,
)

if TYPE_CHECKING:
    from src.application.services.kernel.kernel_claim_participant_service import (
        KernelClaimParticipantService,
    )
    from src.application.services.kernel.kernel_entity_service import (
        KernelEntityService,
    )
    from src.application.services.kernel.kernel_relation_claim_service import (
        KernelRelationClaimService,
    )
    from src.application.services.kernel.kernel_relation_projection_invariant_service import (
        KernelRelationProjectionInvariantService,
    )
    from src.application.services.kernel.kernel_relation_projection_source_service import (
        KernelRelationProjectionSourceService,
    )
    from src.application.services.kernel.kernel_relation_service import (
        KernelRelationService,
    )
    from src.application.services.membership_management_service import (
        MembershipManagementService,
    )
    from src.domain.ports.dictionary_port import DictionaryPort


class RelationClaimTriageDependencies(NamedTuple):
    membership_service: MembershipManagementService
    relation_claim_service: KernelRelationClaimService
    relation_projection_invariant_service: KernelRelationProjectionInvariantService
    relation_projection_service: KernelRelationProjectionSourceService
    relation_service: KernelRelationService
    dictionary_service: DictionaryPort
    session: Session


def get_relation_claim_triage_dependencies(
    membership_service: MembershipManagementService = Depends(get_membership_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    relation_projection_invariant_service: KernelRelationProjectionInvariantService = Depends(
        get_kernel_relation_projection_invariant_service,
    ),
    relation_projection_service: KernelRelationProjectionSourceService = Depends(
        get_kernel_relation_projection_source_service,
    ),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> RelationClaimTriageDependencies:
    return RelationClaimTriageDependencies(
        membership_service=membership_service,
        relation_claim_service=relation_claim_service,
        relation_projection_invariant_service=relation_projection_invariant_service,
        relation_projection_service=relation_projection_service,
        relation_service=relation_service,
        dictionary_service=dictionary_service,
        session=session,
    )


class KernelRelationWriteServices(NamedTuple):
    relation_service: KernelRelationService
    entity_service: KernelEntityService
    relation_claim_service: KernelRelationClaimService
    claim_participant_service: KernelClaimParticipantService
    relation_projection_invariant_service: KernelRelationProjectionInvariantService
    relation_projection_service: KernelRelationProjectionSourceService


def get_kernel_relation_write_services(
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    claim_participant_service: KernelClaimParticipantService = Depends(
        get_kernel_claim_participant_service,
    ),
    relation_projection_invariant_service: KernelRelationProjectionInvariantService = Depends(
        get_kernel_relation_projection_invariant_service,
    ),
    relation_projection_service: KernelRelationProjectionSourceService = Depends(
        get_kernel_relation_projection_source_service,
    ),
) -> KernelRelationWriteServices:
    return KernelRelationWriteServices(
        relation_service=relation_service,
        entity_service=entity_service,
        relation_claim_service=relation_claim_service,
        claim_participant_service=claim_participant_service,
        relation_projection_invariant_service=relation_projection_invariant_service,
        relation_projection_service=relation_projection_service,
    )


class CreateRelationDependencies(NamedTuple):
    membership_service: MembershipManagementService
    write_services: KernelRelationWriteServices
    session: Session


def get_create_relation_dependencies(
    membership_service: MembershipManagementService = Depends(get_membership_service),
    write_services: KernelRelationWriteServices = Depends(
        get_kernel_relation_write_services,
    ),
    session: Session = Depends(get_session),
) -> CreateRelationDependencies:
    return CreateRelationDependencies(
        membership_service=membership_service,
        write_services=write_services,
        session=session,
    )


def normalize_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def claim_endpoint_entity_ids(claim: object) -> tuple[str | None, str | None]:
    metadata_payload = getattr(claim, "metadata_payload", None)
    if not isinstance(metadata_payload, dict):
        return None, None
    source_entity_id = normalize_optional_text(
        metadata_payload.get("source_entity_id"),
    )
    target_entity_id = normalize_optional_text(
        metadata_payload.get("target_entity_id"),
    )
    return source_entity_id, target_entity_id


def claim_resolution_evidence_summary(claim: object) -> str:
    validation_reason = normalize_optional_text(
        getattr(claim, "validation_reason", None),
    )
    claim_id = normalize_optional_text(str(getattr(claim, "id", "")))
    if validation_reason is not None:
        if claim_id is None:
            return validation_reason
        return f"{validation_reason} (claim_id={claim_id})"
    if claim_id is None:
        return "Promoted from resolved extraction claim."
    return f"Promoted from resolved extraction claim ({claim_id})."


def manual_relation_claim_text(
    *,
    evidence_summary: str | None,
    evidence_sentence: str | None,
    relation_type: str,
    source_label: str | None,
    target_label: str | None,
) -> str:
    if evidence_sentence is not None and evidence_sentence.strip():
        return evidence_sentence.strip()[:2000]
    if evidence_summary is not None and evidence_summary.strip():
        return evidence_summary.strip()[:2000]
    source_text = source_label.strip() if source_label is not None else ""
    target_text = target_label.strip() if target_label is not None else ""
    if source_text and target_text:
        return f"{source_text} {relation_type} {target_text}"
    if source_text:
        return f"{source_text} {relation_type}"
    if target_text:
        return f"{relation_type} {target_text}"
    return relation_type


__all__ = [
    "CreateRelationDependencies",
    "KernelRelationWriteServices",
    "RelationClaimTriageDependencies",
    "claim_endpoint_entity_ids",
    "claim_resolution_evidence_summary",
    "get_create_relation_dependencies",
    "get_kernel_relation_write_services",
    "get_relation_claim_triage_dependencies",
    "manual_relation_claim_text",
    "normalize_optional_text",
]
