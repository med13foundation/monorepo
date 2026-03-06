"""
Authentication routes for MED13 Resource Library.

Provides REST API endpoints for user authentication, session management,
and user registration.
"""

import os
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from src.application.dto.auth_requests import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterUserRequest,
    ResetPasswordRequest,
    UpdateProfileRequest,
    UpdateUserRequest,
)
from src.application.dto.auth_responses import (
    ErrorResponse,
    GenericSuccessResponse,
    LoginResponse,
    TokenRefreshResponse,
    UserProfileResponse,
    UserPublic,
    ValidationErrorResponse,
)
from src.application.services import (
    authentication_service,
    authorization_service,
    user_management_service,
)
from src.domain.entities.user import User, UserRole, UserStatus
from src.domain.value_objects.permission import Permission
from src.infrastructure.dependency_injection.container import container
from src.infrastructure.dependency_injection.dependencies import (
    get_authentication_service_dependency,
)

# Create router
auth_router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        422: {"model": ValidationErrorResponse, "description": "Validation Error"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"},
    },
)

# Security scheme
security = HTTPBearer(auto_error=False)


class RouteInfo(BaseModel):
    """Lightweight representation of an auth route."""

    path: str
    methods: set[str] | None
    name: str | None


class RouteListResponse(BaseModel):
    """Response payload for listing auth routes."""

    routes: list[RouteInfo]


@auth_router.get("/test")
async def test_endpoint() -> dict[str, str]:
    return {"message": "Auth routes are working!"}


@auth_router.get("/routes", response_model=RouteListResponse)
async def list_routes() -> RouteListResponse:
    routes = [
        RouteInfo(
            path=getattr(route, "path", str(route)),
            methods=getattr(route, "methods", None),
            name=getattr(route, "name", None),
        )
        for route in auth_router.routes
    ]
    return RouteListResponse(routes=routes)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    auth_service: authentication_service.AuthenticationService = Depends(
        get_authentication_service_dependency,
    ),
) -> User:
    # ------------------------------------------------------------------
    # Test bypass: allow injecting a user via headers in non-production
    # contexts to keep integration tests lightweight (no real JWT).
    # ------------------------------------------------------------------
    allow_test_headers = (
        os.getenv("TESTING") == "true"
        or os.getenv("MED13_BYPASS_TEST_AUTH_HEADERS") == "1"
    )
    test_user_id = request.headers.get("X-TEST-USER-ID")
    test_user_email = request.headers.get("X-TEST-USER-EMAIL")
    test_user_role = request.headers.get("X-TEST-USER-ROLE")
    if allow_test_headers and test_user_id and test_user_email and test_user_role:
        try:
            role_enum = UserRole(test_user_role.lower())
        except ValueError:
            role_enum = UserRole.VIEWER

        username_value = test_user_email.split("@")[0]
        return User(
            id=UUID(test_user_id),
            email=test_user_email,
            username=username_value,
            full_name=test_user_email,
            role=role_enum,
            status=UserStatus.ACTIVE,
            hashed_password="test",
        )

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user = await auth_service.validate_token(credentials.credentials)
        return user
    except authentication_service.AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.can_authenticate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )
    return current_user


async def require_permission(
    permission: str,
    current_user: User = Depends(get_current_active_user),
    authz_service: authorization_service.AuthorizationService = Depends(
        container.get_authorization_service,
    ),
) -> User:
    try:
        # Convert string to Permission enum
        perm_enum = Permission(permission)
        await authz_service.require_permission(current_user.id, perm_enum)
        return current_user
    except (ValueError, authorization_service.AuthorizationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission}",
        )


async def require_role(
    role: str,
    current_user: User = Depends(get_current_active_user),
) -> User:
    try:
        required_role = UserRole(role.lower())
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' required",
            )
        return current_user
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {role}",
        )


@auth_router.post(
    "/login",
    response_model=LoginResponse,
    summary="User login",
    description="Authenticate user with email and password",
)
async def login(
    request: LoginRequest,
    http_request: Request,
    auth_service: authentication_service.AuthenticationService = Depends(
        get_authentication_service_dependency,
    ),
) -> LoginResponse:
    try:
        # Extract IP address and user agent from request
        ip_address = http_request.client.host if http_request.client else None
        user_agent = http_request.headers.get("user-agent")

        # Use the actual authentication service
        response = await auth_service.authenticate_user(
            request,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return response
    except authentication_service.InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except authentication_service.AccountLockedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except authentication_service.AccountInactiveError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except authentication_service.AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {e!s}",
        )


