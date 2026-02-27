"""Add extraction_queue.created_at for ORM/base audit-field parity.

Revision ID: 018_extraction_queue_created_at
Revises: 017_phi_identifier_encryption
Create Date: 2026-02-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "018_extraction_queue_created_at"
down_revision = "017_phi_identifier_encryption"
branch_labels = None
depends_on = None

_TABLE_NAME = "extraction_queue"
_COLUMN_NAME = "created_at"
_QUEUED_AT_COLUMN = "queued_at"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return column_name in {
        column["name"] for column in _inspector().get_columns(table_name)
    }


def upgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return
    if _has_column(_TABLE_NAME, _COLUMN_NAME):
        return

    with op.batch_alter_table(_TABLE_NAME) as batch_op:
        batch_op.add_column(
            sa.Column(
                _COLUMN_NAME,
                sa.TIMESTAMP(timezone=True),
                nullable=True,
                server_default=sa.func.now(),
            ),
        )

    if _has_column(_TABLE_NAME, _QUEUED_AT_COLUMN):
        op.execute(
            sa.text(
                """
                UPDATE extraction_queue
                SET created_at = queued_at
                WHERE created_at IS NULL
                """,
            ),
        )

    op.execute(
        sa.text(
            """
            UPDATE extraction_queue
            SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL
            """,
        ),
    )

    with op.batch_alter_table(_TABLE_NAME) as batch_op:
        batch_op.alter_column(
            _COLUMN_NAME,
            existing_type=sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        )


def downgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return
    if not _has_column(_TABLE_NAME, _COLUMN_NAME):
        return
    with op.batch_alter_table(_TABLE_NAME) as batch_op:
        batch_op.drop_column(_COLUMN_NAME)
