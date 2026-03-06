from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.services.user_management_service import UserAlreadyExistsError
from src.infrastructure.dependency_injection.container import container
from src.routes.auth import auth_router

if TYPE_CHECKING:
    from src.application.dto.auth_requests import RegisterUserRequest
    from src.domain.entities.user import User


class _DuplicateUserServiceStub:
    async def register_user(self, request: RegisterUserRequest) -> User:
        del request
        message = "User with this username already exists"
        raise UserAlreadyExistsError(message)


def test_register_user_maps_duplicate_username_to_conflict() -> None:
    app = FastAPI()
    app.include_router(auth_router)
    service = _DuplicateUserServiceStub()
    app.dependency_overrides[container.get_user_management_service] = lambda: service

    client = TestClient(app)

    response = client.post(
        "/auth/register",
        json={
            "email": "newuser@example.com",
            "username": "existing_user",
            "full_name": "New User",
            "password": "SecurePassword123!",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "User with this username already exists"
