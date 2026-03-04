"""Add optional evidence_sentence column to relation evidence.

Revision ID: 027_relation_evidence_sentence
Revises: 026_concept_manager_foundation
Create Date: 2026-03-04
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "027_relation_evidence_sentence"
down_revision = "026_concept_manager_foundation"
branch_labels = None
depends_on = None

_TABLE_NAME = "relation_evidence"
_COLUMN_NAME = "evidence_sentence"


def upgrade() -> None:
    if not _has_table(_TABLE_NAME) or _has_column(_TABLE_NAME, _COLUMN_NAME):
        return

    with op.batch_alter_table(
        _TABLE_NAME,
        reflect_kwargs={"resolve_fks": False},
    ) as batch_op:
        batch_op.add_column(sa.Column(_COLUMN_NAME, sa.Text(), nullable=True))


def downgrade() -> None:
    if not _has_table(_TABLE_NAME) or not _has_column(_TABLE_NAME, _COLUMN_NAME):
        return

    with op.batch_alter_table(
        _TABLE_NAME,
        reflect_kwargs={"resolve_fks": False},
    ) as batch_op:
        batch_op.drop_column(_COLUMN_NAME)


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )
