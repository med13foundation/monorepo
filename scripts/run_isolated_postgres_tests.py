"""Run pytest against an isolated ephemeral Postgres database.

When local Postgres mode is active (via `.postgres-active`), running tests
directly against `MED13_POSTGRES_DB` risks mutating developer data and can leave
the database in a drifted state if a test is destructive.

This helper creates a fresh temporary database, runs Alembic migrations, runs
pytest, and then drops the database.

Usage (typically via Makefile):
    python scripts/run_isolated_postgres_tests.py -m "not performance"
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_ALEMBIC_CONFIG = REPO_ROOT / "services" / "graph_api" / "alembic.ini"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.database.url_resolver import to_async_database_url  # noqa: E402


@dataclass(frozen=True)
class PostgresUrls:
    """Connection strings used for test orchestration."""

    sync_url: str
    async_url: str
    alembic_url: str


def _quote_ident(identifier: str) -> str:
    # Double-quote escaping per SQL spec.
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def _require_postgres_sync_url(url: str) -> None:
    if not url.startswith("postgresql"):
        msg = (
            "DATABASE_URL must be PostgreSQL; this script only supports Postgres mode."
        )
        raise SystemExit(msg)


def _build_urls_for_database(base_sync_url: str, database_name: str) -> PostgresUrls:
    parsed = make_url(base_sync_url)
    # Use render_as_string to avoid SQLAlchemy's default password masking in `str(url)`.
    sync_url = parsed.set(database=database_name).render_as_string(hide_password=False)
    async_url = to_async_database_url(sync_url)
    return PostgresUrls(
        sync_url=sync_url,
        async_url=async_url,
        alembic_url=sync_url,
    )


def _create_database(admin_sync_url: str, database_name: str) -> None:
    engine = create_engine(admin_sync_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE {_quote_ident(database_name)}"))
    finally:
        engine.dispose()


def _drop_database(admin_sync_url: str, database_name: str) -> None:
    engine = create_engine(admin_sync_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            # Ensure no pooled connections prevent the DROP.
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :db_name AND pid <> pg_backend_pid()",
                ),
                {"db_name": database_name},
            )
            conn.execute(text(f"DROP DATABASE IF EXISTS {_quote_ident(database_name)}"))
    finally:
        engine.dispose()


def _resolve_alembic_binary() -> str:
    candidate_bins = (
        Path(sys.executable).resolve().parent / "alembic",
        REPO_ROOT / ".venv" / "bin" / "alembic",
        REPO_ROOT / "venv" / "bin" / "alembic",
    )
    for bin_path in candidate_bins:
        if bin_path.exists():
            return str(bin_path)
    return "alembic"


def _run_alembic_migrations(env: dict[str, str]) -> None:
    subprocess.run(  # noqa: S603
        [
            _resolve_alembic_binary(),
            "-c",
            str(GRAPH_ALEMBIC_CONFIG),
            "upgrade",
            "heads",
        ],
        check=True,
        env=env,
    )


def _run_pytest(pytest_args: list[str], env: dict[str, str]) -> int:
    runner_module = os.environ.get("MED13_TEST_RUNNER", "pytest")
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", runner_module, *pytest_args],
        check=False,
        env=env,
    )
    return result.returncode


def _generate_database_name() -> str:
    # PostgreSQL identifier length limit is 63 bytes. Keep it short and stable.
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    suffix = uuid4().hex[:10]
    return f"med13_test_{stamp}_{suffix}"[:63]


def main(argv: list[str]) -> int:
    base_sync_url = os.environ.get("DATABASE_URL", "")
    if not base_sync_url:
        msg = "DATABASE_URL is required"
        raise SystemExit(msg)
    _require_postgres_sync_url(base_sync_url)

    # Connect to the base database to create/drop the ephemeral one. This avoids
    # assuming the maintenance DB name ('postgres') exists in all environments.
    admin_sync_url = base_sync_url

    test_db_name = _generate_database_name()
    urls = _build_urls_for_database(base_sync_url, test_db_name)

    # Propagate all env vars, overriding only DB URLs for the test subprocesses.
    child_env = dict(os.environ)
    child_env["DATABASE_URL"] = urls.sync_url
    child_env["ASYNC_DATABASE_URL"] = urls.async_url
    child_env["ALEMBIC_DATABASE_URL"] = urls.alembic_url

    print(f">> Creating ephemeral test database: {test_db_name}")
    _create_database(admin_sync_url, test_db_name)

    try:
        print(">> Applying Alembic migrations...")
        _run_alembic_migrations(child_env)

        print(">> Running pytest...")
        return _run_pytest(argv, child_env)
    finally:
        print(f">> Dropping ephemeral test database: {test_db_name}")
        _drop_database(admin_sync_url, test_db_name)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
