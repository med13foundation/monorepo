"""Ontology validation/proposal endpoints scoped to research spaces."""

from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.application.curation.services.review_service import ReviewService
from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.domain.ports.dictionary_port import DictionaryPort
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_curation_service,
    get_membership_service,
    require_researcher_role,
    verify_space_membership,
)
from src.routes.research_spaces.kernel_dependencies import get_dictionary_service
from src.type_definitions.common import ResearchSpaceSettings

from .router import (
    HTTP_400_BAD_REQUEST,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)

ValidationState = Literal["ALLOWED", "FORBIDDEN", "UNDEFINED"]


class OntologyValidateRelationRequest(BaseModel):
    """Read-only relation validation request."""

    model_config = ConfigDict(strict=True)

    src_type: str = Field(..., min_length=1, max_length=64)
    relation_label: str = Field(..., min_length=1, max_length=128)
    dst_type: str = Field(..., min_length=1, max_length=64)
    context: str | None = Field(default=None, max_length=4000)


class OntologyValidateRelationResponse(BaseModel):
    """Read-only relation validation response."""

    model_config = ConfigDict(strict=True)

    validation_state: ValidationState
    canonical_relation_type_id: str | None = None
    mapped_from_label: str | None = None
    constraint_id: str | None = None
    dictionary_version: int = Field(default=0, ge=0)
    reason: str


class OntologyProposeRelationConstraintRequest(BaseModel):
    """Proposal request for unknown/undefined relation patterns."""

    model_config = ConfigDict(strict=True)

    src_type: str = Field(..., min_length=1, max_length=64)
    relation_label: str = Field(..., min_length=1, max_length=128)
    dst_type: str = Field(..., min_length=1, max_length=64)
    context: str | None = Field(default=None, max_length=4000)
    is_allowed: bool = True
    requires_evidence: bool = True
    priority: Literal["low", "medium", "high"] = "medium"
    domain_context: str = Field(default="general", min_length=1, max_length=64)


class OntologyProposeRelationConstraintResponse(BaseModel):
    """Proposal response with review queue linkage."""

    model_config = ConfigDict(strict=True)

    canonical_relation_type_id: str
    constraint_id: str
    proposal_created: bool
    relation_type_created: bool
    review_item_id: int | None = None
    dictionary_version: int = Field(default=0, ge=0)
    reason: str


_RELATION_TOKEN_SPLIT_PATTERN = re.compile(r"[^A-Za-z0-9]+")


def _normalize_entity_type(raw_value: str) -> str:
    normalized = raw_value.strip().upper()
    if not normalized:
        msg = "Entity type is required."
        raise ValueError(msg)
    return normalized


def _normalize_relation_type_id(raw_value: str) -> str:
    normalized = raw_value.strip().upper()
    if not normalized:
        msg = "Relation label is required."
        raise ValueError(msg)
    tokens = [
        token for token in _RELATION_TOKEN_SPLIT_PATTERN.split(normalized) if token
    ]
    if not tokens:
        msg = "Relation label must include alphanumeric tokens."
        raise ValueError(msg)
    return "_".join(tokens)


def _build_constraint_key(
    *,
    source_type: str,
    relation_type: str,
    target_type: str,
) -> str:
    return f"{source_type}:{relation_type}:{target_type}"


def _resolve_dictionary_version(dictionary_service: DictionaryPort) -> int:
    entries = dictionary_service.list_changelog_entries(limit=1)
    if not entries:
        return 0
    latest = entries[0].id
    return latest if isinstance(latest, int) and latest >= 0 else 0


def _resolve_relation_mapping(
    *,
    dictionary_service: DictionaryPort,
    relation_label: str,
) -> tuple[str | None, str | None]:
    normalized_id = _normalize_relation_type_id(relation_label)
    direct = dictionary_service.get_relation_type(
        normalized_id,
        include_inactive=True,
    )
    if direct is not None:
        mapped_from = relation_label if direct.id != relation_label.strip() else None
        return direct.id, mapped_from

    normalized_label = relation_label.strip().casefold()
    relation_types = dictionary_service.list_relation_types(include_inactive=True)
    for relation_type in relation_types:
        if relation_type.id.casefold() == normalized_label:
            return relation_type.id, relation_label
        if relation_type.display_name.strip().casefold() == normalized_label:
            return relation_type.id, relation_label
    return None, None


def _resolve_constraint_state(  # noqa: PLR0911
    *,
    dictionary_service: DictionaryPort,
    source_type: str,
    relation_type: str,
    target_type: str,
) -> tuple[ValidationState, str]:
    constraints = dictionary_service.get_constraints(
        source_type=source_type,
        relation_type=relation_type,
        include_inactive=True,
    )
    exact_matches = [c for c in constraints if c.target_type == target_type]
    if not exact_matches:
        return "UNDEFINED", "No relation constraint exists for this type triple."

    for constraint in exact_matches:
        if not constraint.is_active:
            continue
        if constraint.review_status != "ACTIVE":
            continue
        if constraint.is_allowed:
            return "ALLOWED", "Matched active allowed relation constraint."
        return "FORBIDDEN", "Matched active forbidden relation constraint."

    if any(c.review_status == "PENDING_REVIEW" for c in exact_matches):
        return (
            "UNDEFINED",
            "Constraint exists but remains pending review.",
        )

    return "UNDEFINED", "Constraint exists but is not active for validation."


