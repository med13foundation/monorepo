"""Add immutable dictionary changelog audit table.

Revision ID: 010_dictionary_changelog
Revises: 009_dictionary_provenance_review
Create Date: 2026-02-14
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "010_dictionary_changelog"
down_revision = "009_dictionary_provenance_review"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name for index in _inspector().get_indexes(table_name)
    )


def upgrade() -> None:
    if not _has_table("dictionary_changelog"):
        op.create_table(
            "dictionary_changelog",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("table_name", sa.String(length=64), nullable=False),
            sa.Column("record_id", sa.String(length=128), nullable=False),
            sa.Column("action", sa.String(length=32), nullable=False),
            sa.Column("before_snapshot", postgresql.JSONB(astext_type=sa.Text())),
            sa.Column("after_snapshot", postgresql.JSONB(astext_type=sa.Text())),
            sa.Column("changed_by", sa.String(length=128), nullable=True),
            sa.Column("source_ref", sa.String(length=1024), nullable=True),
            sa.Column(
                "created_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            comment="Immutable audit log for dictionary mutations",
        )

    if _has_table("dictionary_changelog") and not _has_index(
        "dictionary_changelog",
        "idx_dictionary_changelog_table_record",
    ):
        op.create_index(
            "idx_dictionary_changelog_table_record",
            "dictionary_changelog",
            ["table_name", "record_id"],
            unique=False,
        )


def downgrade() -> None:
    if _has_table("dictionary_changelog"):
        if _has_index("dictionary_changelog", "idx_dictionary_changelog_table_record"):
            op.drop_index(
                "idx_dictionary_changelog_table_record",
                table_name="dictionary_changelog",
            )
        op.drop_table("dictionary_changelog")
