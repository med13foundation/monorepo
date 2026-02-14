import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, inspect, pool, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from alembic import context

# Import our models for autogenerate support
from src.database.url_resolver import resolve_sync_database_url
from src.models.database import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Allow DATABASE_URL/ALEMBIC_DATABASE_URL to override default
database_url = os.getenv("ALEMBIC_DATABASE_URL") or resolve_sync_database_url()
config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata
_LEGACY_REVISION_ALIAS_MAP = {
    "004_relation_evidence_and_extraction_queue_contract": (
        "004_rel_evidence_extract_queue"
    ),
}


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
        inspector = inspect(connection)
        if "alembic_version" in inspector.get_table_names():
            for old_revision, canonical_revision in _LEGACY_REVISION_ALIAS_MAP.items():
                current_revisions = {
                    str(row[0])
                    for row in connection.execute(
                        text("SELECT version_num FROM alembic_version"),
                    ).all()
                }
                if old_revision not in current_revisions:
                    continue
                if canonical_revision in current_revisions:
                    connection.execute(
                        text(
                            "DELETE FROM alembic_version "
                            "WHERE version_num = :version_num",
                        ),
                        {"version_num": old_revision},
                    )
                else:
                    connection.execute(
                        text(
                            "UPDATE alembic_version "
                            "SET version_num = :canonical_revision "
                            "WHERE version_num = :old_revision",
                        ),
                        {
                            "canonical_revision": canonical_revision,
                            "old_revision": old_revision,
                        },
                    )
        if connection.in_transaction():
            connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
