"""Add append-only pipeline run events ledger.

Revision ID: 037_pipeline_run_events
Revises: 036_pipeline_job_kind
Create Date: 2026-03-09
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "037_pipeline_run_events"
down_revision = "036_pipeline_job_kind"
branch_labels = None
depends_on = None

_TABLE_NAME = "pipeline_run_events"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def _is_postgresql() -> bool:
    return _dialect_name() == "postgresql"


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def upgrade() -> None:
    if _has_table(_TABLE_NAME):
        return
    payload_type = (
        postgresql.JSONB(astext_type=sa.Text()) if _is_postgresql() else sa.JSON()
    )
    payload_default = sa.text("'{}'::jsonb") if _is_postgresql() else sa.text("'{}'")
    seq_type = sa.BigInteger() if _is_postgresql() else sa.Integer()
    uuid_type: sa.TypeEngine[object] = (
        postgresql.UUID(as_uuid=False) if _is_postgresql() else sa.String(length=36)
    )

    op.create_table(
        _TABLE_NAME,
        sa.Column("seq", seq_type, primary_key=True, autoincrement=True),
        sa.Column(
            "research_space_id",
            uuid_type,
            sa.ForeignKey("research_spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            uuid_type,
            sa.ForeignKey("user_data_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pipeline_run_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("scope_kind", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=255), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("agent_kind", sa.String(length=64), nullable=True),
        sa.Column("agent_run_id", sa.String(length=255), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("queue_wait_ms", sa.BigInteger(), nullable=True),
        sa.Column("timeout_budget_ms", sa.BigInteger(), nullable=True),
        sa.Column(
            "payload",
            payload_type,
            nullable=False,
            server_default=payload_default,
        ),
    )
    op.create_index(
        "ix_pipeline_run_events_research_space_id",
        _TABLE_NAME,
        ["research_space_id"],
    )
    op.create_index("ix_pipeline_run_events_source_id", _TABLE_NAME, ["source_id"])
    op.create_index(
        "ix_pipeline_run_events_pipeline_run_id",
        _TABLE_NAME,
        ["pipeline_run_id"],
    )
    op.create_index("ix_pipeline_run_events_event_type", _TABLE_NAME, ["event_type"])
    op.create_index("ix_pipeline_run_events_stage", _TABLE_NAME, ["stage"])
    op.create_index("ix_pipeline_run_events_scope_kind", _TABLE_NAME, ["scope_kind"])
    op.create_index("ix_pipeline_run_events_scope_id", _TABLE_NAME, ["scope_id"])
    op.create_index("ix_pipeline_run_events_level", _TABLE_NAME, ["level"])
    op.create_index("ix_pipeline_run_events_status", _TABLE_NAME, ["status"])
    op.create_index("ix_pipeline_run_events_agent_kind", _TABLE_NAME, ["agent_kind"])
    op.create_index(
        "ix_pipeline_run_events_agent_run_id",
        _TABLE_NAME,
        ["agent_run_id"],
    )
    op.create_index(
        "ix_pipeline_run_events_occurred_at",
        _TABLE_NAME,
        ["occurred_at"],
    )
    op.create_index(
        "idx_pipeline_run_events_source_run_occurred",
        _TABLE_NAME,
        ["source_id", "pipeline_run_id", "occurred_at"],
    )
    op.create_index(
        "idx_pipeline_run_events_run_scope",
        _TABLE_NAME,
        ["pipeline_run_id", "scope_kind", "scope_id"],
    )
    op.create_index(
        "idx_pipeline_run_events_run_agent",
        _TABLE_NAME,
        ["pipeline_run_id", "agent_kind", "agent_run_id"],
    )


def downgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return
    op.drop_index("idx_pipeline_run_events_run_agent", table_name=_TABLE_NAME)
    op.drop_index("idx_pipeline_run_events_run_scope", table_name=_TABLE_NAME)
    op.drop_index("idx_pipeline_run_events_source_run_occurred", table_name=_TABLE_NAME)
    op.drop_index("ix_pipeline_run_events_occurred_at", table_name=_TABLE_NAME)
    op.drop_index("ix_pipeline_run_events_agent_run_id", table_name=_TABLE_NAME)
    op.drop_index("ix_pipeline_run_events_agent_kind", table_name=_TABLE_NAME)
    op.drop_index("ix_pipeline_run_events_status", table_name=_TABLE_NAME)
    op.drop_index("ix_pipeline_run_events_level", table_name=_TABLE_NAME)
    op.drop_index("ix_pipeline_run_events_scope_id", table_name=_TABLE_NAME)
    op.drop_index("ix_pipeline_run_events_scope_kind", table_name=_TABLE_NAME)
    op.drop_index("ix_pipeline_run_events_stage", table_name=_TABLE_NAME)
    op.drop_index("ix_pipeline_run_events_event_type", table_name=_TABLE_NAME)
    op.drop_index("ix_pipeline_run_events_pipeline_run_id", table_name=_TABLE_NAME)
    op.drop_index("ix_pipeline_run_events_source_id", table_name=_TABLE_NAME)
    op.drop_index("ix_pipeline_run_events_research_space_id", table_name=_TABLE_NAME)
    op.drop_table(_TABLE_NAME)
