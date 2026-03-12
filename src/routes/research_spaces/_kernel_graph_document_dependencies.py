"""Dependency bundles for unified graph document routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from fastapi import Depends
from sqlalchemy.orm import Session

from src.database.session import get_session
from src.routes.research_spaces.dependencies import get_membership_service
from src.routes.research_spaces.kernel_dependencies import (
    get_kernel_claim_evidence_service,
    get_kernel_claim_participant_service,
    get_kernel_entity_service,
    get_kernel_relation_claim_service,
    get_kernel_relation_projection_source_service,
    get_kernel_relation_service,
)

if TYPE_CHECKING:
    from src.application.services.kernel import (
        KernelClaimEvidenceService,
        KernelClaimParticipantService,
        KernelEntityService,
        KernelRelationClaimService,
        KernelRelationProjectionSourceService,
        KernelRelationService,
    )
    from src.application.services.membership_management_service import (
        MembershipManagementService,
    )


class KernelGraphDocumentDependencies(NamedTuple):
    membership_service: MembershipManagementService
    entity_service: KernelEntityService
    relation_service: KernelRelationService
    relation_claim_service: KernelRelationClaimService
    relation_projection_source_service: KernelRelationProjectionSourceService
    claim_participant_service: KernelClaimParticipantService
    claim_evidence_service: KernelClaimEvidenceService
    session: Session


class KernelGraphDocumentServiceDependencies(NamedTuple):
    entity_service: KernelEntityService
    relation_service: KernelRelationService
    relation_claim_service: KernelRelationClaimService
    relation_projection_source_service: KernelRelationProjectionSourceService
    claim_participant_service: KernelClaimParticipantService
    claim_evidence_service: KernelClaimEvidenceService


def get_kernel_graph_document_service_dependencies(
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    relation_projection_source_service: KernelRelationProjectionSourceService = Depends(
        get_kernel_relation_projection_source_service,
    ),
    claim_participant_service: KernelClaimParticipantService = Depends(
        get_kernel_claim_participant_service,
    ),
    claim_evidence_service: KernelClaimEvidenceService = Depends(
        get_kernel_claim_evidence_service,
    ),
) -> KernelGraphDocumentServiceDependencies:
    return KernelGraphDocumentServiceDependencies(
        entity_service=entity_service,
        relation_service=relation_service,
        relation_claim_service=relation_claim_service,
        relation_projection_source_service=relation_projection_source_service,
        claim_participant_service=claim_participant_service,
        claim_evidence_service=claim_evidence_service,
    )


def get_kernel_graph_document_dependencies(
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service_dependencies: KernelGraphDocumentServiceDependencies = Depends(
        get_kernel_graph_document_service_dependencies,
    ),
    session: Session = Depends(get_session),
) -> KernelGraphDocumentDependencies:
    return KernelGraphDocumentDependencies(
        membership_service=membership_service,
        entity_service=service_dependencies.entity_service,
        relation_service=service_dependencies.relation_service,
        relation_claim_service=service_dependencies.relation_claim_service,
        relation_projection_source_service=(
            service_dependencies.relation_projection_source_service
        ),
        claim_participant_service=service_dependencies.claim_participant_service,
        claim_evidence_service=service_dependencies.claim_evidence_service,
        session=session,
    )


__all__ = [
    "KernelGraphDocumentDependencies",
    "KernelGraphDocumentServiceDependencies",
    "get_kernel_graph_document_dependencies",
    "get_kernel_graph_document_service_dependencies",
]
