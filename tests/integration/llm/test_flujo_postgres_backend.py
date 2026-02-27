"""Integration tests for Artana PostgreSQL state configuration."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlsplit

import pytest
from sqlalchemy import create_engine, text

from src.database.url_resolver import resolve_sync_database_url
from src.infrastructure.llm.config.artana_config import resolve_artana_state_uri


def _get_query_param(url: str, key: str) -> str | None:
    for name, value in parse_qsl(urlsplit(url).query, keep_blank_values=True):
        if name == key:
            return value
    return None


@pytest.fixture
def postgres_engine():
    """Create engine connected to test database and ensure artana schema exists."""
    url = resolve_sync_database_url()
    if not url.startswith("postgresql"):
        pytest.skip("PostgreSQL required for this test")
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS artana"))
        conn.commit()
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.mark.integration
class TestArtanaPostgresIntegration:
    """Integration tests for Artana state configuration with PostgreSQL."""

    def test_artana_schema_exists(self, postgres_engine) -> None:
        """Verify artana schema was created."""
        with postgres_engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name = 'artana'",
                ),
            )
            assert result.fetchone() is not None

    def test_state_uri_targets_artana_schema(self, postgres_engine) -> None:
        """Resolved state URI should include the artana search_path."""
        del postgres_engine
        state_uri = resolve_artana_state_uri()
        options = _get_query_param(state_uri, "options")
        assert options is not None
        assert "search_path=artana,public" in options
