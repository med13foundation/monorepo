import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from src.database.graph_schema import (
    graph_postgres_search_path,
    graph_schema_name,
)

# Import our models for autogenerate support
from src.database.url_resolver import resolve_sync_database_url
from src.models.database import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Allow DATABASE_URL/ALEMBIC_DATABASE_URL to override default
database_url = os.getenv("ALEMBIC_DATABASE_URL") or resolve_sync_database_url()
config.set_main_option("sqlalchemy.url", database_url)
graph_db_schema = graph_schema_name(
    os.getenv("ALEMBIC_GRAPH_DB_SCHEMA") or os.getenv("GRAPH_DB_SCHEMA"),
)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type: JSONB, _compiler: object, **_kw: object) -> str:
    """Allow PostgreSQL JSONB columns to compile as JSON on SQLite."""
    return "JSON"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=graph_db_schema is not None,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if connection.dialect.name == "postgresql" and graph_db_schema is not None:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{graph_db_schema}"'))
            connection.execute(
                text(
                    f"SET search_path TO {graph_postgres_search_path(graph_db_schema)}",
                ),
            )

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=graph_db_schema is not None,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
