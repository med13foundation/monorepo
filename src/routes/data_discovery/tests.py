"""Route handlers for executing and retrieving query tests."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.application.services.audit_service import AuditTrailService
from src.application.services.data_discovery_service import DataDiscoveryService
from src.database.session import get_session
from src.domain.entities.user import User
from src.infrastructure.dependency_injection.dependencies import (
    get_data_discovery_service_dependency,
)
from src.infrastructure.observability.request_context import get_audit_context
from src.routes.auth import get_current_active_user
from src.type_definitions.common import AuditContext

from .dependencies import (
    get_audit_trail_service,
    owner_filter_for_user,
    require_session_for_user,
)
from .mappers import test_result_to_response
from .schemas import ExecuteTestRequest, QueryTestResultResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/sessions/{session_id}/tests",
    response_model=QueryTestResultResponse,
    summary="Execute query test",
    description="Execute a query test against a data source in the workbench session.",
)
async def execute_query_test(
    session_id: UUID,
    request: ExecuteTestRequest,
    service: DataDiscoveryService = Depends(get_data_discovery_service_dependency),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_session),
    audit_service: AuditTrailService = Depends(get_audit_trail_service),
    audit_context: AuditContext = Depends(get_audit_context),
) -> QueryTestResultResponse:
    """Execute a query test."""
    try:
        require_session_for_user(session_id, service, current_user)
        owner_filter = owner_filter_for_user(current_user)

        test_request = request.to_domain_request(session_id)

        result = await service.execute_query_test(
            test_request,
            owner_id=owner_filter,
        )
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session or catalog entry not found",
            )
        audit_service.record_action(
            db,
            action="data_discovery.session.execute_test",
            target=("data_discovery_session", str(session_id)),
            actor_id=current_user.id,
            details={
                "catalog_entry_id": request.catalog_entry_id,
                "status": result.status.value,
            },
            context=audit_context,
            success=True,
        )
        return test_result_to_response(result)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to execute query test for session %s", session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute query test",
        ) from exc


@router.get(
    "/sessions/{session_id}/tests",
    response_model=list[QueryTestResultResponse],
    summary="Get session test results",
    description="Retrieve all query test results for a workbench session.",
)
def get_session_test_results(
    session_id: UUID,
    service: DataDiscoveryService = Depends(get_data_discovery_service_dependency),
    current_user: User = Depends(get_current_active_user),
) -> list[QueryTestResultResponse]:
    """Get all test results for a session."""
    try:
        require_session_for_user(session_id, service, current_user)

        results = service.get_session_test_results(session_id)
        return [test_result_to_response(result) for result in results]

    except Exception as exc:
        logger.exception("Failed to get test results for session %s", session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve test results",
        ) from exc


__all__ = ["router"]
