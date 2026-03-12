"""Dependency bundles for claim graph routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from fastapi import Depends
from sqlalchemy.orm import Session

from src.database.session import get_session
from src.routes.research_spaces.dependencies import get_membership_service
from src.routes.research_spaces.kernel_dependencies import (
    get_kernel_claim_relation_service,
    get_kernel_reasoning_path_service,
    get_kernel_relation_claim_service,
)

if TYPE_CHECKING:
    from src.application.services.kernel.kernel_claim_relation_service import (
        KernelClaimRelationService,
    )
    from src.application.services.kernel.kernel_reasoning_path_service import (
        KernelReasoningPathService,
    )
    from src.application.services.kernel.kernel_relation_claim_service import (
        KernelRelationClaimService,
    )
    from src.application.services.membership_management_service import (
        MembershipManagementService,
    )
    from src.domain.entities.kernel.claim_relations import (
        ClaimRelationReviewStatus,
        ClaimRelationType,
    )


class ClaimRelationWriteDependencies(NamedTuple):
    membership_service: MembershipManagementService
    relation_claim_service: KernelRelationClaimService
    claim_relation_service: KernelClaimRelationService
    reasoning_path_service: KernelReasoningPathService
    session: Session


class ClaimRelationReviewDependencies(NamedTuple):
    membership_service: MembershipManagementService
    claim_relation_service: KernelClaimRelationService
    reasoning_path_service: KernelReasoningPathService
    session: Session


def get_claim_relation_write_dependencies(
    membership_service: MembershipManagementService = Depends(get_membership_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    claim_relation_service: KernelClaimRelationService = Depends(
        get_kernel_claim_relation_service,
    ),
    reasoning_path_service: KernelReasoningPathService = Depends(
        get_kernel_reasoning_path_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimRelationWriteDependencies:
    return ClaimRelationWriteDependencies(
        membership_service=membership_service,
        relation_claim_service=relation_claim_service,
        claim_relation_service=claim_relation_service,
        reasoning_path_service=reasoning_path_service,
        session=session,
    )


def get_claim_relation_review_dependencies(
    membership_service: MembershipManagementService = Depends(get_membership_service),
    claim_relation_service: KernelClaimRelationService = Depends(
        get_kernel_claim_relation_service,
    ),
    reasoning_path_service: KernelReasoningPathService = Depends(
        get_kernel_reasoning_path_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimRelationReviewDependencies:
    return ClaimRelationReviewDependencies(
        membership_service=membership_service,
        claim_relation_service=claim_relation_service,
        reasoning_path_service=reasoning_path_service,
        session=session,
    )


def normalize_relation_type(value: str) -> ClaimRelationType:  # noqa: PLR0911
    normalized = value.strip().upper()
    if normalized == "SUPPORTS":
        return "SUPPORTS"
    if normalized == "CONTRADICTS":
        return "CONTRADICTS"
    if normalized == "REFINES":
        return "REFINES"
    if normalized == "CAUSES":
        return "CAUSES"
    if normalized == "UPSTREAM_OF":
        return "UPSTREAM_OF"
    if normalized == "DOWNSTREAM_OF":
        return "DOWNSTREAM_OF"
    if normalized == "SAME_AS":
        return "SAME_AS"
    if normalized == "GENERALIZES":
        return "GENERALIZES"
    if normalized == "INSTANCE_OF":
        return "INSTANCE_OF"
    msg = f"Unsupported relation_type '{value}'"
    raise ValueError(msg)


def normalize_review_status(value: str) -> ClaimRelationReviewStatus:
    normalized = value.strip().upper()
    if normalized == "PROPOSED":
        return "PROPOSED"
    if normalized == "ACCEPTED":
        return "ACCEPTED"
    if normalized == "REJECTED":
        return "REJECTED"
    msg = f"Unsupported review_status '{value}'"
    raise ValueError(msg)


__all__ = [
    "ClaimRelationReviewDependencies",
    "ClaimRelationWriteDependencies",
    "get_claim_relation_review_dependencies",
    "get_claim_relation_write_dependencies",
    "normalize_relation_type",
    "normalize_review_status",
]
