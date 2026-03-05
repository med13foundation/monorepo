"""Enforce unique active variable synonyms across variables.

Revision ID: 023_active_synonym_unique
Revises: 022_run_ids_as_text
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "023_active_synonym_unique"
down_revision = "022_run_ids_as_text"
branch_labels = None
depends_on = None

_TABLE_NAME = "variable_synonyms"
_INDEX_NAME = "uq_variable_synonyms_active_synonym"


def upgrade() -> None:
    if not _has_table(_TABLE_NAME) or _has_index(_TABLE_NAME, _INDEX_NAME):
        return

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM variable_synonyms
                    WHERE is_active IS TRUE
                    GROUP BY lower(synonym)
                    HAVING count(DISTINCT variable_id) > 1
                ) THEN
                    RAISE EXCEPTION
                        'Cannot enforce active synonym uniqueness: duplicate active synonyms exist across variables';
                END IF;
            END $$;
            """,
        )
        op.create_index(
            _INDEX_NAME,
            _TABLE_NAME,
            [sa.text("lower(synonym)")],
            unique=True,
            postgresql_where=sa.text("is_active"),
        )
        return

    op.create_index(
        _INDEX_NAME,
        _TABLE_NAME,
        [sa.text("lower(synonym)")],
        unique=True,
    )


def downgrade() -> None:
    if not _has_table(_TABLE_NAME) or not _has_index(_TABLE_NAME, _INDEX_NAME):
        return
    op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        index.get("name") == index_name for index in inspector.get_indexes(table_name)
    )
