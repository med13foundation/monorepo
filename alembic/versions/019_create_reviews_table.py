"""Create reviews table for centralized curation queue.

Revision ID: 019_create_reviews_table
Revises: 018_extraction_queue_created_at
Create Date: 2026-02-16
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "019_create_reviews_table"
down_revision = "018_extraction_queue_created_at"
branch_labels = None
depends_on = None

_TABLE_NAME = "reviews"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        index.get("name") == index_name
        for index in _inspector().get_indexes(table_name)
    )


def upgrade() -> None:
    if not _has_table(_TABLE_NAME):
        op.create_table(
            _TABLE_NAME,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("entity_type", sa.String(length=50), nullable=False),
            sa.Column("entity_id", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column(
                "priority",
                sa.String(length=16),
                nullable=False,
                server_default="medium",
            ),
            sa.Column("quality_score", sa.Float(), nullable=True),
            sa.Column(
                "issues",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "research_space_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("research_spaces.id"),
                nullable=True,
            ),
            sa.Column(
                "last_updated",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
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
        )

    if not _has_index(_TABLE_NAME, "ix_reviews_entity_type"):
        op.create_index("ix_reviews_entity_type", _TABLE_NAME, ["entity_type"])
    if not _has_index(_TABLE_NAME, "ix_reviews_entity_id"):
        op.create_index("ix_reviews_entity_id", _TABLE_NAME, ["entity_id"])
    if not _has_index(_TABLE_NAME, "ix_reviews_status"):
        op.create_index("ix_reviews_status", _TABLE_NAME, ["status"])
    if not _has_index(_TABLE_NAME, "ix_reviews_research_space_id"):
        op.create_index(
            "ix_reviews_research_space_id",
            _TABLE_NAME,
            ["research_space_id"],
        )


def downgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return

    if _has_index(_TABLE_NAME, "ix_reviews_research_space_id"):
        op.drop_index("ix_reviews_research_space_id", table_name=_TABLE_NAME)
    if _has_index(_TABLE_NAME, "ix_reviews_status"):
        op.drop_index("ix_reviews_status", table_name=_TABLE_NAME)
    if _has_index(_TABLE_NAME, "ix_reviews_entity_id"):
        op.drop_index("ix_reviews_entity_id", table_name=_TABLE_NAME)
    if _has_index(_TABLE_NAME, "ix_reviews_entity_type"):
        op.drop_index("ix_reviews_entity_type", table_name=_TABLE_NAME)

    op.drop_table(_TABLE_NAME)