@auth_router.post(
    "/refresh",
    response_model=TokenRefreshResponse,
    summary="Refresh access token",
    description="Get new access token using refresh token",
)
async def refresh_token(
    request: RefreshTokenRequest,
    auth_service: authentication_service.AuthenticationService = Depends(
        container.get_authentication_service,
    ),
) -> TokenRefreshResponse:
    try:
        response = await auth_service.refresh_token(request.refresh_token)
        return response
    except authentication_service.AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )


@auth_router.post(
    "/logout",
    response_model=GenericSuccessResponse,
    summary="User logout",
    description="Revoke current session",
)
async def logout(
    current_user: User = Depends(get_current_user),
    auth_service: authentication_service.AuthenticationService = Depends(
        container.get_authentication_service,
    ),
) -> GenericSuccessResponse:
    try:
        # TODO: Get token from request and revoke it via service
        return GenericSuccessResponse(message="Logged out successfully")
    except authentication_service.AuthenticationError:
        # Even if logout fails, we return success for security
        return GenericSuccessResponse(message="Logged out successfully")


@auth_router.post(
    "/register",
    response_model=GenericSuccessResponse,
    summary="User registration",
    description="Register a new user account",
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    request: RegisterUserRequest,
    user_service: user_management_service.UserManagementService = Depends(
        container.get_user_management_service,
    ),
) -> GenericSuccessResponse:
    try:
        await user_service.register_user(request)

        # TODO: Send verification email in background

        return GenericSuccessResponse(
            message="User registered successfully. Please check your email for verification instructions.",
        )
    except user_management_service.UserAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except user_management_service.UserManagementError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {e!s}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {e!s}",
        )


@auth_router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get current user profile",
    description="Get detailed information about the current user",
)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user),
) -> UserProfileResponse:
    return UserProfileResponse(user=UserPublic.from_user(current_user))


@auth_router.put(
    "/me",
    response_model=UserProfileResponse,
    summary="Update user profile",
    description="Update current user's profile information",
)
async def update_user_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_active_user),
    user_service: user_management_service.UserManagementService = Depends(
        container.get_user_management_service,
    ),
) -> UserProfileResponse:
    try:
        update_request = UpdateUserRequest(
            full_name=request.full_name,
            role=None,  # Users cannot change their own role
        )

        updated_user = await user_service.update_user(
            user_id=current_user.id,
            request=update_request,
            updated_by=current_user.id,
        )

        return UserProfileResponse(user=UserPublic.from_user(updated_user))
    except user_management_service.UserManagementError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@auth_router.post(
    "/me/change-password",
    response_model=GenericSuccessResponse,
    summary="Change password",
    description="Change current user's password",
)
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    user_service: user_management_service.UserManagementService = Depends(
        container.get_user_management_service,
    ),
) -> GenericSuccessResponse:
    try:
        await user_service.change_password(
            user_id=current_user.id,
            old_password=request.old_password,
            new_password=request.new_password,
        )

        # TODO: Send confirmation email

        return GenericSuccessResponse(message="Password changed successfully")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except user_management_service.UserManagementError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@auth_router.post(
    "/forgot-password",
    response_model=GenericSuccessResponse,
    summary="Request password reset",
    description="Send password reset email to user",
)
async def forgot_password(
    request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    user_service: user_management_service.UserManagementService = Depends(
        container.get_user_management_service,
    ),
) -> GenericSuccessResponse:
    try:
        masked_email = await user_service.request_password_reset(request.email)

        # TODO: Send password reset email in background

        return GenericSuccessResponse(
            message=f"Password reset email sent to {masked_email}",
        )
    except user_management_service.UserManagementError:
        # Don't reveal if email exists or not for security
        return GenericSuccessResponse(
            message="If the email exists, a password reset link has been sent.",
        )


@auth_router.post(
    "/reset-password",
    response_model=GenericSuccessResponse,
    summary="Reset password",
    description="Reset user password using reset token",
)
async def reset_password(
    request: ResetPasswordRequest,
    user_service: user_management_service.UserManagementService = Depends(
        container.get_user_management_service,
    ),
) -> GenericSuccessResponse:
    try:
        await user_service.reset_password(
            token=request.token,
            new_password=request.new_password,
        )

        return GenericSuccessResponse(message="Password reset successfully")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except user_management_service.UserManagementError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired reset token",
        )


@auth_router.post(
    "/verify-email/{token}",
    response_model=GenericSuccessResponse,
    summary="Verify email address",
    description="Verify user email using verification token",
)
async def verify_email(
    token: str,
    user_service: user_management_service.UserManagementService = Depends(
        container.get_user_management_service,
    ),
) -> GenericSuccessResponse:
    try:
        await user_service.verify_email(token)
        return GenericSuccessResponse(message="Email verified successfully")
    except user_management_service.UserManagementError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token",
        )
