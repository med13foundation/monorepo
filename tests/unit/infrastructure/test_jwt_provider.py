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


def test_create_access_token_preserves_extra_claims() -> None:
    provider = JWTProvider(
        secret_key="test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz",
    )

    token = provider.create_access_token(
        uuid4(),
        "viewer",
        extra_claims={"graph_admin": True},
    )
    payload = provider.decode_token(token)

    assert payload["graph_admin"] is True
