"""Authentication helpers for the standalone graph API service."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.domain.entities.research_space_membership import MembershipRole
from src.domain.entities.user import User, UserRole, UserStatus
from src.graph.core.access import GraphAccessRole, GraphPrincipal
from src.graph.core.tenancy import (
    GraphRlsSessionContext,
    GraphTenant,
    GraphTenantMembership,
    create_graph_rls_session_context,
)
from src.infrastructure.security.jwt_provider import JWTProvider

from .config import get_settings

security = HTTPBearer(auto_error=False)

_GRAPH_ACCESS_ROLE_BY_MEMBERSHIP_ROLE = {
    MembershipRole.VIEWER: GraphAccessRole.VIEWER,
    MembershipRole.RESEARCHER: GraphAccessRole.RESEARCHER,
    MembershipRole.CURATOR: GraphAccessRole.CURATOR,
    MembershipRole.ADMIN: GraphAccessRole.ADMIN,
    MembershipRole.OWNER: GraphAccessRole.OWNER,
}


class GraphServiceUser(User):
    """Authenticated graph-service caller with service-local control-plane claims."""

    is_graph_admin: bool = False


def _parse_graph_admin_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"1", "true", "yes", "on"}
    return False


def _build_user_from_test_headers(request: Request) -> GraphServiceUser | None:
    settings = get_settings()
    if not settings.allow_test_auth_headers:
        return None

    test_user_id = request.headers.get("X-TEST-USER-ID")
    test_user_email = request.headers.get("X-TEST-USER-EMAIL")
    test_user_role = request.headers.get("X-TEST-USER-ROLE")
    if not test_user_id or not test_user_email:
        return None

    role = UserRole.VIEWER
    if test_user_role is not None and test_user_role.strip():
        try:
            role = UserRole(test_user_role.lower())
        except ValueError:
            role = UserRole.VIEWER

    username = test_user_email.split("@")[0]
    return GraphServiceUser(
        id=UUID(test_user_id),
        email=test_user_email,
        username=username,
        full_name=test_user_email,
        role=role,
        status=UserStatus.ACTIVE,
        hashed_password="test",
        is_graph_admin=_parse_graph_admin_flag(
            request.headers.get("X-TEST-GRAPH-ADMIN"),
        ),
    )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> GraphServiceUser:
    """Resolve the current caller from JWT or test headers."""
    test_user = _build_user_from_test_headers(request)
    if test_user is not None:
        return test_user

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    provider = JWTProvider(
        secret_key=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    try:
        payload = provider.decode_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    sub_value = payload.get("sub")
    if not isinstance(sub_value, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    role_value = payload.get("role")
    role = UserRole.VIEWER
    if isinstance(role_value, str):
        try:
            role = UserRole(role_value.lower())
        except ValueError:
            role = UserRole.VIEWER

    user_id = UUID(sub_value)
    email = f"{user_id}@graph-service.example.com"
    return GraphServiceUser(
        id=user_id,
        email=email,
        username=sub_value,
        full_name=email,
        role=role,
        status=UserStatus.ACTIVE,
        hashed_password="token",
        is_graph_admin=_parse_graph_admin_flag(payload.get("graph_admin")),
    )


def get_current_active_user(
    current_user: GraphServiceUser = Depends(get_current_user),
) -> GraphServiceUser:
    """Require an active user account."""
    if not current_user.can_authenticate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )
    return current_user


def is_graph_service_admin(current_user: User) -> bool:
    """Return whether one authenticated caller has graph-service admin access."""
    return isinstance(current_user, GraphServiceUser) and current_user.is_graph_admin


def to_graph_principal(current_user: User) -> GraphPrincipal:
    """Map one authenticated caller onto the graph-core principal abstraction."""
    return GraphPrincipal(
        subject_id=str(current_user.id),
        is_platform_admin=is_graph_service_admin(current_user),
    )


def to_graph_access_role(membership_role: MembershipRole) -> GraphAccessRole:
    """Map one application membership role onto graph-core access semantics."""
    return _GRAPH_ACCESS_ROLE_BY_MEMBERSHIP_ROLE[membership_role]


def to_graph_tenant(space_id: UUID) -> GraphTenant:
    """Map one graph-space identifier onto the graph-core tenant abstraction."""
    return GraphTenant(tenant_id=str(space_id))


def to_graph_tenant_membership(
    *,
    space_id: UUID,
    membership_role: MembershipRole | None,
) -> GraphTenantMembership:
    """Map one graph-space membership onto graph-core tenancy abstractions."""
    return GraphTenantMembership(
        tenant=to_graph_tenant(space_id),
        membership_role=(
            to_graph_access_role(membership_role)
            if membership_role is not None
            else None
        ),
    )


def to_graph_rls_session_context(
    current_user: User,
    *,
    bypass_rls: bool = False,
) -> GraphRlsSessionContext:
    """Map one authenticated caller onto graph-core RLS session settings."""
    return create_graph_rls_session_context(
        principal=to_graph_principal(current_user),
        bypass_rls=bypass_rls,
    )


__all__ = [
    "GraphServiceUser",
    "get_current_active_user",
    "get_current_user",
    "is_graph_service_admin",
    "security",
    "to_graph_access_role",
    "to_graph_principal",
    "to_graph_rls_session_context",
    "to_graph_tenant",
    "to_graph_tenant_membership",
]
