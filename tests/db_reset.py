"""Test database reset helpers.

These utilities keep tests working in both SQLite (fast local runs) and
PostgreSQL (CI / migration parity) without relying on `Base.metadata.drop_all()`
against a migrated Postgres schema that may include tables not represented by
SQLAlchemy models.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from sqlalchemy import inspect, text

from src.database.graph_schema import graph_schema_name

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.engine import Engine
    from sqlalchemy.sql.schema import MetaData


def _escape_identifier(identifier: str) -> str:
    # Double-quote escaping per SQL spec.
    return identifier.replace('"', '""')


def _qualified_tables_for_schema(
    *,
    inspector,
    schema: str,
) -> list[str]:
    tables = [
        table
        for table in inspector.get_table_names(schema=schema)
        if not (schema == "public" and table == "alembic_version")
    ]
    escaped_schema = _escape_identifier(schema)
    return [f'"{escaped_schema}"."{_escape_identifier(table)}"' for table in tables]


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
            schemas = ["public"]
            graph_schema = graph_schema_name(os.getenv("GRAPH_DB_SCHEMA"))
            if graph_schema is not None:
                schemas.append(graph_schema)
            qualified_tables: list[str] = []
            for schema in schemas:
                qualified_tables.extend(
                    _qualified_tables_for_schema(
                        inspector=inspector,
                        schema=schema,
                    ),
                )
            if not qualified_tables:
                return
            connection.execute(
                text(
                    "TRUNCATE TABLE "
                    + ", ".join(qualified_tables)
                    + " RESTART IDENTITY CASCADE",
                ),
            )
            return

    # SQLite and other local DBs: recreate from metadata.
    metadata.drop_all(bind=engine)
    metadata.create_all(bind=engine)


__all__ = ["reset_database"]
