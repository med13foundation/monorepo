"""Add ingestion job runtime tracking fields.

Revision ID: 020_ingestion_job_runtime_fields
Revises: 019_create_reviews_table
Create Date: 2026-02-24
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "020_ingestion_job_runtime_fields"
down_revision = "019_create_reviews_table"
branch_labels = None
depends_on = None

_TABLE_NAME = "ingestion_jobs"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        column.get("name") == column_name
        for column in _inspector().get_columns(table_name)
    )


def upgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return

    with op.batch_alter_table(_TABLE_NAME) as batch_op:
        if not _has_column(_TABLE_NAME, "dictionary_version_used"):
            batch_op.add_column(
                sa.Column(
                    "dictionary_version_used",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
            )
        if not _has_column(_TABLE_NAME, "replay_policy"):
            batch_op.add_column(
                sa.Column(
                    "replay_policy",
                    sa.String(length=32),
                    nullable=False,
                    server_default="strict",
                ),
            )


def downgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return

    with op.batch_alter_table(_TABLE_NAME) as batch_op:
        if _has_column(_TABLE_NAME, "replay_policy"):
            batch_op.drop_column("replay_policy")
        if _has_column(_TABLE_NAME, "dictionary_version_used"):
            batch_op.drop_column("dictionary_version_used")
