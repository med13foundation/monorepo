"""Add dictionary provenance and review workflow columns.

Revision ID: 009_dictionary_provenance_review
Revises: 008_pg_scheduler_tables
Create Date: 2026-02-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "009_dictionary_provenance_review"
down_revision = "008_pg_scheduler_tables"
branch_labels = None
depends_on = None

_DICTIONARY_TABLES = (
    "variable_definitions",
    "variable_synonyms",
    "entity_resolution_policies",
    "relation_constraints",
    "transform_registry",
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name for column in _inspector().get_columns(table_name)
    )


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _has_table(table_name) and not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def _add_provenance_columns(table_name: str) -> None:
    _add_column_if_missing(
        table_name,
        sa.Column(
            "created_by",
            sa.String(length=128),
            nullable=False,
            server_default="seed",
        ),
    )
    _add_column_if_missing(
        table_name,
        sa.Column("source_ref", sa.String(length=1024), nullable=True),
    )
    _add_column_if_missing(
        table_name,
        sa.Column(
            "review_status",
            sa.String(length=32),
            nullable=False,
            server_default="ACTIVE",
        ),
    )
    _add_column_if_missing(
        table_name,
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
    )
    _add_column_if_missing(
        table_name,
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        table_name,
        sa.Column("revocation_reason", sa.Text(), nullable=True),
    )


def _backfill_existing_rows(table_name: str) -> None:
    if not _has_table(table_name):
        return

    dictionary_table = sa.table(
        table_name,
        sa.column("created_by", sa.String()),
        sa.column("review_status", sa.String()),
    )
    op.execute(
        sa.update(dictionary_table).values(
            created_by=sa.func.coalesce(dictionary_table.c.created_by, "seed"),
            review_status=sa.func.coalesce(
                dictionary_table.c.review_status,
                "ACTIVE",
            ),
        ),
    )


def upgrade() -> None:
    for table_name in _DICTIONARY_TABLES:
        _add_provenance_columns(table_name)

    for table_name in _DICTIONARY_TABLES:
        _backfill_existing_rows(table_name)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if _has_table(table_name) and _has_column(table_name, column_name):
        op.drop_column(table_name, column_name)


def downgrade() -> None:
    for table_name in _DICTIONARY_TABLES:
        _drop_column_if_exists(table_name, "revocation_reason")
        _drop_column_if_exists(table_name, "reviewed_at")
        _drop_column_if_exists(table_name, "reviewed_by")
        _drop_column_if_exists(table_name, "review_status")
        _drop_column_if_exists(table_name, "source_ref")
        _drop_column_if_exists(table_name, "created_by")
