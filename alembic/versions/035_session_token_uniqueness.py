"""Enforce unique active session tokens.

Revision ID: 035_session_token_uniqueness
Revises: 034_claim_participant_fk
Create Date: 2026-03-05
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "035_session_token_uniqueness"
down_revision = "034_claim_participant_fk"
branch_labels = None
depends_on = None

_TABLE_NAME = "sessions"
_ACCESS_INDEX_NAME = "uq_sessions_active_session_token"
_REFRESH_INDEX_NAME = "uq_sessions_active_refresh_token"


def upgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    _revoke_duplicate_active_sessions()

    if not _has_index(_TABLE_NAME, _ACCESS_INDEX_NAME):
        op.create_index(
            _ACCESS_INDEX_NAME,
            _TABLE_NAME,
            ["session_token"],
            unique=True,
            postgresql_where=sa.text("status = 'ACTIVE'"),
        )

    if not _has_index(_TABLE_NAME, _REFRESH_INDEX_NAME):
        op.create_index(
            _REFRESH_INDEX_NAME,
            _TABLE_NAME,
            ["refresh_token"],
            unique=True,
            postgresql_where=sa.text("status = 'ACTIVE'"),
        )


def downgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return

    if _has_index(_TABLE_NAME, _ACCESS_INDEX_NAME):
        op.drop_index(_ACCESS_INDEX_NAME, table_name=_TABLE_NAME)

    if _has_index(_TABLE_NAME, _REFRESH_INDEX_NAME):
        op.drop_index(_REFRESH_INDEX_NAME, table_name=_TABLE_NAME)


def _revoke_duplicate_active_sessions() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY session_token
                    ORDER BY created_at DESC, id DESC
                ) AS access_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY refresh_token
                    ORDER BY created_at DESC, id DESC
                ) AS refresh_rank
            FROM sessions
            WHERE status = 'ACTIVE'
        )
        UPDATE sessions AS target
        SET
            status = 'REVOKED',
            last_activity = NOW()
        FROM ranked
        WHERE target.id = ranked.id
          AND (ranked.access_rank > 1 OR ranked.refresh_rank > 1);
        """,
    )


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        index.get("name") == index_name for index in inspector.get_indexes(table_name)
    )
