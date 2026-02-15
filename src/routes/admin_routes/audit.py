"""Administrative audit log query and retention endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from src.application.curation.repositories.audit_repository import (
    AuditLogQuery,
    SqlAlchemyAuditRepository,
)
from src.application.services.audit_service import AuditTrailService
from src.application.services.authorization_service import (
    AuthorizationError,
    AuthorizationService,
)
from src.domain.entities.user import User
from src.domain.value_objects.permission import Permission
from src.infrastructure.dependency_injection.container import container
from src.routes.auth import get_current_active_user

from .audit_schemas import (
    AuditLogListResponse,
    AuditLogQueryParams,
    AuditLogResponse,
    AuditLogRetentionRunRequest,
    AuditLogRetentionRunResponse,
)
from .dependencies import get_admin_db_session

router = APIRouter(tags=["audit"])


def _build_audit_service() -> AuditTrailService:
    return AuditTrailService(SqlAlchemyAuditRepository())


async def _require_permission(
    *,
    permission: Permission,
    current_user: User,
    authz_service: AuthorizationService,
) -> None:
    try:
        await authz_service.require_permission(current_user.id, permission)
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get(
    "/audit/logs",
    response_model=AuditLogListResponse,
    summary="List audit logs",
)
async def list_audit_logs(
    query_params: Annotated[AuditLogQueryParams, Depends()],
    current_user: Annotated[User, Depends(get_current_active_user)],
    authz_service: Annotated[
        AuthorizationService,
        Depends(container.get_authorization_service),
    ],
    session: Annotated[Session, Depends(get_admin_db_session)],
) -> AuditLogListResponse:
    await _require_permission(
        permission=Permission.AUDIT_READ,
        current_user=current_user,
        authz_service=authz_service,
    )

    service = _build_audit_service()
    query = AuditLogQuery(
        action=query_params.action,
        entity_type=query_params.entity_type,
        entity_id=query_params.entity_id,
        actor_id=query_params.actor_id,
        request_id=query_params.request_id,
        ip_address=query_params.ip_address,
        success=query_params.success,
        created_after=query_params.created_after,
        created_before=query_params.created_before,
    )
    result = service.query_logs(
        session,
        query=query,
        page=query_params.page,
        per_page=query_params.per_page,
    )
    return AuditLogListResponse(
        logs=[
            AuditLogResponse.model_validate(service.serialize_log(log))
            for log in result.logs
        ],
        total=result.total,
        page=result.page,
        per_page=result.per_page,
    )


@router.get(
    "/audit/logs/export",
    summary="Export audit logs",
)
async def export_audit_logs(
    query_params: Annotated[AuditLogQueryParams, Depends()],
    current_user: Annotated[User, Depends(get_current_active_user)],
    authz_service: Annotated[
        AuthorizationService,
        Depends(container.get_authorization_service),
    ],
    session: Annotated[Session, Depends(get_admin_db_session)],
) -> Response:
    await _require_permission(
        permission=Permission.AUDIT_READ,
        current_user=current_user,
        authz_service=authz_service,
    )

    service = _build_audit_service()
    query = AuditLogQuery(
        action=query_params.action,
        entity_type=query_params.entity_type,
        entity_id=query_params.entity_id,
        actor_id=query_params.actor_id,
        request_id=query_params.request_id,
        ip_address=query_params.ip_address,
        success=query_params.success,
        created_after=query_params.created_after,
        created_before=query_params.created_before,
    )
    exported = service.export_logs(
        session,
        query=query,
        export_format=query_params.export_format,
        limit=query_params.export_limit,
    )
    now_token = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = "csv" if query_params.export_format == "csv" else "json"
    media_type = (
        "text/csv" if query_params.export_format == "csv" else "application/json"
    )
    return Response(
        content=exported,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="audit_logs_{now_token}.{suffix}"',
        },
    )


@router.post(
    "/audit/logs/retention/run",
    response_model=AuditLogRetentionRunResponse,
    summary="Run audit log retention cleanup",
)
async def run_audit_retention_cleanup(
    request: AuditLogRetentionRunRequest,
    current_user: User = Depends(get_current_active_user),
    authz_service: AuthorizationService = Depends(container.get_authorization_service),
    session: Session = Depends(get_admin_db_session),
) -> AuditLogRetentionRunResponse:
    await _require_permission(
        permission=Permission.SYSTEM_ADMIN,
        current_user=current_user,
        authz_service=authz_service,
    )
    service = _build_audit_service()
    deleted_rows = service.cleanup_old_logs(
        session,
        retention_days=request.retention_days,
        batch_size=request.batch_size,
    )
    return AuditLogRetentionRunResponse(
        deleted_rows=deleted_rows,
        retention_days=request.retention_days,
        batch_size=request.batch_size,
    )


__all__ = ["router"]
