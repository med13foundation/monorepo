"""Route handlers for data discovery session management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.services.data_discovery_service import DataDiscoveryService

# Import DTOs directly from application layer
from src.application.services.data_discovery_service.dtos import (
    CreateSessionRequest,
    DataDiscoverySessionResponse,
    OrchestratedSessionState,
    UpdateParametersRequest,
    UpdateSelectionRequest,
)
from src.application.services.data_discovery_service.mappers import (
    data_discovery_session_to_response,
)
from src.application.services.data_discovery_service.requests import (
    CreateDataDiscoverySessionRequest,
    UpdateSessionParametersRequest,
)

# Using relative import to avoid circular dependency issues at module level
from src.application.services.data_discovery_service.session_orchestration import (
    SessionOrchestrationService,
)
from src.database.seed import DEFAULT_RESEARCH_SPACE_ID
from src.domain.entities.user import User
from src.infrastructure.dependency_injection.dependencies import (
    get_data_discovery_service_dependency,
)
from src.routes.auth import get_current_active_user

router = APIRouter()


# Dependency to get Orchestration Service
def get_orchestration_service(
    discovery_service: DataDiscoveryService = Depends(
        get_data_discovery_service_dependency,
    ),
) -> SessionOrchestrationService:
    # Manually inject repositories from the main service for now
    # In a pure DI setup, we would inject repositories directly
    return SessionOrchestrationService(
        discovery_service._session_repo,
        discovery_service._catalog_repo,
    )


@router.post(
    "/sessions",
    response_model=DataDiscoverySessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create workbench session",
    description="Create a new data discovery workbench session.",
)
def create_session(
    payload: CreateSessionRequest,
    current_user: User = Depends(get_current_active_user),
    service: DataDiscoveryService = Depends(get_data_discovery_service_dependency),
) -> DataDiscoverySessionResponse:
    """Create a new data discovery workbench session."""
    session_request = CreateDataDiscoverySessionRequest(
        owner_id=current_user.id,
        name=payload.name,
        research_space_id=payload.research_space_id or DEFAULT_RESEARCH_SPACE_ID,
        initial_parameters=payload.initial_parameters.to_domain_model(),
    )
    session = service.create_session(session_request)
    return data_discovery_session_to_response(session)


@router.get(
    "/sessions",
    response_model=list[DataDiscoverySessionResponse],
    summary="List user sessions",
    description="List all data discovery sessions for the current user.",
)
def list_sessions(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    service: DataDiscoveryService = Depends(get_data_discovery_service_dependency),
) -> list[DataDiscoverySessionResponse]:
    """List sessions for the current user."""
    # TODO: Implement proper pagination in service
    sessions = service.get_user_sessions(current_user.id)
    return [
        data_discovery_session_to_response(s) for s in sessions[offset : offset + limit]
    ]


@router.get(
    "/sessions/{session_id}",
    response_model=DataDiscoverySessionResponse,
    summary="Get session details",
    description="Retrieve details for a specific session.",
)
def get_session_details(
    session_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: DataDiscoveryService = Depends(get_data_discovery_service_dependency),
) -> DataDiscoverySessionResponse:
    """Get details for a specific session."""
    # Authorization handled by require_session_for_user logic inside service if needed
    # For now, we rely on service logic or manual check
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if session.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )
    return data_discovery_session_to_response(session)


@router.patch(
    "/sessions/{session_id}/parameters",
    response_model=DataDiscoverySessionResponse,
    summary="Update session parameters",
    description="Update query parameters for a session.",
)
def update_session_parameters(
    session_id: UUID,
    payload: UpdateParametersRequest,
    current_user: User = Depends(get_current_active_user),
    service: DataDiscoveryService = Depends(get_data_discovery_service_dependency),
) -> DataDiscoverySessionResponse:
    """Update session parameters."""
    update_req = UpdateSessionParametersRequest(
        session_id=session_id,
        parameters=payload.parameters.to_domain_model(),
    )
    session = service.update_session_parameters(update_req)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return data_discovery_session_to_response(session)


# --- Orchestration Endpoints ---


@router.get(
    "/sessions/{session_id}/state",
    response_model=OrchestratedSessionState,
    summary="Get orchestrated session state",
    description="Get complete session state with derived capabilities and validation status.",
)
def get_orchestrated_state(
    session_id: UUID,
    current_user: User = Depends(get_current_active_user),
    orchestrator: SessionOrchestrationService = Depends(get_orchestration_service),
) -> OrchestratedSessionState:
    """Get the orchestrated state (ViewModel) for a session."""
    try:
        return orchestrator.get_orchestrated_state(session_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post(
    "/sessions/{session_id}/selection",
    response_model=OrchestratedSessionState,
    summary="Update source selection",
    description="Update selected sources and return new orchestrated state.",
)
def update_source_selection(
    session_id: UUID,
    request: UpdateSelectionRequest,
    current_user: User = Depends(get_current_active_user),
    orchestrator: SessionOrchestrationService = Depends(get_orchestration_service),
) -> OrchestratedSessionState:
    """Update selection and return new state."""
    try:
        return orchestrator.update_selection(
            session_id,
            request.source_ids,
            current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete session",
    description="Delete a data discovery session.",
)
def delete_session(
    session_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: DataDiscoveryService = Depends(get_data_discovery_service_dependency),
) -> None:
    """Delete a session."""
    service.delete_session(session_id)
