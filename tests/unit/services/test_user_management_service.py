"""
Unit tests for UserManagementService.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.services.user_management_service import (
    UserManagementService,
    UserNotFoundError,
)
from src.domain.entities.user import User, UserRole, UserStatus


@pytest.fixture
def mock_user_repository():
    return AsyncMock()


@pytest.fixture
def mock_password_hasher():
    return MagicMock()


@pytest.fixture
def user_management_service(mock_user_repository, mock_password_hasher):
    return UserManagementService(
        user_repository=mock_user_repository,
        password_hasher=mock_password_hasher,
    )


@pytest.mark.asyncio
async def test_activate_user_account_marks_user_active_and_verified(
    user_management_service: UserManagementService,
    mock_user_repository: AsyncMock,
):
    user = User(
        id=uuid4(),
        email="pending@example.com",
        username="pending-user",
        full_name="Pending User",
        hashed_password="hashed",
        role=UserRole.RESEARCHER,
        status=UserStatus.PENDING_VERIFICATION,
        email_verification_token="verification-token",
    )
    mock_user_repository.get_by_id.return_value = user
    mock_user_repository.update.return_value = user

    updated_user = await user_management_service.activate_user_account(user.id)

    assert updated_user.status == UserStatus.ACTIVE
    assert updated_user.email_verified is True
    assert updated_user.email_verification_token is None
    assert updated_user.locked_until is None
    assert updated_user.login_attempts == 0
    mock_user_repository.update.assert_awaited_once_with(user)


@pytest.mark.asyncio
async def test_activate_user_account_raises_for_missing_user(
    user_management_service: UserManagementService,
    mock_user_repository: AsyncMock,
):
    missing_user_id = uuid4()
    mock_user_repository.get_by_id.return_value = None

    with pytest.raises(UserNotFoundError, match="User not found"):
        await user_management_service.activate_user_account(missing_user_id)

    mock_user_repository.update.assert_not_awaited()
