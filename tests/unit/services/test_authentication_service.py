"""
Unit tests for Authentication Service.

Tests authentication, token validation, and session management with regression tests
for datetime comparison issues.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.services.authentication_service import (
    AuthenticationError,
    AuthenticationService,
)
from src.domain.entities.session import SessionStatus, UserSession
from src.domain.entities.user import User, UserRole, UserStatus


class TestAuthenticationService:
    """Test authentication service functionality."""

    @pytest.fixture
    def mock_user_repository(self):
        """Create mock user repository."""
        repo = AsyncMock()
        return repo

    @pytest.fixture
    def mock_session_repository(self):
        """Create mock session repository."""
        repo = AsyncMock()
        return repo

    @pytest.fixture
    def mock_jwt_provider(self):
        """Create mock JWT provider."""
        provider = MagicMock()
        return provider

    @pytest.fixture
    def mock_password_hasher(self):
        """Create mock password hasher."""
        hasher = MagicMock()
        return hasher

    @pytest.fixture
    def auth_service(
        self,
        mock_user_repository,
        mock_session_repository,
        mock_jwt_provider,
        mock_password_hasher,
    ):
        """Create authentication service with mocked dependencies."""
        return AuthenticationService(
            user_repository=mock_user_repository,
            session_repository=mock_session_repository,
            jwt_provider=mock_jwt_provider,
            password_hasher=mock_password_hasher,
        )

    @pytest.fixture
    def sample_user(self):
        """Create sample user for testing."""
        return User(
            id=uuid4(),
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hashed_password_for_testing",
            role=UserRole.RESEARCHER,
            status=UserStatus.ACTIVE,
            email_verified=True,
        )

    @pytest.fixture
    def admin_user(self):
        """Create sample admin user for testing."""
        return User(
            id=uuid4(),
            email="admin@example.com",
            username="adminuser",
            full_name="Admin User",
            hashed_password="hashed_password_for_testing",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            email_verified=True,
        )

    @pytest.mark.asyncio
    async def test_authenticate_user_mints_graph_admin_claim_for_admins(
        self,
        auth_service,
        mock_user_repository,
        mock_jwt_provider,
        mock_password_hasher,
        admin_user,
    ):
        from src.application.dto.auth_requests import LoginRequest

        mock_user_repository.get_by_email.return_value = admin_user
        mock_user_repository.update = AsyncMock()
        mock_password_hasher.verify_password.return_value = True
        mock_jwt_provider.create_access_token.return_value = "access-token"
        mock_jwt_provider.create_refresh_token.return_value = "refresh-token"
        auth_service.session_lifecycle.create_session = AsyncMock()

        response = await auth_service.authenticate_user(
            LoginRequest(email=admin_user.email, password="correct-password"),
        )

        mock_jwt_provider.create_access_token.assert_called_once_with(
            admin_user.id,
            admin_user.role.value,
            extra_claims={"graph_admin": True},
        )
        assert response.access_token == "access-token"

    @pytest.mark.asyncio
    async def test_refresh_token_preserves_graph_admin_claim_for_admins(
        self,
        auth_service,
        mock_user_repository,
        mock_session_repository,
        mock_jwt_provider,
        admin_user,
    ):
        refresh_token = "refresh-token"
        session = UserSession(
            user_id=admin_user.id,
            session_token="old-access-token",
            refresh_token=refresh_token,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
            refresh_expires_at=datetime.now(UTC) + timedelta(days=7),
            status=SessionStatus.ACTIVE,
        )
        mock_session_repository.get_active_by_refresh_token.return_value = session
        mock_session_repository.update = AsyncMock()
        mock_user_repository.get_by_id.return_value = admin_user
        mock_jwt_provider.create_access_token.return_value = "new-access-token"
        mock_jwt_provider.create_refresh_token.return_value = "new-refresh-token"

        response = await auth_service.refresh_token(refresh_token)

        mock_jwt_provider.create_access_token.assert_called_once_with(
            admin_user.id,
            admin_user.role.value,
            extra_claims={"graph_admin": True},
        )
        assert response.access_token == "new-access-token"

    @pytest.mark.asyncio
    async def test_validate_token_success_with_timezone_aware_session(
        self,
        auth_service,
        mock_user_repository,
        mock_session_repository,
        mock_jwt_provider,
        sample_user,
    ):
        """Regression test: Token validation with timezone-aware session datetimes."""
        token = "valid_jwt_token"
        user_id = sample_user.id

        # Mock JWT decode
        mock_jwt_provider.decode_token.return_value = {
            "sub": str(user_id),
            "type": "access",
            "role": "researcher",
        }

        # Mock user repository
        mock_user_repository.get_by_id.return_value = sample_user

        # Create session with timezone-aware datetimes
        expires_at = datetime.now(UTC) + timedelta(minutes=15)
        refresh_expires_at = datetime.now(UTC) + timedelta(days=7)
        session = UserSession(
            user_id=user_id,
            session_token=token,
            refresh_token="refresh_token",
            expires_at=expires_at,
            refresh_expires_at=refresh_expires_at,
            status=SessionStatus.ACTIVE,
        )
        object.__setattr__(
            session,
            "last_activity",
            datetime.now(UTC) - timedelta(minutes=10),
        )

        # Mock session repository
        mock_session_repository.get_by_access_token.return_value = session
        mock_session_repository.update = AsyncMock()

        # Validate token - should not raise TypeError
        result = await auth_service.validate_token(token)

        assert result == sample_user
        mock_jwt_provider.decode_token.assert_called_once_with(token)
        mock_user_repository.get_by_id.assert_called_once_with(user_id)
        mock_session_repository.get_by_access_token.assert_called_once_with(token)
        mock_session_repository.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_token_success_with_timezone_naive_session(
        self,
        auth_service,
        mock_user_repository,
        mock_session_repository,
        mock_jwt_provider,
        sample_user,
    ):
        """Regression test: Token validation with timezone-naive session datetimes (from database)."""
        token = "valid_jwt_token"
        user_id = sample_user.id

        # Mock JWT decode
        mock_jwt_provider.decode_token.return_value = {
            "sub": str(user_id),
            "type": "access",
            "role": "researcher",
        }

        # Mock user repository
        mock_user_repository.get_by_id.return_value = sample_user

        # Create session with UTC-aware datetimes first (passes validation)
        base_time = datetime.now(UTC)
        expires_at = base_time + timedelta(minutes=15)
        refresh_expires_at = base_time + timedelta(days=7)
        session = UserSession(
            user_id=user_id,
            session_token=token,
            refresh_token="refresh_token",
            expires_at=expires_at,
            refresh_expires_at=refresh_expires_at,
            status=SessionStatus.ACTIVE,
        )
        object.__setattr__(
            session,
            "last_activity",
            datetime.now(UTC) - timedelta(minutes=10),
        )
        # Simulate database load: replace with naive datetimes
        object.__setattr__(session, "expires_at", expires_at.replace(tzinfo=None))
        object.__setattr__(
            session,
            "refresh_expires_at",
            refresh_expires_at.replace(tzinfo=None),
        )

        # Mock session repository
        mock_session_repository.get_by_access_token.return_value = session
        mock_session_repository.update = AsyncMock()

        # Validate token - should not raise TypeError: can't compare offset-naive and offset-aware datetimes
        result = await auth_service.validate_token(token)

        assert result == sample_user
        # Verify session.is_active() was called without errors
        assert session.is_active() is True
        mock_session_repository.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_token_with_expired_naive_session(
        self,
        auth_service,
        mock_user_repository,
        mock_session_repository,
        mock_jwt_provider,
        sample_user,
    ):
        """Regression test: Token validation with expired session using naive datetime."""
        token = "valid_jwt_token"
        user_id = sample_user.id

        # Mock JWT decode
        mock_jwt_provider.decode_token.return_value = {
            "sub": str(user_id),
            "type": "access",
            "role": "researcher",
        }

        # Mock user repository
        mock_user_repository.get_by_id.return_value = sample_user

        # Create session with valid UTC-aware datetimes first
        base_time = datetime.now(UTC)
        expires_at = base_time + timedelta(minutes=15)
        refresh_expires_at = base_time + timedelta(days=1)
        session = UserSession(
            user_id=user_id,
            session_token=token,
            refresh_token="refresh_token",
            expires_at=expires_at,
            refresh_expires_at=refresh_expires_at,
            status=SessionStatus.ACTIVE,
        )
        # Simulate database load: replace with expired naive datetime
        past_time_naive = (base_time - timedelta(hours=1)).replace(tzinfo=None)
        future_time_naive = (base_time + timedelta(days=1)).replace(tzinfo=None)
        object.__setattr__(session, "expires_at", past_time_naive)
        object.__setattr__(session, "refresh_expires_at", future_time_naive)

        # Mock session repository
        mock_session_repository.get_by_access_token.return_value = session
        mock_session_repository.update = AsyncMock()

        # Validate token - should succeed (token is valid, session is expired but that's OK)
        result = await auth_service.validate_token(token)

        assert result == sample_user
        # Session should be identified as expired
        assert session.is_expired() is True
        assert session.is_active() is False
        # Update should not be called since session is not active
        mock_session_repository.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_token_with_mixed_timezone_session(
        self,
        auth_service,
        mock_user_repository,
        mock_session_repository,
        mock_jwt_provider,
        sample_user,
    ):
        """Regression test: Token validation with mixed timezone-aware and naive datetimes."""
        token = "valid_jwt_token"
        user_id = sample_user.id

        # Mock JWT decode
        mock_jwt_provider.decode_token.return_value = {
            "sub": str(user_id),
            "type": "access",
            "role": "researcher",
        }

        # Mock user repository
        mock_user_repository.get_by_id.return_value = sample_user

        # Create session with UTC-aware datetimes first
        base_time = datetime.now(UTC)
        expires_at_aware = base_time + timedelta(minutes=15)
        refresh_expires_at = base_time + timedelta(days=7)
        session = UserSession(
            user_id=user_id,
            session_token=token,
            refresh_token="refresh_token",
            expires_at=expires_at_aware,
            refresh_expires_at=refresh_expires_at,
            status=SessionStatus.ACTIVE,
        )
        object.__setattr__(
            session,
            "last_activity",
            datetime.now(UTC) - timedelta(minutes=10),
        )
        # Simulate database load: replace refresh_expires_at with naive datetime
        object.__setattr__(
            session,
            "refresh_expires_at",
            refresh_expires_at.replace(tzinfo=None),
        )

        # Mock session repository
        mock_session_repository.get_by_access_token.return_value = session
        mock_session_repository.update = AsyncMock()

        # Validate token - should handle mixed timezones gracefully
        result = await auth_service.validate_token(token)

        assert result == sample_user
        assert session.is_active() is True
        mock_session_repository.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_token_debounces_session_activity_writes(
        self,
        auth_service,
        mock_user_repository,
        mock_session_repository,
        mock_jwt_provider,
        sample_user,
    ):
        """Skip DB writes when session activity is still within debounce window."""
        token = "valid_jwt_token"
        user_id = sample_user.id

        mock_jwt_provider.decode_token.return_value = {
            "sub": str(user_id),
            "type": "access",
            "role": "researcher",
        }
        mock_user_repository.get_by_id.return_value = sample_user

        session = UserSession(
            user_id=user_id,
            session_token=token,
            refresh_token="refresh_token",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
            refresh_expires_at=datetime.now(UTC) + timedelta(days=7),
            status=SessionStatus.ACTIVE,
        )
        object.__setattr__(
            session,
            "last_activity",
            datetime.now(UTC) - timedelta(seconds=10),
        )

        mock_session_repository.get_by_access_token.return_value = session
        mock_session_repository.update = AsyncMock()

        result = await auth_service.validate_token(token)

        assert result == sample_user
        mock_session_repository.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_token_invalid_token_type(
        self,
        auth_service,
        mock_jwt_provider,
        sample_user,
    ):
        """Test token validation fails with invalid token type."""
        token = "refresh_token"

        # Mock JWT decode returns refresh token
        mock_jwt_provider.decode_token.return_value = {
            "sub": str(sample_user.id),
            "type": "refresh",  # Wrong type
        }

        with pytest.raises(AuthenticationError, match="Invalid token type"):
            await auth_service.validate_token(token)

    @pytest.mark.asyncio
    async def test_validate_token_user_not_found(
        self,
        auth_service,
        mock_user_repository,
        mock_jwt_provider,
    ):
        """Test token validation fails when user not found."""
        token = "valid_token"
        user_id = uuid4()

        mock_jwt_provider.decode_token.return_value = {
            "sub": str(user_id),
            "type": "access",
        }

        mock_user_repository.get_by_id.return_value = None

        with pytest.raises(AuthenticationError, match="User not found"):
            await auth_service.validate_token(token)

    @pytest.mark.asyncio
    async def test_validate_token_inactive_user(
        self,
        auth_service,
        mock_user_repository,
        mock_jwt_provider,
    ):
        """Test token validation fails for inactive user."""
        token = "valid_token"
        inactive_user = User(
            id=uuid4(),
            email="inactive@example.com",
            username="inactive",
            full_name="Inactive User",
            hashed_password="hashed_password_for_testing",
            role=UserRole.RESEARCHER,
            status=UserStatus.INACTIVE,
            email_verified=True,
        )

        mock_jwt_provider.decode_token.return_value = {
            "sub": str(inactive_user.id),
            "type": "access",
        }

        mock_user_repository.get_by_id.return_value = inactive_user

        with pytest.raises(AuthenticationError, match="User account not active"):
            await auth_service.validate_token(token)
