"""Claim-first orchestration rollout migration.

Revision ID: 024_claim_first_orchestration
Revises: 023_active_synonym_unique
Create Date: 2026-02-27
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "024_claim_first_orchestration"
down_revision = "023_active_synonym_unique"
branch_labels = None
depends_on = None

_RELATION_CLAIMS_TABLE = "relation_claims"


def upgrade() -> None:
    _create_relation_claims_table()
    _enable_relation_claims_rls()
    _normalize_relation_statuses()
    _disable_relation_auto_promotion_for_all_spaces()


def downgrade() -> None:
    _drop_relation_claims_table()


def _create_relation_claims_table() -> None:
    if _has_table(_RELATION_CLAIMS_TABLE):
        return

    op.create_table(
        _RELATION_CLAIMS_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "research_space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_run_id", sa.String(length=255), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("source_label", sa.String(length=512), nullable=True),
        sa.Column("target_label", sa.String(length=512), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("validation_state", sa.String(length=32), nullable=False),
        sa.Column("validation_reason", sa.Text(), nullable=True),
        sa.Column("persistability", sa.String(length=32), nullable=False),
        sa.Column(
            "claim_status",
            sa.String(length=32),
            nullable=False,
            server_default="OPEN",
        ),
        sa.Column(
            "linked_relation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("relations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "metadata_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "triaged_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("triaged_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
        "idx_relation_claims_space",
        _RELATION_CLAIMS_TABLE,
        ["research_space_id"],
    )
    op.create_index(
        "idx_relation_claims_status",
        _RELATION_CLAIMS_TABLE,
        ["claim_status"],
    )
    op.create_index(
        "idx_relation_claims_validation_state",
        _RELATION_CLAIMS_TABLE,
        ["validation_state"],
    )
    op.create_index(
        "idx_relation_claims_persistability",
        _RELATION_CLAIMS_TABLE,
        ["persistability"],
    )
    op.create_index(
        "idx_relation_claims_source_document_id",
        _RELATION_CLAIMS_TABLE,
        ["source_document_id"],
    )
    op.create_index(
        "idx_relation_claims_linked_relation_id",
        _RELATION_CLAIMS_TABLE,
        ["linked_relation_id"],
    )
    op.create_index(
        "idx_relation_claims_space_created_at",
        _RELATION_CLAIMS_TABLE,
        ["research_space_id", "created_at"],
    )


def _normalize_relation_statuses() -> None:
    if not _has_table("relations"):
        return
    op.execute(
        sa.text(
            "UPDATE relations SET curation_status = 'DRAFT' WHERE curation_status = 'PENDING_REVIEW'",
        ),
    )


def _disable_relation_auto_promotion_for_all_spaces() -> None:
    if not _has_table("research_spaces"):
        return

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, settings FROM research_spaces")).all()
    for row in rows:
        raw_settings = row[1]
        settings = dict(raw_settings) if isinstance(raw_settings, dict) else {}
        relation_auto_promotion = settings.get("relation_auto_promotion")
        if isinstance(relation_auto_promotion, dict):
            relation_auto_promotion = dict(relation_auto_promotion)
        else:
            relation_auto_promotion = {}
        relation_auto_promotion["enabled"] = False
        settings["relation_auto_promotion"] = relation_auto_promotion
        bind.execute(
            sa.text(
                "UPDATE research_spaces "
                "SET settings = CAST(:settings AS jsonb) "
                "WHERE id = :space_id",
            ),
            {"settings": json.dumps(settings), "space_id": row[0]},
        )


def _enable_relation_claims_rls() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not _has_table(_RELATION_CLAIMS_TABLE):
        return

    op.execute(sa.text('ALTER TABLE "relation_claims" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('ALTER TABLE "relation_claims" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            'DROP POLICY IF EXISTS "rls_relation_claims_access" ON "relation_claims"',
        ),
    )
    op.execute(
        sa.text(
            """
            CREATE POLICY "rls_relation_claims_access"
            ON "relation_claims"
            FOR ALL
            USING (
                (
                    COALESCE(NULLIF(current_setting('app.bypass_rls', true), '')::boolean, false)
                    OR COALESCE(NULLIF(current_setting('app.is_admin', true), '')::boolean, false)
                    OR (
                        NULLIF(current_setting('app.current_user_id', true), '')::uuid IS NOT NULL
                        AND research_space_id IN (
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
            WITH CHECK (
                (
                    COALESCE(NULLIF(current_setting('app.bypass_rls', true), '')::boolean, false)
                    OR COALESCE(NULLIF(current_setting('app.is_admin', true), '')::boolean, false)
                    OR (
                        NULLIF(current_setting('app.current_user_id', true), '')::uuid IS NOT NULL
                        AND research_space_id IN (
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
            """,
        ),
    )


def _drop_relation_claims_table() -> None:
    if not _has_table(_RELATION_CLAIMS_TABLE):
        return
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                'DROP POLICY IF EXISTS "rls_relation_claims_access" ON "relation_claims"',
            ),
        )
        op.execute(
            sa.text(
                'ALTER TABLE "relation_claims" NO FORCE ROW LEVEL SECURITY',
            ),
        )
        op.execute(
            sa.text('ALTER TABLE "relation_claims" DISABLE ROW LEVEL SECURITY'),
        )
    for index_name in (
        "idx_relation_claims_space_created_at",
        "idx_relation_claims_linked_relation_id",
        "idx_relation_claims_source_document_id",
        "idx_relation_claims_persistability",
        "idx_relation_claims_validation_state",
        "idx_relation_claims_status",
        "idx_relation_claims_space",
    ):
        if _has_index(_RELATION_CLAIMS_TABLE, index_name):
            op.drop_index(index_name, table_name=_RELATION_CLAIMS_TABLE)
    op.drop_table(_RELATION_CLAIMS_TABLE)


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
