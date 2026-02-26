"""Tests for Artana configuration helpers."""

from __future__ import annotations

import os
from unittest.mock import patch
from urllib.parse import parse_qsl, urlsplit

import pytest

from src.infrastructure.llm.config.artana_config import (
    _add_artana_schema,
    _normalize_postgres_dsn,
    resolve_artana_state_uri,
)


def _get_query_param(url: str, key: str) -> str | None:
    items = parse_qsl(urlsplit(url).query, keep_blank_values=True)
    for name, value in items:
        if name == key:
            return value
    return None


class TestResolveArtanaUri:
    """Tests for resolve_artana_state_uri."""

    def test_explicit_uri_takes_precedence(self) -> None:
        """ARTANA_STATE_URI should override derived URL."""
        with patch.dict(os.environ, {"ARTANA_STATE_URI": "postgresql://custom"}):
            assert resolve_artana_state_uri() == "postgresql://custom"

    def test_sqlite_database_url_is_rejected(self) -> None:
        """SQLite DATABASE_URL should be rejected by Postgres-only config."""
        with (
            patch.dict(
                os.environ,
                {"DATABASE_URL": "sqlite:///test.db", "TESTING": "true"},
                clear=True,
            ),
            pytest.raises(RuntimeError, match="requires a PostgreSQL"),
        ):
            resolve_artana_state_uri()

    def test_postgres_adds_schema(self) -> None:
        """PostgreSQL should have artana schema added."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://user:pass@host:5432/db"},
            clear=True,
        ):
            result = resolve_artana_state_uri()
            options = _get_query_param(result, "options")
            assert options is not None
            assert "search_path=artana,public" in options


class TestAddArtanaSchema:
    """Tests for _add_artana_schema helper."""

    def test_adds_options_to_clean_url(self) -> None:
        """Schema option should be added to URL without options."""
        url = "postgresql://user:pass@host:5432/db"
        result = _add_artana_schema(url)
        options = _get_query_param(result, "options")
        assert options is not None
        assert "search_path=artana,public" in options

    def test_preserves_existing_query_params(self) -> None:
        """Existing query params should be preserved."""
        url = "postgresql://user:pass@host:5432/db?sslmode=require"
        result = _add_artana_schema(url)
        assert _get_query_param(result, "sslmode") == "require"
        options = _get_query_param(result, "options")
        assert options is not None
        assert "search_path=artana,public" in options

    def test_normalizes_sqlalchemy_driver(self) -> None:
        """SQLAlchemy driver schemes should be normalized for asyncpg."""
        url = "postgresql+psycopg2://user:pass@host:5432/db"
        assert _normalize_postgres_dsn(url).startswith("postgresql://")

    def test_normalizes_asyncpg_driver(self) -> None:
        """Asyncpg driver schemes should be normalized for asyncpg."""
        url = "postgresql+asyncpg://user:pass@host:5432/db"
        assert _normalize_postgres_dsn(url).startswith("postgresql://")
