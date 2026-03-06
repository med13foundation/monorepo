"""
Unit tests for User domain entity.

Tests user entity behavior, validation, and business logic.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.domain.entities.user import User, UserRole, UserStatus


class TestUserEntity:
    def test_user_creation_valid_data(self):
        """Test successful user creation with valid data."""
        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hashed_password",
            role=UserRole.RESEARCHER,
        )

        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.full_name == "Test User"
        assert user.role == UserRole.RESEARCHER
        assert user.status == UserStatus.PENDING_VERIFICATION
        assert user.email_verified is False
        assert user.id is not None
        assert isinstance(user.created_at, datetime)
        assert isinstance(user.updated_at, datetime)

    @pytest.mark.parametrize(
        "invalid_email",
        [
            "",
            "invalid-email",
            "test@.com",
            "@example.com",
            "test..test@example.com",
            "test@example..com",
        ],
    )
    def test_user_creation_invalid_email(self, invalid_email):
        """Test user creation fails with invalid email."""
        with pytest.raises(ValueError):
            User(
                email=invalid_email,
                username="testuser",
                full_name="Test User",
                hashed_password="hash",
            )

    @pytest.mark.parametrize(
        "invalid_username",
        [
            "",  # empty
            "a",  # too short
            "a" * 51,  # too long
            "user name",  # spaces (should be allowed)
            "user@name",  # special chars
            "user.name",  # dots (should be allowed)
            "user-name",  # dashes (should be allowed)
            "user_name",  # underscores (should be allowed)
        ],
    )
    def test_username_validation(self, invalid_username):
        """Test username validation."""
        # Valid usernames should work
        if (
            len(invalid_username) >= 3
            and len(invalid_username) <= 50
            and invalid_username.replace(" ", "")
            .replace(".", "")
            .replace("-", "")
            .replace("_", "")
            .isalnum()
        ):
            user = User(
                email="test@example.com",
                username=invalid_username,
                full_name="Test User",
                hashed_password="hash",
            )
            assert user.username == invalid_username
        else:
            with pytest.raises(ValueError):
                User(
                    email="test@example.com",
                    username=invalid_username,
                    full_name="Test User",
                    hashed_password="hash",
                )

    def test_can_authenticate_active_user(self):
        """Test authentication capability for active user."""
        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hash",
            status=UserStatus.ACTIVE,
        )

        assert user.can_authenticate() is True

    def test_cannot_authenticate_inactive_user(self):
        """Test authentication fails for inactive user."""
        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hash",
            status=UserStatus.INACTIVE,
        )

        assert user.can_authenticate() is False

    def test_cannot_authenticate_locked_user(self):
        """Test authentication fails for locked user."""
        future_time = datetime.now(UTC) + timedelta(hours=1)
        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hash",
            status=UserStatus.ACTIVE,
            locked_until=future_time,
        )

        assert user.can_authenticate() is False
        assert user.is_locked() is True

    def test_login_attempt_recording_success(self):
        """Test successful login attempt recording."""
        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hash",
            login_attempts=2,
        )

        user.record_login_attempt(success=True)

        assert user.login_attempts == 0  # Reset on success
        assert user.last_login is not None
        assert user.locked_until is None  # Clear any lockout

    def test_login_attempt_recording_failure(self):
        """Test failed login attempt recording."""
        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hash",
            login_attempts=0,
        )

        user.record_login_attempt(success=False)

        assert user.login_attempts == 1
        assert user.last_login is None  # Don't update on failure

    def test_account_lockout_after_max_attempts(self):
        """Test account lockout after maximum failed attempts."""
        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hash",
            login_attempts=4,  # One away from lockout
        )

        user.record_login_attempt(success=False)

        assert user.login_attempts == 5
        assert user.locked_until is not None

    def test_manual_account_locking(self):
        """Test manual account locking."""
        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hash",
            status=UserStatus.ACTIVE,
        )

        user.lock_account(duration_minutes=60 * 24 * 7)  # 7 days

        assert user.status == UserStatus.SUSPENDED
        assert user.locked_until is not None

    def test_manual_account_unlocking(self):
        """Test manual account unlocking."""
        future_time = datetime.now(UTC) + timedelta(hours=1)
        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hash",
            status=UserStatus.ACTIVE,
            locked_until=future_time,
        )

        user.unlock_account()

        assert user.status == UserStatus.ACTIVE
        assert user.locked_until is None
        assert user.login_attempts == 0  # Reset attempts

    def test_email_verification_workflow(self):
        """Test email verification token workflow."""
        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hash",
        )

        # Generate verification token
        token = user.generate_email_verification_token()
        assert token is not None
        assert len(token) > 32  # Secure token length
        assert user.email_verification_token == token

        # Mark as verified
        user.mark_email_verified()
        assert user.email_verified is True
        assert user.email_verification_token is None

    def test_activate_account_bypasses_email_verification(self):
        """Test admin activation promotes a pending user to an active verified account."""
        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hash",
            status=UserStatus.PENDING_VERIFICATION,
            email_verification_token="pending-token",
            login_attempts=3,
            locked_until=datetime.now(UTC) + timedelta(hours=1),
        )
        original_updated_at = user.updated_at

        user.activate_account()

        assert user.status == UserStatus.ACTIVE
        assert user.email_verified is True
        assert user.email_verification_token is None
        assert user.locked_until is None
        assert user.login_attempts == 0
        assert user.updated_at > original_updated_at

    def test_password_reset_workflow(self):
        """Test password reset token workflow."""
        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hash",
        )

        # Generate reset token
        token = user.generate_password_reset_token(expires_minutes=30)
        assert token is not None
        assert user.password_reset_token == token
        assert user.password_reset_expires is not None

        # Check if reset is valid
        assert user.can_reset_password(token) is True

        # Clear reset token
        user.clear_password_reset_token()
        assert user.password_reset_token is None
        assert user.password_reset_expires is None

    def test_expired_password_reset_token(self):
        """Test expired password reset token handling."""
        past_time = datetime.now(UTC) - timedelta(hours=1)
        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hash",
            password_reset_token="expired_token",
            password_reset_expires=past_time,
        )

        assert user.can_reset_password("expired_token") is False

    def test_profile_update(self):
        """Test profile update functionality."""
        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Old Name",
            hashed_password="hash",
        )

        original_updated_at = user.updated_at

        user.update_profile(full_name="New Name")

        assert user.full_name == "New Name"
        assert user.updated_at > original_updated_at

    def test_admin_user_business_rules(self):
        """Test admin users may exist in non-active states but cannot authenticate."""
        admin_user = User(
            email="admin@example.com",
            username="admin",
            full_name="Admin User",
            hashed_password="hash",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        assert admin_user.role == UserRole.ADMIN
        assert admin_user.status == UserStatus.ACTIVE

        suspended_admin = User(
            email="suspended-admin@example.com",
            username="suspended-admin",
            full_name="Suspended Admin",
            hashed_password="hash",
            role=UserRole.ADMIN,
            status=UserStatus.SUSPENDED,
        )
        assert suspended_admin.role == UserRole.ADMIN
        assert suspended_admin.status == UserStatus.SUSPENDED
        assert suspended_admin.can_authenticate() is False

    def test_business_rules_validation(self):
        """Test cross-field business rules validation."""
        # Password reset token with expired time should be cleared
        past_time = datetime.now(UTC) - timedelta(hours=1)
        user = User(
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hash",
            password_reset_token="token",
            password_reset_expires=past_time,
        )

        # The model validator should clear expired tokens
        # This test verifies the validator runs and clears expired tokens
        assert user.password_reset_token is None  # Cleared by validator
        assert user.password_reset_expires is None  # Also cleared

        # Trigger validation by accessing model again
        user_dict = user.model_dump()
        user_copy = User(**user_dict)

        # Note: The validator logic might need adjustment
        # This tests that validation runs without errors
        assert isinstance(user_copy, User)

    def test_string_representations(self):
        """Test string representations for logging/debugging."""
        user = User(
            id=uuid4(),
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password="hash",
            role=UserRole.RESEARCHER,
            status=UserStatus.ACTIVE,
        )

        str_repr = str(user)
        assert "test@example.com" in str_repr
        assert "researcher" in str_repr
        assert "active" in str_repr

        repr_str = repr(user)
        assert "User(" in repr_str
        assert "test@example.com" in repr_str
