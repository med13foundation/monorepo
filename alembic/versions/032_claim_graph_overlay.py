"""Create claim_participants and claim_relations overlay tables.

Revision ID: 032_claim_graph_overlay
Revises: 031_entity_embeddings_hybrid
Create Date: 2026-03-04
"""

# ruff: noqa: S608

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "032_claim_graph_overlay"
down_revision = "031_entity_embeddings_hybrid"
branch_labels = None
depends_on = None

_RELATION_CLAIMS_TABLE = "relation_claims"
_RELATION_CLAIMS_SPACE_UNIQUE = "uq_relation_claims_id_space"

_CLAIM_PARTICIPANTS_TABLE = "claim_participants"
_CLAIM_PARTICIPANTS_POLICY = "rls_claim_participants_access"

_CLAIM_RELATIONS_TABLE = "claim_relations"
_CLAIM_RELATIONS_POLICY = "rls_claim_relations_access"


def upgrade() -> None:
    _ensure_relation_claims_space_unique()
    _create_claim_participants_table()
    _create_claim_relations_table()
    _enable_rls(_CLAIM_PARTICIPANTS_TABLE, _CLAIM_PARTICIPANTS_POLICY)
    _enable_rls(_CLAIM_RELATIONS_TABLE, _CLAIM_RELATIONS_POLICY)


def downgrade() -> None:
    _drop_rls(_CLAIM_RELATIONS_TABLE, _CLAIM_RELATIONS_POLICY)
    _drop_rls(_CLAIM_PARTICIPANTS_TABLE, _CLAIM_PARTICIPANTS_POLICY)

    if _has_table(_CLAIM_RELATIONS_TABLE):
        for index_name in (
            "idx_claim_relations_review_status",
            "idx_claim_relations_space_type",
            "idx_claim_relations_target",
            "idx_claim_relations_source",
        ):
            if _has_index(_CLAIM_RELATIONS_TABLE, index_name):
                op.drop_index(index_name, table_name=_CLAIM_RELATIONS_TABLE)
        op.drop_table(_CLAIM_RELATIONS_TABLE)

    if _has_table(_CLAIM_PARTICIPANTS_TABLE):
        for index_name in (
            "idx_claim_participants_space_role",
            "idx_claim_participants_space_entity",
            "idx_claim_participants_claim",
        ):
            if _has_index(_CLAIM_PARTICIPANTS_TABLE, index_name):
                op.drop_index(index_name, table_name=_CLAIM_PARTICIPANTS_TABLE)
        op.drop_table(_CLAIM_PARTICIPANTS_TABLE)

    if _has_table(_RELATION_CLAIMS_TABLE) and _has_unique_constraint(
        _RELATION_CLAIMS_TABLE,
        _RELATION_CLAIMS_SPACE_UNIQUE,
    ):
        with op.batch_alter_table(
            _RELATION_CLAIMS_TABLE,
            reflect_kwargs={"resolve_fks": False},
        ) as batch_op:
            batch_op.drop_constraint(
                _RELATION_CLAIMS_SPACE_UNIQUE,
                type_="unique",
            )


