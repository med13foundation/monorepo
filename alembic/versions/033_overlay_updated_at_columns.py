"""Ensure claim overlay tables include updated_at audit columns.

Revision ID: 033_overlay_updated_at_columns
Revises: 032_claim_graph_overlay
Create Date: 2026-03-04
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "033_overlay_updated_at_columns"
down_revision = "032_claim_graph_overlay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _ensure_updated_at_column("claim_participants")
    _ensure_updated_at_column("claim_relations")


def downgrade() -> None:
    _drop_updated_at_column("claim_relations")
    _drop_updated_at_column("claim_participants")


def _ensure_updated_at_column(table_name: str) -> None:
    if not _has_table(table_name):
        return
    if _has_column(table_name, "updated_at"):
        return

    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )


def _drop_updated_at_column(table_name: str) -> None:
    if not _has_table(table_name):
        return
    if not _has_column(table_name, "updated_at"):
        return

    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_column("updated_at")


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)
