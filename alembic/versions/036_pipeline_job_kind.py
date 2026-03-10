"""Add job-kind discriminator to ingestion jobs.

Revision ID: 036_pipeline_job_kind
Revises: 035_session_token_uniqueness
Create Date: 2026-03-06
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "036_pipeline_job_kind"
down_revision = "035_session_token_uniqueness"
branch_labels = None
depends_on = None

_TABLE_NAME = "ingestion_jobs"
_COLUMN_NAME = "job_kind"
_ENUM_NAME = "ingestionjobkindenum"


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

    job_kind_enum = sa.Enum(
        "ingestion",
        "pipeline_orchestration",
        name=_ENUM_NAME,
    )
    bind = op.get_bind()
    job_kind_enum.create(bind, checkfirst=True)

    with op.batch_alter_table(
        _TABLE_NAME,
        reflect_kwargs={"resolve_fks": False},
    ) as batch_op:
        if not _has_column(_TABLE_NAME, _COLUMN_NAME):
            batch_op.add_column(
                sa.Column(
                    _COLUMN_NAME,
                    job_kind_enum,
                    nullable=False,
                    server_default="ingestion",
                ),
            )


def downgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return

    with op.batch_alter_table(
        _TABLE_NAME,
        reflect_kwargs={"resolve_fks": False},
    ) as batch_op:
        if _has_column(_TABLE_NAME, _COLUMN_NAME):
            batch_op.drop_column(_COLUMN_NAME)

    bind = op.get_bind()
    sa.Enum(name=_ENUM_NAME).drop(bind, checkfirst=True)