def _create_claim_participants_table() -> None:
    if _has_table(_CLAIM_PARTICIPANTS_TABLE):
        return

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        qualifiers_type: sa.types.TypeEngine[dict[str, object]] = postgresql.JSONB()
        qualifiers_default = sa.text("'{}'::jsonb")
    else:
        qualifiers_type = sa.JSON()
        qualifiers_default = sa.text("'{}'")

    op.create_table(
        _CLAIM_PARTICIPANTS_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "research_space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=512), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=True),
        sa.Column(
            "qualifiers",
            qualifiers_type,
            nullable=False,
            server_default=qualifiers_default,
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
            "role IN ('SUBJECT', 'OBJECT', 'CONTEXT', 'QUALIFIER', 'MODIFIER')",
            name="ck_claim_participants_role",
        ),
        sa.CheckConstraint(
            "label IS NOT NULL OR entity_id IS NOT NULL",
            name="ck_claim_participants_anchor",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id", "research_space_id"],
            ["relation_claims.id", "relation_claims.research_space_id"],
            name="fk_claim_participants_claim_space",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id", "research_space_id"],
            ["entities.id", "entities.research_space_id"],
            name="fk_claim_participants_entity_space",
            ondelete="RESTRICT",
        ),
    )

    op.create_index(
        "idx_claim_participants_claim",
        _CLAIM_PARTICIPANTS_TABLE,
        ["claim_id"],
    )
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE INDEX IF NOT EXISTS idx_claim_participants_space_entity
                ON claim_participants (research_space_id, entity_id)
                WHERE entity_id IS NOT NULL
                """,
            ),
        )
    else:
        op.create_index(
            "idx_claim_participants_space_entity",
            _CLAIM_PARTICIPANTS_TABLE,
            ["research_space_id", "entity_id"],
        )
    op.create_index(
        "idx_claim_participants_space_role",
        _CLAIM_PARTICIPANTS_TABLE,
        ["research_space_id", "role"],
    )


def _create_claim_relations_table() -> None:
    if _has_table(_CLAIM_RELATIONS_TABLE):
        return

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        metadata_type: sa.types.TypeEngine[dict[str, object]] = postgresql.JSONB()
        metadata_default = sa.text("'{}'::jsonb")
    else:
        metadata_type = sa.JSON()
        metadata_default = sa.text("'{}'")

    op.create_table(
        _CLAIM_RELATIONS_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "research_space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relation_type", sa.String(length=32), nullable=False),
        sa.Column("agent_run_id", sa.String(length=255), nullable=True),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id"),
            nullable=True,
        ),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column(
            "review_status",
            sa.String(length=32),
            nullable=False,
            server_default="PROPOSED",
        ),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column(
            "metadata_payload",
            metadata_type,
            nullable=False,
            server_default=metadata_default,
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
            (
                "relation_type IN "
                "('SUPPORTS','CONTRADICTS','REFINES','CAUSES','UPSTREAM_OF',"
                "'DOWNSTREAM_OF','SAME_AS','GENERALIZES','INSTANCE_OF')"
            ),
            name="ck_claim_relations_type",
        ),
        sa.CheckConstraint(
            "source_claim_id <> target_claim_id",
            name="ck_claim_relations_no_self_loop",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_claim_relations_confidence_range",
        ),
        sa.CheckConstraint(
            "review_status IN ('PROPOSED','ACCEPTED','REJECTED')",
            name="ck_claim_relations_review_status",
        ),
        sa.ForeignKeyConstraint(
            ["source_claim_id", "research_space_id"],
            ["relation_claims.id", "relation_claims.research_space_id"],
            name="fk_claim_relations_source_space",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_claim_id", "research_space_id"],
            ["relation_claims.id", "relation_claims.research_space_id"],
            name="fk_claim_relations_target_space",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "research_space_id",
            "source_claim_id",
            "relation_type",
            "target_claim_id",
            name="uq_claim_relations_space_edge",
        ),
    )

    op.create_index(
        "idx_claim_relations_source",
        _CLAIM_RELATIONS_TABLE,
        ["source_claim_id"],
    )
    op.create_index(
        "idx_claim_relations_target",
        _CLAIM_RELATIONS_TABLE,
        ["target_claim_id"],
    )
    op.create_index(
        "idx_claim_relations_space_type",
        _CLAIM_RELATIONS_TABLE,
        ["research_space_id", "relation_type"],
    )
    op.create_index(
        "idx_claim_relations_review_status",
        _CLAIM_RELATIONS_TABLE,
        ["review_status"],
    )


def _ensure_relation_claims_space_unique() -> None:
    if not _has_table(_RELATION_CLAIMS_TABLE):
        return
    if _has_unique_constraint(_RELATION_CLAIMS_TABLE, _RELATION_CLAIMS_SPACE_UNIQUE):
        return

    with op.batch_alter_table(
        _RELATION_CLAIMS_TABLE,
        reflect_kwargs={"resolve_fks": False},
    ) as batch_op:
        batch_op.create_unique_constraint(
            _RELATION_CLAIMS_SPACE_UNIQUE,
            ["id", "research_space_id"],
        )


def _enable_rls(table_name: str, policy_name: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not _has_table(table_name):
        return

    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'DROP POLICY IF EXISTS "{policy_name}" ON "{table_name}"'))
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "{policy_name}"
            ON "{table_name}"
            FOR ALL
            USING ({_space_access_condition(table_name)})
            WITH CHECK ({_space_access_condition(table_name)})
            """,
        ),
    )


def _drop_rls(table_name: str, policy_name: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not _has_table(table_name):
        return

    op.execute(sa.text(f'DROP POLICY IF EXISTS "{policy_name}" ON "{table_name}"'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))


def _space_access_condition(table_name: str) -> str:
    return f"""
        (
            COALESCE(NULLIF(current_setting('app.bypass_rls', true), '')::boolean, false)
            OR COALESCE(NULLIF(current_setting('app.is_admin', true), '')::boolean, false)
            OR (
                NULLIF(current_setting('app.current_user_id', true), '')::uuid IS NOT NULL
                AND {table_name}.research_space_id IN (
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
    """


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


def _has_unique_constraint(table_name: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        constraint.get("name") == constraint_name
        for constraint in inspector.get_unique_constraints(table_name)
    )
