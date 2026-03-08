"""Space-scoped data discovery routes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.application.services.space_data_discovery_service import (
    SpaceDataDiscoveryService,
)
from src.database.session import get_session
from src.domain.entities.user import User, UserRole
from src.infrastructure.dependency_injection.container import container
from src.infrastructure.repositories.research_space_membership_repository import (
    SqlAlchemyResearchSpaceMembershipRepository,
)
from src.infrastructure.repositories.research_space_repository import (
    SqlAlchemyResearchSpaceRepository,
)
from src.routes.auth import get_current_active_user
from src.type_definitions.common import AuditContext

from .data_discovery import dependencies, mappers, schemas

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/research-spaces/{space_id}/discovery",
    tags=["space-discovery"],
)


@dataclass
class SpaceDiscoveryContext:
    """Shared request-scoped objects for space discovery endpoints."""

    db_session: Session
    service: SpaceDataDiscoveryService


def get_space_discovery_context(
    space_id: UUID,
    db: Session = Depends(get_session),
) -> SpaceDiscoveryContext:
    """Build a space discovery context from the current DB session."""
    space_repo = SqlAlchemyResearchSpaceRepository(db)
    if not space_repo.exists(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research space not found",
        )

    data_discovery_service = container.create_data_discovery_service(db)
    discovery_config_service = container.create_discovery_configuration_service(db)
    service = SpaceDataDiscoveryService(
        space_id,
        data_discovery_service,
        discovery_config_service,
    )
    return SpaceDiscoveryContext(db_session=db, service=service)


def require_space_access(
    context: SpaceDiscoveryContext,
    current_user: User,
) -> None:
    """Ensure the requesting user is allowed to access the space."""
    if current_user.role == UserRole.ADMIN:
        return

    space_repo = SqlAlchemyResearchSpaceRepository(context.db_session)
    space = space_repo.find_by_id(context.service.space_id)
    if space is not None and space.owner_id == current_user.id:
        return

    membership_repo = SqlAlchemyResearchSpaceMembershipRepository(
        context.db_session,
    )
    membership = membership_repo.find_by_space_and_user(
        context.service.space_id,
        current_user.id,
    )

    if membership is None or not membership.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this research space",
        )


@router.get(
    "/catalog",
    response_model=list[schemas.SourceCatalogResponse],
    summary="List catalog entries scoped to a research space",
)
def get_space_catalog(
    context: SpaceDiscoveryContext = Depends(get_space_discovery_context),
    current_user: User = Depends(get_current_active_user),
    category: str | None = Query(None, description="Optional category filter"),
    search: str | None = Query(None, description="Optional search query"),
) -> list[schemas.SourceCatalogResponse]:
    """Return catalog entries available to this research space."""
    require_space_access(context, current_user)

    try:
        entries = context.service.get_catalog(category, search)
        return [mappers.catalog_entry_to_response(entry) for entry in entries]
    except Exception as exc:  # pragma: no cover - defensive log
        logger.exception(
            "Failed to load catalog for space %s",
            context.service.space_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load catalog entries",
        ) from exc


@router.get(
    "/sessions",
    response_model=list[schemas.DataDiscoverySessionResponse],
    summary="List discovery sessions within the space",
)
def list_space_sessions(
    include_inactive: bool = Query(False, description="Include inactive sessions"),
    owner_id: UUID | None = Query(
        None,
        description="Filter sessions by owner (admin only)",
    ),
    context: SpaceDiscoveryContext = Depends(get_space_discovery_context),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.DataDiscoverySessionResponse]:
    """List space-scoped sessions for the current user (or all if admin)."""
    require_space_access(context, current_user)

    effective_owner: UUID | None
    if current_user.role == UserRole.ADMIN:
        effective_owner = owner_id
    else:
        effective_owner = current_user.id

    sessions = context.service.list_sessions(
        owner_id=effective_owner,
        include_inactive=include_inactive,
    )
    return [mappers.session_to_response(session) for session in sessions]


@router.post(
    "/sessions",
    response_model=schemas.DataDiscoverySessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a discovery session within the space",
)
def create_space_session(
    payload: schemas.CreateSessionRequest,
    context: SpaceDiscoveryContext = Depends(get_space_discovery_context),
    current_user: User = Depends(get_current_active_user),
    audit_context: AuditContext = Depends(dependencies.get_audit_context_dependency),
) -> schemas.DataDiscoverySessionResponse:
    """Create a new session pinned to the research space."""
    require_space_access(context, current_user)

    session_entity = context.service.create_session(
        owner_id=current_user.id,
        name=payload.name,
        parameters=payload.initial_parameters.to_domain_model(),
    )

    audit_service = dependencies.get_audit_trail_service()
    audit_service.record_action(
        context.db_session,
        action="data_discovery.session.create",
        target=("data_discovery_session", str(session_entity.id)),
        actor_id=current_user.id,
        details={
            "research_space_id": str(context.service.space_id),
            "name": payload.name,
        },
        context=audit_context,
        success=True,
    )
    return mappers.session_to_response(session_entity)


@router.get(
    "/presets",
    response_model=list[schemas.DiscoveryPresetResponse],
    summary="List PubMed presets available within the space",
)
def list_space_presets(
    owner_id: UUID | None = Query(
        None,
        description="Filter presets by owner (admin only)",
    ),
    context: SpaceDiscoveryContext = Depends(get_space_discovery_context),
    current_user: User = Depends(get_current_active_user),
) -> list[schemas.DiscoveryPresetResponse]:
    """Return presets the user can access within this space."""
    require_space_access(context, current_user)
    effective_owner = (
        owner_id
        if current_user.role == UserRole.ADMIN and owner_id
        else current_user.id
    )
    try:
        presets = context.service.list_pubmed_presets(
            effective_owner,
            include_space_presets=True,
        )
    except RuntimeError as exc:  # pragma: no cover - dependency misconfiguration
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Preset service unavailable",
        ) from exc
    return [mappers.preset_to_response(preset) for preset in presets]


@router.get(
    "/defaults",
    response_model=schemas.AdvancedQueryParametersModel,
    summary="Get default advanced parameters for the space",
)
def get_space_default_parameters(
    owner_id: UUID | None = Query(
        None,
        description="Override owner when requesting defaults (admin only)",
    ),
    context: SpaceDiscoveryContext = Depends(get_space_discovery_context),
    current_user: User = Depends(get_current_active_user),
) -> schemas.AdvancedQueryParametersModel:
    """Return default advanced parameters derived from recent sessions or presets."""
    require_space_access(context, current_user)
    effective_owner = (
        owner_id
        if current_user.role == UserRole.ADMIN and owner_id
        else current_user.id
    )
    defaults = context.service.get_default_parameters(owner_id=effective_owner)
    return schemas.AdvancedQueryParametersModel.from_domain(defaults)


@router.get(
    "/sessions/{session_id}",
    response_model=schemas.DataDiscoverySessionResponse,
    summary="Get discovery session details",
)
def get_space_session(
    session_id: UUID,
    context: SpaceDiscoveryContext = Depends(get_space_discovery_context),
    current_user: User = Depends(get_current_active_user),
) -> schemas.DataDiscoverySessionResponse:
    """Retrieve a space-scoped session."""
    require_space_access(context, current_user)

    session = context.service.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data discovery session not found",
        )
    if session.research_space_id != context.service.space_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not belong to this research space",
        )
    if current_user.role != UserRole.ADMIN and session.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this data discovery session",
        )
    return mappers.session_to_response(session)


@router.put(
    "/sessions/{session_id}/parameters",
    response_model=schemas.DataDiscoverySessionResponse,
    summary="Update session parameters",
)
def update_space_session_parameters(
    session_id: UUID,
    payload: schemas.UpdateParametersRequest,
    context: SpaceDiscoveryContext = Depends(get_space_discovery_context),
    current_user: User = Depends(get_current_active_user),
    audit_context: AuditContext = Depends(dependencies.get_audit_context_dependency),
) -> schemas.DataDiscoverySessionResponse:
    """Update query parameters for a session within the space."""
    require_space_access(context, current_user)
    owner_filter = dependencies.owner_filter_for_user(current_user)

    updated = context.service.update_parameters(
        session_id,
        payload.parameters.to_domain_model(),
        owner_id=owner_filter,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data discovery session not found",
        )

    audit_service = dependencies.get_audit_trail_service()
    audit_service.record_action(
        context.db_session,
        action="data_discovery.session.update_parameters",
        target=("data_discovery_session", str(updated.id)),
        actor_id=current_user.id,
        details=payload.parameters.model_dump(),
        context=audit_context,
        success=True,
    )
    return mappers.session_to_response(updated)


@router.put(
    "/sessions/{session_id}/sources/{catalog_entry_id}/toggle",
    response_model=schemas.DataDiscoverySessionResponse,
    summary="Toggle source selection",
)
def toggle_space_session_source(
    session_id: UUID,
    catalog_entry_id: str,
    context: SpaceDiscoveryContext = Depends(get_space_discovery_context),
    current_user: User = Depends(get_current_active_user),
    audit_context: AuditContext = Depends(dependencies.get_audit_context_dependency),
) -> schemas.DataDiscoverySessionResponse:
    """Toggle source selection for a session within this space."""
    require_space_access(context, current_user)
    owner_filter = dependencies.owner_filter_for_user(current_user)

    updated = context.service.toggle_source_selection(
        session_id,
        catalog_entry_id,
        owner_id=owner_filter,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data discovery session not found",
        )

    audit_service = dependencies.get_audit_trail_service()
    audit_service.record_action(
        context.db_session,
        action="data_discovery.session.toggle_source",
        target=("data_discovery_session", str(updated.id)),
        actor_id=current_user.id,
        details={
            "catalog_entry_id": catalog_entry_id,
            "selected_sources": list(updated.selected_sources),
        },
        context=audit_context,
        success=True,
    )
    return mappers.session_to_response(updated)


@router.put(
    "/sessions/{session_id}/selections",
    response_model=schemas.DataDiscoverySessionResponse,
    summary="Set session source selections",
)
def set_space_session_selections(
    session_id: UUID,
    payload: schemas.UpdateSelectionRequest,
    context: SpaceDiscoveryContext = Depends(get_space_discovery_context),
    current_user: User = Depends(get_current_active_user),
    audit_context: AuditContext = Depends(dependencies.get_audit_context_dependency),
) -> schemas.DataDiscoverySessionResponse:
    """Replace the selected sources within a session."""
    require_space_access(context, current_user)
    owner_filter = dependencies.owner_filter_for_user(current_user)

    updated = context.service.set_source_selection(
        session_id,
        payload.source_ids,
        owner_id=owner_filter,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data discovery session not found",
        )

    audit_service = dependencies.get_audit_trail_service()
    audit_service.record_action(
        context.db_session,
        action="data_discovery.session.set_sources",
        target=("data_discovery_session", str(updated.id)),
        actor_id=current_user.id,
        details={"selected_sources": list(updated.selected_sources)},
        context=audit_context,
        success=True,
    )
    return mappers.session_to_response(updated)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete discovery session",
)
def delete_space_session(
    session_id: UUID,
    context: SpaceDiscoveryContext = Depends(get_space_discovery_context),
    current_user: User = Depends(get_current_active_user),
    audit_context: AuditContext = Depends(dependencies.get_audit_context_dependency),
) -> None:
    """Delete a session scoped to this space."""
    require_space_access(context, current_user)
    owner_filter = dependencies.owner_filter_for_user(current_user)

    deleted = context.service.delete_session(
        session_id,
        owner_id=owner_filter,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data discovery session not found",
        )

    audit_service = dependencies.get_audit_trail_service()
    audit_service.record_action(
        context.db_session,
        action="data_discovery.session.delete",
        target=("data_discovery_session", str(session_id)),
        actor_id=current_user.id,
        details={"research_space_id": str(context.service.space_id)},
        context=audit_context,
        success=True,
    )


__all__ = ["router"]
