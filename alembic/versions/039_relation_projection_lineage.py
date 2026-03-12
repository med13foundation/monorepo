"""Add claim-backed lineage table for canonical relation projections.

Revision ID: 039_relation_projection_lineage
Revises: 038_pipeline_run_event_audit_columns
Create Date: 2026-03-11
"""

# ruff: noqa: S608

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "039_relation_projection_lineage"
down_revision = "038_pipeline_event_audit"
branch_labels = None
depends_on = None

_RELATIONS_TABLE = "relations"
_RELATIONS_SPACE_UNIQUE = "uq_relations_id_space"
_TABLE_NAME = "relation_projection_sources"
_POLICY_NAME = "rls_relation_projection_sources_access"


def upgrade() -> None:
    _ensure_relations_space_unique()
    _create_relation_projection_sources_table()
    _enable_rls(_TABLE_NAME, _POLICY_NAME)


def downgrade() -> None:
    _drop_rls(_TABLE_NAME, _POLICY_NAME)
    if _has_table(_TABLE_NAME):
        for index_name in (
            "idx_relation_projection_sources_space_origin",
            "idx_relation_projection_sources_claim_id",
            "idx_relation_projection_sources_relation_id",
        ):
            if _has_index(_TABLE_NAME, index_name):
                op.drop_index(index_name, table_name=_TABLE_NAME)
        op.drop_table(_TABLE_NAME)

    if _has_table(_RELATIONS_TABLE) and _has_unique_constraint(
        _RELATIONS_TABLE,
        _RELATIONS_SPACE_UNIQUE,
    ):
        with op.batch_alter_table(
            _RELATIONS_TABLE,
            reflect_kwargs={"resolve_fks": False},
        ) as batch_op:
            batch_op.drop_constraint(_RELATIONS_SPACE_UNIQUE, type_="unique")


def _ensure_relations_space_unique() -> None:
    if not _has_table(_RELATIONS_TABLE) or _has_unique_constraint(
        _RELATIONS_TABLE,
        _RELATIONS_SPACE_UNIQUE,
    ):
        return

    with op.batch_alter_table(
        _RELATIONS_TABLE,
        reflect_kwargs={"resolve_fks": False},
    ) as batch_op:
        batch_op.create_unique_constraint(
            _RELATIONS_SPACE_UNIQUE,
            ["id", "research_space_id"],
        )


def _create_relation_projection_sources_table() -> None:
    if _has_table(_TABLE_NAME):
        return

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        metadata_type: sa.types.TypeEngine[dict[str, object]] = postgresql.JSONB()
        metadata_default = sa.text("'{}'::jsonb")
    else:
        metadata_type = sa.JSON()
        metadata_default = sa.text("'{}'")

    op.create_table(
        _TABLE_NAME,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "research_space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("projection_origin", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_documents.id"),
            nullable=True,
        ),
        sa.Column("agent_run_id", sa.String(length=255), nullable=True),
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
                "projection_origin IN "
                "('EXTRACTION','CLAIM_RESOLUTION','MANUAL_RELATION','GRAPH_CONNECTION')"
            ),
            name="ck_relation_projection_sources_origin",
        ),
        sa.ForeignKeyConstraint(
            ["relation_id", "research_space_id"],
            ["relations.id", "relations.research_space_id"],
            name="fk_relation_projection_sources_relation_space",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id", "research_space_id"],
            ["relation_claims.id", "relation_claims.research_space_id"],
            name="fk_relation_projection_sources_claim_space",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "research_space_id",
            "relation_id",
            "claim_id",
            name="uq_relation_projection_sources_edge_claim",
        ),
    )

    op.create_index(
        "idx_relation_projection_sources_relation_id",
        _TABLE_NAME,
        ["relation_id"],
    )
    op.create_index(
        "idx_relation_projection_sources_claim_id",
        _TABLE_NAME,
        ["claim_id"],
    )
    op.create_index(
        "idx_relation_projection_sources_space_origin",
        _TABLE_NAME,
        ["research_space_id", "projection_origin"],
    )


def _enable_rls(table_name: str, policy_name: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not _has_table(table_name):
        return

    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(f'DROP POLICY IF EXISTS "{policy_name}" ON "{table_name}"'),
    )
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

    op.execute(
        sa.text(f'DROP POLICY IF EXISTS "{policy_name}" ON "{table_name}"'),
    )
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
