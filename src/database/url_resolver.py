"""
Database URL resolution helpers.

These utilities centralize how the application derives synchronous and
asynchronous SQLAlchemy URLs from environment variables. They let us
run Dockerized Postgres in local development and Postgres in deployed
environments without touching call sites throughout the codebase.
"""

from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_ALLOWED_INSECURE_ENV = os.getenv("MED13_ALLOW_INSECURE_DEFAULTS") == "1"
_ENVIRONMENT = os.getenv("MED13_ENV", "development").lower()
_POSTGRES_PREFIXES = (
    "postgresql://",
    "postgresql+psycopg2://",
    "postgresql+psycopg://",
    "postgresql+asyncpg://",
)


def _validate_url_security(url: str) -> None:
    """Ensure we do not boot with insecure defaults in production-like environments."""
    if _ALLOWED_INSECURE_ENV:
        return
    if _ENVIRONMENT not in {"production", "staging"}:
        return

    insecure_markers = ("med13_dev_password",)
    if any(marker in url for marker in insecure_markers):
        msg = (
            "Insecure default database credentials detected in a production/staging "
            "environment. Provide secure DATABASE_URL/ASYNC_DATABASE_URL values."
        )
        raise RuntimeError(msg)


def _enforce_runtime_postgres(url: str) -> None:
    """Reject non-Postgres runtime URLs in non-test contexts."""
    if os.getenv("TESTING", "").strip().lower() == "true":
        return
    if not url.startswith(_POSTGRES_PREFIXES):
        msg = (
            "Non-Postgres runtime configuration is disabled. Use Dockerized Postgres via "
            ".env.postgres and set DATABASE_URL/ASYNC_DATABASE_URL accordingly."
        )
        raise RuntimeError(msg)


def _enforce_tls_requirements(url: str) -> str:
    """
    Ensure TLS is required for Postgres connections in production-like environments.

    Adds sslmode=require when missing, unless insecure defaults are explicitly allowed.
    """
    if _ALLOWED_INSECURE_ENV or _ENVIRONMENT not in {"production", "staging"}:
        return url
    if not url.startswith(_POSTGRES_PREFIXES):
        return url

    split = urlsplit(url)
    query_items = parse_qsl(split.query, keep_blank_values=True)
    lowercase_keys = {key.lower() for key, _ in query_items}
    if "sslmode" not in lowercase_keys:
        query_items.append(("sslmode", "require"))
    rebuilt_query = urlencode(query_items, doseq=True)
    return urlunsplit(
        (
            split.scheme,
            split.netloc,
            split.path,
            rebuilt_query,
            split.fragment,
        ),
    )


_DEFAULT_POSTGRES_HOST = os.getenv("MED13_POSTGRES_HOST", "localhost")
_DEFAULT_POSTGRES_PORT = os.getenv("MED13_POSTGRES_PORT", "5432")
_DEFAULT_POSTGRES_DB = os.getenv("MED13_POSTGRES_DB", "med13_dev")
_DEFAULT_POSTGRES_USER = os.getenv("MED13_POSTGRES_USER", "med13_dev")
_DEFAULT_POSTGRES_PASSWORD = os.getenv("MED13_POSTGRES_PASSWORD", "med13_dev_password")
DEFAULT_POSTGRES_SYNC_URL = (
    "postgresql+psycopg2://"
    f"{_DEFAULT_POSTGRES_USER}:{_DEFAULT_POSTGRES_PASSWORD}"
    f"@{_DEFAULT_POSTGRES_HOST}:{_DEFAULT_POSTGRES_PORT}/{_DEFAULT_POSTGRES_DB}"
)


def resolve_sync_database_url() -> str:
    """Return the sync SQLAlchemy URL, defaulting to local Postgres."""
    url = os.getenv("DATABASE_URL", DEFAULT_POSTGRES_SYNC_URL)
    _validate_url_security(url)
    _enforce_runtime_postgres(url)
    return _enforce_tls_requirements(url)


def to_async_database_url(sync_url: str) -> str:
    """
    Convert a synchronous SQLAlchemy URL into its async counterpart.

    Examples:
        postgresql:// -> postgresql+asyncpg://
        postgresql+psycopg2:// -> postgresql+asyncpg://
    """
    passthrough_prefixes = ("postgresql+asyncpg",)
    if sync_url.startswith(passthrough_prefixes):
        return sync_url

    replacements = (
        ("postgresql+psycopg2://", "postgresql+asyncpg://"),
        ("postgresql+psycopg://", "postgresql+asyncpg://"),
        ("postgresql://", "postgresql+asyncpg://"),
    )

    for prefix, replacement in replacements:
        if sync_url.startswith(prefix):
            return sync_url.replace(prefix, replacement, 1)

    return sync_url


def resolve_async_database_url() -> str:
    """Return the async SQLAlchemy URL, deriving from sync URL when needed."""
    async_override = os.getenv("ASYNC_DATABASE_URL")
    if async_override:
        _validate_url_security(async_override)
        _enforce_runtime_postgres(async_override)
        return _enforce_tls_requirements(async_override)
    sync_url = resolve_sync_database_url()
    return to_async_database_url(sync_url)