@research_spaces_router.post(
    "/{space_id}/ontology/validate_relation",
    response_model=OntologyValidateRelationResponse,
    summary="Validate a relation label/type triple against ontology constraints",
)
def validate_relation(
    space_id: UUID,
    request: OntologyValidateRelationRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> OntologyValidateRelationResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    try:
        source_type = _normalize_entity_type(request.src_type)
        target_type = _normalize_entity_type(request.dst_type)
        if (
            dictionary_service.get_entity_type(source_type, include_inactive=True)
            is None
        ):
            return OntologyValidateRelationResponse(
                validation_state="UNDEFINED",
                canonical_relation_type_id=None,
                mapped_from_label=None,
                constraint_id=None,
                dictionary_version=_resolve_dictionary_version(dictionary_service),
                reason=f"Unknown source entity type '{source_type}'.",
            )
        if (
            dictionary_service.get_entity_type(target_type, include_inactive=True)
            is None
        ):
            return OntologyValidateRelationResponse(
                validation_state="UNDEFINED",
                canonical_relation_type_id=None,
                mapped_from_label=None,
                constraint_id=None,
                dictionary_version=_resolve_dictionary_version(dictionary_service),
                reason=f"Unknown target entity type '{target_type}'.",
            )
        relation_type, mapped_from = _resolve_relation_mapping(
            dictionary_service=dictionary_service,
            relation_label=request.relation_label,
        )
        dictionary_version = _resolve_dictionary_version(dictionary_service)
        if relation_type is None:
            return OntologyValidateRelationResponse(
                validation_state="UNDEFINED",
                canonical_relation_type_id=None,
                mapped_from_label=None,
                constraint_id=None,
                dictionary_version=dictionary_version,
                reason="No canonical relation type matched the provided relation label.",
            )

        state, reason = _resolve_constraint_state(
            dictionary_service=dictionary_service,
            source_type=source_type,
            relation_type=relation_type,
            target_type=target_type,
        )
        return OntologyValidateRelationResponse(
            validation_state=state,
            canonical_relation_type_id=relation_type,
            mapped_from_label=mapped_from,
            constraint_id=_build_constraint_key(
                source_type=source_type,
                relation_type=relation_type,
                target_type=target_type,
            ),
            dictionary_version=dictionary_version,
            reason=reason,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ontology validation failed: {exc!s}",
        ) from exc


@research_spaces_router.post(
    "/{space_id}/ontology/propose_relation_constraint",
    response_model=OntologyProposeRelationConstraintResponse,
    summary="Create a pending relation-constraint proposal and enqueue review",
)
def propose_relation_constraint(
    space_id: UUID,
    request: OntologyProposeRelationConstraintRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    curation_service: ReviewService = Depends(get_curation_service),
    session: Session = Depends(get_session),
) -> OntologyProposeRelationConstraintResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    try:
        source_type = _normalize_entity_type(request.src_type)
        target_type = _normalize_entity_type(request.dst_type)
        if (
            dictionary_service.get_entity_type(source_type, include_inactive=True)
            is None
        ):
            msg = f"Unknown source entity type '{source_type}'."
            raise ValueError(msg)
        if (
            dictionary_service.get_entity_type(target_type, include_inactive=True)
            is None
        ):
            msg = f"Unknown target entity type '{target_type}'."
            raise ValueError(msg)
        canonical_relation_type, _ = _resolve_relation_mapping(
            dictionary_service=dictionary_service,
            relation_label=request.relation_label,
        )
        relation_type_created = False
        created_by = f"agent:{current_user.id}"
        proposal_settings: ResearchSpaceSettings = {
            "dictionary_agent_creation_policy": "PENDING_REVIEW",
        }

        if canonical_relation_type is None:
            canonical_relation_type = _normalize_relation_type_id(
                request.relation_label,
            )
            dictionary_service.create_relation_type(
                relation_type=canonical_relation_type,
                display_name=request.relation_label.strip(),
                description=(
                    request.context.strip()
                    if isinstance(request.context, str) and request.context.strip()
                    else (
                        "Proposed relation type created by ontology proposal endpoint "
                        "for review."
                    )
                ),
                domain_context=request.domain_context,
                created_by=created_by,
                source_ref=request.context,
                research_space_settings=proposal_settings,
            )
            relation_type_created = True

        constraint_key = _build_constraint_key(
            source_type=source_type,
            relation_type=canonical_relation_type,
            target_type=target_type,
        )
        existing_constraints = dictionary_service.get_constraints(
            source_type=source_type,
            relation_type=canonical_relation_type,
            include_inactive=True,
        )
        matching_constraints = [
            constraint
            for constraint in existing_constraints
            if constraint.target_type == target_type
        ]
        proposal_created = False
        if not matching_constraints:
            dictionary_service.create_relation_constraint(
                source_type=source_type,
                relation_type=canonical_relation_type,
                target_type=target_type,
                is_allowed=request.is_allowed,
                requires_evidence=request.requires_evidence,
                created_by=created_by,
                source_ref=request.context,
                research_space_settings=proposal_settings,
            )
            proposal_created = True

        review_item = curation_service.submit(
            session,
            entity_type="relation_constraint",
            entity_id=constraint_key,
            priority=request.priority,
            research_space_id=str(space_id),
        )
        session.commit()
        return OntologyProposeRelationConstraintResponse(
            canonical_relation_type_id=canonical_relation_type,
            constraint_id=constraint_key,
            proposal_created=proposal_created,
            relation_type_created=relation_type_created,
            review_item_id=review_item.id,
            dictionary_version=_resolve_dictionary_version(dictionary_service),
            reason=(
                "Constraint proposal created and queued for review."
                if proposal_created
                else "Constraint already exists; review item queued."
            ),
        )
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Constraint proposal failed: {exc!s}",
        ) from exc
