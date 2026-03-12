"""Support types and helpers for kernel relation routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from fastapi import Depends
from sqlalchemy.orm import Session

from src.database.session import get_session
from src.routes.research_spaces.dependencies import get_membership_service
from src.routes.research_spaces.kernel_dependencies import (
    get_dictionary_service,
    get_kernel_claim_evidence_service,
    get_kernel_claim_participant_service,
    get_kernel_entity_service,
    get_kernel_reasoning_path_service,
    get_kernel_relation_claim_service,
    get_kernel_relation_projection_materialization_service,
)

if TYPE_CHECKING:
    from src.application.services.kernel.kernel_claim_evidence_service import (
        KernelClaimEvidenceService,
    )
    from src.application.services.kernel.kernel_claim_participant_service import (
        KernelClaimParticipantService,
    )
    from src.application.services.kernel.kernel_entity_service import (
        KernelEntityService,
    )
    from src.application.services.kernel.kernel_reasoning_path_service import (
        KernelReasoningPathService,
    )
    from src.application.services.kernel.kernel_relation_claim_service import (
        KernelRelationClaimService,
    )
    from src.application.services.kernel.kernel_relation_projection_materialization_service import (
        KernelRelationProjectionMaterializationService,
    )
    from src.application.services.membership_management_service import (
        MembershipManagementService,
    )
    from src.domain.ports.dictionary_port import DictionaryPort


class RelationClaimTriageDependencies(NamedTuple):
    membership_service: MembershipManagementService
    relation_claim_service: KernelRelationClaimService
    relation_projection_materialization_service: (
        KernelRelationProjectionMaterializationService
    )
    reasoning_path_service: KernelReasoningPathService
    dictionary_service: DictionaryPort
    session: Session


def get_relation_claim_triage_dependencies(
    membership_service: MembershipManagementService = Depends(get_membership_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    relation_projection_materialization_service: KernelRelationProjectionMaterializationService = Depends(
        get_kernel_relation_projection_materialization_service,
    ),
    reasoning_path_service: KernelReasoningPathService = Depends(
        get_kernel_reasoning_path_service,
    ),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> RelationClaimTriageDependencies:
    return RelationClaimTriageDependencies(
        membership_service=membership_service,
        relation_claim_service=relation_claim_service,
        relation_projection_materialization_service=(
            relation_projection_materialization_service
        ),
        reasoning_path_service=reasoning_path_service,
        dictionary_service=dictionary_service,
        session=session,
    )


class KernelRelationWriteServices(NamedTuple):
    entity_service: KernelEntityService
    relation_claim_service: KernelRelationClaimService
    claim_participant_service: KernelClaimParticipantService
    claim_evidence_service: KernelClaimEvidenceService
    relation_projection_materialization_service: (
        KernelRelationProjectionMaterializationService
    )


def get_kernel_relation_write_services(
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    claim_participant_service: KernelClaimParticipantService = Depends(
        get_kernel_claim_participant_service,
    ),
    claim_evidence_service: KernelClaimEvidenceService = Depends(
        get_kernel_claim_evidence_service,
    ),
    relation_projection_materialization_service: KernelRelationProjectionMaterializationService = Depends(
        get_kernel_relation_projection_materialization_service,
    ),
) -> KernelRelationWriteServices:
    return KernelRelationWriteServices(
        entity_service=entity_service,
        relation_claim_service=relation_claim_service,
        claim_participant_service=claim_participant_service,
        claim_evidence_service=claim_evidence_service,
        relation_projection_materialization_service=(
            relation_projection_materialization_service
        ),
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
    "get_create_relation_dependencies",
    "get_kernel_relation_write_services",
    "get_relation_claim_triage_dependencies",
    "manual_relation_claim_text",
    "normalize_optional_text",
]
