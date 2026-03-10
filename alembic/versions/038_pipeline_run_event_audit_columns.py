"""Add audit timestamp columns to pipeline_run_events.

Revision ID: 038_pipeline_event_audit
Revises: 037_pipeline_run_events
Create Date: 2026-03-09
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "038_pipeline_event_audit"
down_revision = "037_pipeline_run_events"
branch_labels = None
depends_on = None

_TABLE_NAME = "pipeline_run_events"


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
    if not _has_column(_TABLE_NAME, "created_at"):
        op.add_column(
            _TABLE_NAME,
            sa.Column(
                "created_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
    if not _has_column(_TABLE_NAME, "updated_at"):
        op.add_column(
            _TABLE_NAME,
            sa.Column(
                "updated_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )


def downgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return
    with op.batch_alter_table(
        _TABLE_NAME,
        reflect_kwargs={"resolve_fks": False},
    ) as batch_op:
        if _has_column(_TABLE_NAME, "updated_at"):
            batch_op.drop_column("updated_at")
        if _has_column(_TABLE_NAME, "created_at"):
            batch_op.drop_column("created_at")
