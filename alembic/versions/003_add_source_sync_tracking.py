"""Add source sync tracking tables for incremental datasource ingestion.

Revision ID: 003_add_source_sync_tracking
Revises: 002_add_clinvar_source_types
Create Date: 2026-02-13
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "003_add_source_sync_tracking"
down_revision = "002_add_clinvar_source_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create source sync checkpoint and source record ledger tables."""
    op.create_table(
        "source_sync_state",
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user_data_sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column(
            "checkpoint_kind",
            sa.String(length=32),
            nullable=False,
            server_default="none",
        ),
        sa.Column(
            "checkpoint_payload",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column("query_signature", sa.String(length=128), nullable=True),
        sa.Column(
            "last_successful_job_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_successful_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_attempted_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("upstream_etag", sa.String(length=255), nullable=True),
        sa.Column("upstream_last_modified", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
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
    op.create_index(
        "idx_source_sync_state_source_type",
        "source_sync_state",
        ["source_type"],
    )
    op.create_index(
        "idx_source_sync_state_query_signature",
        "source_sync_state",
        ["query_signature"],
    )
    op.create_index(
        "idx_source_sync_state_last_successful_job_id",
        "source_sync_state",
        ["last_successful_job_id"],
    )

    op.create_table(
        "source_record_ledger",
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user_data_sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("external_record_id", sa.String(length=255), primary_key=True),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("source_updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "first_seen_job_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "last_seen_job_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "last_changed_job_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "last_processed_at",
            sa.TIMESTAMP(timezone=True),
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
    op.create_index(
        "idx_source_record_ledger_source_last_processed",
        "source_record_ledger",
        ["source_id", "last_processed_at"],
    )
    op.create_index(
        "idx_source_record_ledger_first_seen_job_id",
        "source_record_ledger",
        ["first_seen_job_id"],
    )
    op.create_index(
        "idx_source_record_ledger_last_seen_job_id",
        "source_record_ledger",
        ["last_seen_job_id"],
    )
    op.create_index(
        "idx_source_record_ledger_last_changed_job_id",
        "source_record_ledger",
        ["last_changed_job_id"],
    )


def downgrade() -> None:
    """Drop source sync tracking tables."""
    op.drop_table("source_record_ledger")
    op.drop_table("source_sync_state")
