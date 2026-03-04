"""Create claim_evidence table for claim-centric evidence storage.

Revision ID: 030_claim_evidence_table
Revises: 029_relation_claim_semantics
Create Date: 2026-03-04
"""

# ruff: noqa: S608

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "030_claim_evidence_table"
down_revision = "029_relation_claim_semantics"
branch_labels = None
depends_on = None

_TABLE_NAME = "claim_evidence"
_POLICY_NAME = "rls_claim_evidence_access"


def upgrade() -> None:
    _create_claim_evidence_table()
    _enable_claim_evidence_rls()


def downgrade() -> None:
    _drop_claim_evidence_table()


def _create_claim_evidence_table() -> None:
    if _has_table(_TABLE_NAME):
        return
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"
    if is_postgresql:
        metadata_payload_type = postgresql.JSONB()
        metadata_payload_default = sa.text("'{}'::jsonb")
    else:
        metadata_payload_type = sa.JSON()
        metadata_payload_default = sa.text("'{}'")

    op.create_table(
        _TABLE_NAME,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("relation_claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_run_id", sa.String(length=255), nullable=True),
        sa.Column("sentence", sa.Text(), nullable=True),
        sa.Column("sentence_source", sa.String(length=32), nullable=True),
        sa.Column("sentence_confidence", sa.String(length=16), nullable=True),
        sa.Column("sentence_rationale", sa.Text(), nullable=True),
        sa.Column("figure_reference", sa.Text(), nullable=True),
        sa.Column("table_reference", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column(
            "metadata_payload",
            metadata_payload_type,
            nullable=False,
            server_default=metadata_payload_default,
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
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_claim_evidence_confidence_range",
        ),
        sa.CheckConstraint(
            "sentence_source IS NULL OR sentence_source IN ('verbatim_span', 'artana_generated')",
            name="ck_claim_evidence_sentence_source",
        ),
        sa.CheckConstraint(
            "sentence_confidence IS NULL OR sentence_confidence IN ('low', 'medium', 'high')",
            name="ck_claim_evidence_sentence_confidence",
        ),
    )

    op.create_index("idx_claim_evidence_claim_id", _TABLE_NAME, ["claim_id"])
    op.create_index(
        "idx_claim_evidence_source_document_id",
        _TABLE_NAME,
        ["source_document_id"],
    )
    op.create_index("idx_claim_evidence_created_at", _TABLE_NAME, ["created_at"])


def _enable_claim_evidence_rls() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not _has_table(_TABLE_NAME):
        return

    op.execute(
        sa.text(f'ALTER TABLE "{_TABLE_NAME}" ENABLE ROW LEVEL SECURITY'),
    )  # noqa: S608
    op.execute(
        sa.text(f'ALTER TABLE "{_TABLE_NAME}" FORCE ROW LEVEL SECURITY'),
    )  # noqa: S608
    op.execute(
        sa.text(
            f'DROP POLICY IF EXISTS "{_POLICY_NAME}" ON "{_TABLE_NAME}"',  # noqa: S608
        ),
    )
    op.execute(
        sa.text(
            # Identifiers are fixed migration constants.
            f"""
            CREATE POLICY "{_POLICY_NAME}"
            ON "{_TABLE_NAME}"
            FOR ALL
            USING (
                (
                    COALESCE(NULLIF(current_setting('app.bypass_rls', true), '')::boolean, false)
                    OR COALESCE(NULLIF(current_setting('app.is_admin', true), '')::boolean, false)
                    OR (
                        NULLIF(current_setting('app.current_user_id', true), '')::uuid IS NOT NULL
                        AND EXISTS (
                            SELECT 1
                            FROM relation_claims AS rc
                            WHERE rc.id = claim_id
                              AND rc.research_space_id IN (
                                  SELECT rsm.space_id
                                  FROM research_space_memberships AS rsm
                                  WHERE rsm.user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
                                    AND rsm.is_active = TRUE
                                  UNION
                                  SELECT rs.id
                                  FROM research_spaces AS rs
                                  WHERE rs.owner_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
                              )
                        )
                    )
                )
            )
            WITH CHECK (
                (
                    COALESCE(NULLIF(current_setting('app.bypass_rls', true), '')::boolean, false)
                    OR COALESCE(NULLIF(current_setting('app.is_admin', true), '')::boolean, false)
                    OR (
                        NULLIF(current_setting('app.current_user_id', true), '')::uuid IS NOT NULL
                        AND EXISTS (
                            SELECT 1
                            FROM relation_claims AS rc
                            WHERE rc.id = claim_id
                              AND rc.research_space_id IN (
                                  SELECT rsm.space_id
                                  FROM research_space_memberships AS rsm
                                  WHERE rsm.user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
                                    AND rsm.is_active = TRUE
                                  UNION
                                  SELECT rs.id
                                  FROM research_spaces AS rs
                                  WHERE rs.owner_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
                              )
                        )
                    )
                )
            )
            """,
        ),
    )


def _drop_claim_evidence_table() -> None:
    if not _has_table(_TABLE_NAME):
        return

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                f'DROP POLICY IF EXISTS "{_POLICY_NAME}" ON "{_TABLE_NAME}"',  # noqa: S608
            ),
        )
        op.execute(
            sa.text(f'ALTER TABLE "{_TABLE_NAME}" NO FORCE ROW LEVEL SECURITY'),
        )  # noqa: S608
        op.execute(
            sa.text(f'ALTER TABLE "{_TABLE_NAME}" DISABLE ROW LEVEL SECURITY'),
        )  # noqa: S608

    for index_name in (
        "idx_claim_evidence_created_at",
        "idx_claim_evidence_source_document_id",
        "idx_claim_evidence_claim_id",
    ):
        if _has_index(_TABLE_NAME, index_name):
            op.drop_index(index_name, table_name=_TABLE_NAME)

    op.drop_table(_TABLE_NAME)


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
