"""Add source document lifecycle table for Document Store MVP.

Revision ID: 007_add_source_documents_mvp
Revises: 006_queue_payload_refs
Create Date: 2026-02-14
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "007_add_source_documents_mvp"
down_revision = "006_queue_payload_refs"
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
    if not _has_table("source_documents"):
        op.create_table(
            "source_documents",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=False),
                primary_key=True,
            ),
            sa.Column(
                "research_space_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("research_spaces.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "source_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("user_data_sources.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "ingestion_job_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("external_record_id", sa.String(length=255), nullable=False),
            sa.Column("source_type", sa.String(length=32), nullable=False),
            sa.Column("document_format", sa.String(length=64), nullable=False),
            sa.Column("raw_storage_key", sa.String(length=500), nullable=True),
            sa.Column("enriched_storage_key", sa.String(length=500), nullable=True),
            sa.Column("content_hash", sa.String(length=128), nullable=True),
            sa.Column("content_length_chars", sa.Integer(), nullable=True),
            sa.Column(
                "enrichment_status",
                sa.String(length=32),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("enrichment_method", sa.String(length=64), nullable=True),
            sa.Column(
                "enrichment_agent_run_id",
                postgresql.UUID(as_uuid=False),
                nullable=True,
            ),
            sa.Column(
                "extraction_status",
                sa.String(length=32),
                nullable=False,
                server_default="pending",
            ),
            sa.Column(
                "extraction_agent_run_id",
                postgresql.UUID(as_uuid=False),
                nullable=True,
            ),
            sa.Column(
                "metadata_payload",
                postgresql.JSONB,
                nullable=False,
                server_default="{}",
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
            sa.UniqueConstraint(
                "source_id",
                "external_record_id",
                name="uq_source_documents_source_external_record",
            ),
        )

    table_name = "source_documents"
    if not _has_index(table_name, "idx_source_documents_source_enrichment_status"):
        op.create_index(
            "idx_source_documents_source_enrichment_status",
            table_name,
            ["source_id", "enrichment_status"],
        )
    if not _has_index(table_name, "idx_source_documents_source_extraction_status"):
        op.create_index(
            "idx_source_documents_source_extraction_status",
            table_name,
            ["source_id", "extraction_status"],
        )
    if not _has_index(table_name, "idx_source_documents_source_id"):
        op.create_index(
            "idx_source_documents_source_id",
            table_name,
            ["source_id"],
        )
    if not _has_index(table_name, "idx_source_documents_research_space_id"):
        op.create_index(
            "idx_source_documents_research_space_id",
            table_name,
            ["research_space_id"],
        )
    if not _has_index(table_name, "idx_source_documents_ingestion_job_id"):
        op.create_index(
            "idx_source_documents_ingestion_job_id",
            table_name,
            ["ingestion_job_id"],
        )
    if not _has_index(table_name, "idx_source_documents_source_type"):
        op.create_index(
            "idx_source_documents_source_type",
            table_name,
            ["source_type"],
        )
    if not _has_index(table_name, "idx_source_documents_enrichment_status"):
        op.create_index(
            "idx_source_documents_enrichment_status",
            table_name,
            ["enrichment_status"],
        )
    if not _has_index(table_name, "idx_source_documents_extraction_status"):
        op.create_index(
            "idx_source_documents_extraction_status",
            table_name,
            ["extraction_status"],
        )


def downgrade() -> None:
    if _has_table("source_documents"):
        op.drop_table("source_documents")
