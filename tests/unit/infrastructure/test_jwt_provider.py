from uuid import uuid4

from src.infrastructure.security.jwt_provider import JWTProvider


def test_create_access_token_is_unique_per_issue_time() -> None:
    provider = JWTProvider(
        secret_key="test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz",
    )

    user_id = uuid4()

    assert provider.create_access_token(
        user_id,
        "admin",
    ) != provider.create_access_token(
        user_id,
        "admin",
    )


def test_create_refresh_token_is_unique_per_issue_time() -> None:
    provider = JWTProvider(
        secret_key="test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz",
    )

    user_id = uuid4()

    assert provider.create_refresh_token(user_id) != provider.create_refresh_token(
        user_id,
    )
