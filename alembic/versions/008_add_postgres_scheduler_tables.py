"""Add durable scheduler and source lock tables for ingestion runtime.

Revision ID: 008_pg_scheduler_tables
Revises: 007_add_source_documents_mvp
Create Date: 2026-02-14
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "008_pg_scheduler_tables"
down_revision = "007_add_source_documents_mvp"
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
    if not _has_table("ingestion_scheduler_jobs"):
        op.create_table(
            "ingestion_scheduler_jobs",
            sa.Column("job_id", sa.String(length=64), primary_key=True),
            sa.Column(
                "source_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("user_data_sources.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column("frequency", sa.String(length=32), nullable=False),
            sa.Column("cron_expression", sa.String(length=128), nullable=True),
            sa.Column(
                "timezone",
                sa.String(length=64),
                nullable=False,
                server_default="UTC",
            ),
            sa.Column("start_time", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("next_run_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("last_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column(
                "is_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
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

    if not _has_table("ingestion_source_locks"):
        op.create_table(
            "ingestion_source_locks",
            sa.Column(
                "source_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("user_data_sources.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("lock_token", sa.String(length=64), nullable=False),
            sa.Column("lease_expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("last_heartbeat_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("acquired_by", sa.String(length=128), nullable=True),
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

    if not _has_index(
        "ingestion_scheduler_jobs",
        "idx_ingestion_scheduler_jobs_source_id",
    ):
        op.create_index(
            "idx_ingestion_scheduler_jobs_source_id",
            "ingestion_scheduler_jobs",
            ["source_id"],
        )
    if not _has_index(
        "ingestion_scheduler_jobs",
        "idx_ingestion_scheduler_jobs_next_run_at",
    ):
        op.create_index(
            "idx_ingestion_scheduler_jobs_next_run_at",
            "ingestion_scheduler_jobs",
            ["next_run_at"],
        )
    if not _has_index(
        "ingestion_scheduler_jobs",
        "idx_ingestion_scheduler_jobs_is_enabled",
    ):
        op.create_index(
            "idx_ingestion_scheduler_jobs_is_enabled",
            "ingestion_scheduler_jobs",
            ["is_enabled"],
        )
    if not _has_index(
        "ingestion_source_locks",
        "idx_ingestion_source_locks_source_id",
    ):
        op.create_index(
            "idx_ingestion_source_locks_source_id",
            "ingestion_source_locks",
            ["source_id"],
        )
    if not _has_index(
        "ingestion_source_locks",
        "idx_ingestion_source_locks_lease_expires_at",
    ):
        op.create_index(
            "idx_ingestion_source_locks_lease_expires_at",
            "ingestion_source_locks",
            ["lease_expires_at"],
        )


def downgrade() -> None:
    if _has_table("ingestion_source_locks"):
        op.drop_table("ingestion_source_locks")
    if _has_table("ingestion_scheduler_jobs"):
        op.drop_table("ingestion_scheduler_jobs")
