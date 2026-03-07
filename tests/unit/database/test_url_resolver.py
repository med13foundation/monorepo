from __future__ import annotations

import os
from unittest.mock import patch
from urllib.parse import parse_qsl, urlsplit

from src.database import url_resolver


def _query_params(url: str) -> dict[str, str]:
    return dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))


class TestAsyncDatabaseUrlResolution:
    def test_to_async_database_url_rewrites_sslmode_for_asyncpg(self) -> None:
        sync_url = (
            "postgresql+psycopg2://user:pass@db.example.com:5432/app?sslmode=require"
        )

        result = url_resolver.to_async_database_url(sync_url)

        assert result.startswith("postgresql+asyncpg://")
        assert _query_params(result)["ssl"] == "require"
        assert "sslmode" not in _query_params(result)

    def test_resolve_async_database_url_preserves_cloudsql_socket_host(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "DATABASE_URL": (
                        "postgresql+psycopg2://user:pass@/med13_staging"
                        "?host=/cloudsql/artana-bio:us-central1:med13-pg-staging"
                    ),
                },
                clear=True,
            ),
            patch.object(url_resolver, "_ENVIRONMENT", "staging"),
        ):
            result = url_resolver.resolve_async_database_url()

        query_params = _query_params(result)
        assert result.startswith("postgresql+asyncpg://")
        assert (
            query_params["host"] == "/cloudsql/artana-bio:us-central1:med13-pg-staging"
        )
        assert query_params["ssl"] == "require"
        assert "sslmode" not in query_params

    def test_explicit_async_override_drops_sslmode_when_ssl_already_present(
        self,
    ) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "ASYNC_DATABASE_URL": (
                        "postgresql+asyncpg://user:pass@db.example.com:5432/app"
                        "?ssl=require&sslmode=verify-full"
                    ),
                },
                clear=True,
            ),
            patch.object(url_resolver, "_ENVIRONMENT", "staging"),
        ):
            result = url_resolver.resolve_async_database_url()

        query_params = _query_params(result)
        assert query_params["ssl"] == "require"
        assert "sslmode" not in query_params
