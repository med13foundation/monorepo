"""Add page-load performance indexes for sessions and kernel listings.

Revision ID: 021_add_page_load_perf_indexes
Revises: 020_ingestion_job_runtime_fields
Create Date: 2026-02-25
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "021_add_page_load_perf_indexes"
down_revision = "020_ingestion_job_runtime_fields"
branch_labels = None
depends_on = None


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


def _create_index(
    *,
    table_name: str,
    index_name: str,
    columns: list[str],
) -> None:
    if not _has_table(table_name):
        return
    if _has_index(table_name, index_name):
        return
    op.create_index(index_name, table_name, columns)


def _drop_index(*, table_name: str, index_name: str) -> None:
    if not _has_index(table_name, index_name):
        return
    op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    _create_index(
        table_name="sessions",
        index_name="idx_sessions_session_token",
        columns=["session_token"],
    )
    _create_index(
        table_name="sessions",
        index_name="idx_sessions_refresh_token",
        columns=["refresh_token"],
    )
    _create_index(
        table_name="relations",
        index_name="idx_relations_space_created_at",
        columns=["research_space_id", "created_at"],
    )
    _create_index(
        table_name="observations",
        index_name="idx_obs_space_created_at",
        columns=["research_space_id", "created_at"],
    )


def downgrade() -> None:
    _drop_index(
        table_name="observations",
        index_name="idx_obs_space_created_at",
    )
    _drop_index(
        table_name="relations",
        index_name="idx_relations_space_created_at",
    )
    _drop_index(
        table_name="sessions",
        index_name="idx_sessions_refresh_token",
    )
    _drop_index(
        table_name="sessions",
        index_name="idx_sessions_session_token",
    )
