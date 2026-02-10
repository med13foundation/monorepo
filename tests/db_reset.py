"""Test database reset helpers.

These utilities keep tests working in both SQLite (fast local runs) and
PostgreSQL (CI / migration parity) without relying on `Base.metadata.drop_all()`
against a migrated Postgres schema that may include tables not represented by
SQLAlchemy models.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import inspect, text

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.engine import Engine
    from sqlalchemy.sql.schema import MetaData


def _escape_identifier(identifier: str) -> str:
    # Double-quote escaping per SQL spec.
    return identifier.replace('"', '""')


def reset_database(engine: Engine, metadata: MetaData) -> None:
    """Reset the database contents for a test run.

    - SQLite: drop + create the SQLAlchemy metadata schema.
    - Postgres: truncate all public-schema tables (restart identity, cascade),
      excluding `alembic_version`.
    """

    with engine.begin() as connection:
        dialect_name = connection.dialect.name
        if dialect_name == "postgresql":
            inspector = inspect(connection)
            tables = [
                table
                for table in inspector.get_table_names(schema="public")
                if table != "alembic_version"
            ]
            if not tables:
                return

            qualified = ", ".join(
                f'public."{_escape_identifier(table)}"' for table in tables
            )
            connection.execute(
                text(f"TRUNCATE TABLE {qualified} RESTART IDENTITY CASCADE"),
            )
            return

    # SQLite and other local DBs: recreate from metadata.
    metadata.drop_all(bind=engine)
    metadata.create_all(bind=engine)


__all__ = ["reset_database"]
