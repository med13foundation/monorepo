"""Statement of Understanding API routes scoped to research spaces."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.session import get_session
from src.domain.entities.user import User
from src.domain.value_objects import EvidenceLevel, ProteinDomain, StatementStatus
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)
from src.models.api import (
    MechanismResponse,
    PaginatedResponse,
    ProteinDomainPayload,
    StatementCreate,
    StatementResponse,
    StatementUpdate,
)
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    require_curator_role,
    require_researcher_role,
    verify_space_membership,
)
from src.routes.serializers import serialize_mechanism, serialize_statement
from src.type_definitions.common import StatementUpdate as StatementUpdatePayload

from .router import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)

if TYPE_CHECKING:
    from src.application.services import (
        MembershipManagementService,
        StatementApplicationService,
    )


class StatementListParams(BaseModel):
    page: int = Field(1, ge=1, description="Page number")
    per_page: int = Field(20, ge=1, le=100, description="Items per page")
    search: str | None = Field(None, description="Search by title/summary")
    sort_by: str = Field("title", description="Sort field")
    sort_order: str = Field("asc", pattern="^(asc|desc)$", description="Sort order")

    model_config = {"extra": "ignore"}


def get_statement_service(
    db: Session = Depends(get_session),
) -> StatementApplicationService:
    container = get_legacy_dependency_container()
    return container.create_statement_application_service(db)


def _payload_to_domains(
    payloads: list[ProteinDomainPayload],
) -> list[ProteinDomain]:
    return [ProteinDomain.model_validate(payload.model_dump()) for payload in payloads]


def _to_statement_update_payload(
    payload: StatementUpdate,
) -> StatementUpdatePayload:
    updates: StatementUpdatePayload = {}
    if payload.title is not None:
        updates["title"] = payload.title
    if payload.summary is not None:
        updates["summary"] = payload.summary
    if payload.evidence_tier is not None:
        updates["evidence_tier"] = payload.evidence_tier.value
    if payload.confidence_score is not None:
        updates["confidence_score"] = payload.confidence_score
    if payload.status is not None:
        updates["status"] = payload.status.value
    if payload.source is not None:
        updates["source"] = payload.source
    if payload.protein_domains is not None:
        updates["protein_domains"] = [
            domain.model_dump() for domain in payload.protein_domains
        ]
    if payload.phenotype_ids is not None:
        updates["phenotype_ids"] = payload.phenotype_ids
    if payload.promoted_mechanism_id is not None:
        updates["promoted_mechanism_id"] = payload.promoted_mechanism_id
    return updates


def _require_space_membership(
    space_id: UUID,
    current_user: User,
    membership_service: MembershipManagementService,
    session: Session,
) -> None:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )


@research_spaces_router.get(
    "/{space_id}/statements",
    summary="List statements in space",
    response_model=PaginatedResponse[StatementResponse],
)
async def list_space_statements(
    space_id: UUID,
    params: StatementListParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: StatementApplicationService = Depends(get_statement_service),
    session: Session = Depends(get_session),
) -> PaginatedResponse[StatementResponse]:
    """Retrieve a paginated list of statements for a research space."""
    _require_space_membership(space_id, current_user, membership_service, session)
    filters = {"research_space_id": str(space_id)}
    try:
        if params.search:
            statements = service.search_statements(
                params.search,
                limit=params.per_page,
                filters=filters,
            )
            total = len(statements)
            page = 1
        else:
            statements, total = service.list_statements(
                page=params.page,
                per_page=params.per_page,
                sort_by=params.sort_by,
                sort_order=params.sort_order,
                filters=filters,
            )
            page = params.page

        responses = [serialize_statement(statement) for statement in statements]
        total_pages = (total + params.per_page - 1) // params.per_page
        return PaginatedResponse(
            items=responses,
            total=total,
            page=page,
            per_page=params.per_page,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve statements: {exc!s}",
        ) from exc


@research_spaces_router.get(
    "/{space_id}/statements/{statement_id}",
    summary="Get statement by ID",
    response_model=StatementResponse,
)
async def get_space_statement(
    space_id: UUID,
    statement_id: int,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: StatementApplicationService = Depends(get_statement_service),
    session: Session = Depends(get_session),
) -> StatementResponse:
    """Retrieve a statement by ID within a research space."""
    _require_space_membership(space_id, current_user, membership_service, session)
    try:
        statement = service.get_statement_by_id(statement_id)
        if not statement or statement.research_space_id != space_id:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Statement {statement_id} not found",
            )
        return serialize_statement(statement)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve statement: {exc!s}",
        ) from exc


@research_spaces_router.post(
    "/{space_id}/statements",
    summary="Create statement",
    response_model=StatementResponse,
    status_code=HTTP_201_CREATED,
)
async def create_space_statement(
    space_id: UUID,
    payload: StatementCreate,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: StatementApplicationService = Depends(get_statement_service),
    session: Session = Depends(get_session),
) -> StatementResponse:
    """Create a new statement within a research space."""
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        protein_domains = _payload_to_domains(payload.protein_domains)
        statement = service.create_statement(
            title=payload.title,
            research_space_id=space_id,
            summary=payload.summary,
            evidence_tier=EvidenceLevel(payload.evidence_tier.value),
            confidence_score=payload.confidence_score,
            status=StatementStatus(payload.status.value),
            source=payload.source,
            protein_domains=protein_domains,
            phenotype_ids=payload.phenotype_ids,
        )
        return serialize_statement(statement)
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Failed to create statement: {exc!s}",
        ) from exc


@research_spaces_router.put(
    "/{space_id}/statements/{statement_id}",
    summary="Update statement",
    response_model=StatementResponse,
)
async def update_space_statement(
    space_id: UUID,
    statement_id: int,
    payload: StatementUpdate,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: StatementApplicationService = Depends(get_statement_service),
    session: Session = Depends(get_session),
) -> StatementResponse:
    """Update an existing statement within a research space."""
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        existing = service.get_statement_by_id(statement_id)
        if not existing or existing.research_space_id != space_id:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Statement {statement_id} not found",
            )
        updates = _to_statement_update_payload(payload)
        statement = service.update_statement(statement_id, updates)
        return serialize_statement(statement)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update statement: {exc!s}",
        ) from exc


@research_spaces_router.delete(
    "/{space_id}/statements/{statement_id}",
    summary="Delete statement",
)
async def delete_space_statement(
    space_id: UUID,
    statement_id: int,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: StatementApplicationService = Depends(get_statement_service),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    """Delete a statement by ID within a research space."""
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        existing = service.get_statement_by_id(statement_id)
        if not existing or existing.research_space_id != space_id:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Statement {statement_id} not found",
            )
        deleted = service.delete_statement(statement_id)
        if not deleted:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Statement {statement_id} not found",
            )
        return {"message": "Statement deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete statement: {exc!s}",
        ) from exc


@research_spaces_router.post(
    "/{space_id}/statements/{statement_id}/promote",
    summary="Promote statement to mechanism",
    response_model=MechanismResponse,
)
async def promote_statement_to_mechanism(
    space_id: UUID,
    statement_id: int,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: StatementApplicationService = Depends(get_statement_service),
    session: Session = Depends(get_session),
) -> MechanismResponse:
    """Promote a well-supported statement into a canonical mechanism."""
    require_curator_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    try:
        mechanism = service.promote_to_mechanism(
            statement_id,
            research_space_id=space_id,
        )
        return serialize_mechanism(mechanism)
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to promote statement: {exc!s}",
        ) from exc


__all__ = ["research_spaces_router"]
