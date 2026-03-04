"""Add evidence sentence provenance fields to relation evidence.

Revision ID: 028_evidence_sentence_prov
Revises: 027_relation_evidence_sentence
Create Date: 2026-03-04
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "028_evidence_sentence_prov"
down_revision = "027_relation_evidence_sentence"
branch_labels = None
depends_on = None

_TABLE_NAME = "relation_evidence"
_COLUMN_DEFINITIONS: tuple[tuple[str, sa.Column[object]], ...] = (
    (
        "evidence_sentence_source",
        sa.Column("evidence_sentence_source", sa.Text(), nullable=True),
    ),
    (
        "evidence_sentence_confidence",
        sa.Column("evidence_sentence_confidence", sa.Text(), nullable=True),
    ),
    (
        "evidence_sentence_rationale",
        sa.Column("evidence_sentence_rationale", sa.Text(), nullable=True),
    ),
)


def upgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return
    with op.batch_alter_table(
        _TABLE_NAME,
        reflect_kwargs={"resolve_fks": False},
    ) as batch_op:
        for column_name, column in _COLUMN_DEFINITIONS:
            if _has_column(_TABLE_NAME, column_name):
                continue
            batch_op.add_column(column)


def downgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return
    with op.batch_alter_table(
        _TABLE_NAME,
        reflect_kwargs={"resolve_fks": False},
    ) as batch_op:
        for column_name, _ in reversed(_COLUMN_DEFINITIONS):
            if not _has_column(_TABLE_NAME, column_name):
                continue
            batch_op.drop_column(column_name)


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
