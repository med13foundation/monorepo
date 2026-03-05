"""Add kernel entity embeddings table with RLS and ANN index support.

Revision ID: 031_entity_embeddings_hybrid
Revises: 030_claim_evidence_table
Create Date: 2026-03-04
"""

# ruff: noqa: S608

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from src.models.database.types import VectorEmbedding

# revision identifiers, used by Alembic.
revision = "031_entity_embeddings_hybrid"
down_revision = "030_claim_evidence_table"
branch_labels = None
depends_on = None

_TABLE_NAME = "entity_embeddings"
_POLICY_NAME = "rls_entity_embeddings_access"

_BYPASS_RLS = (
    "COALESCE(NULLIF(current_setting('app.bypass_rls', true), '')::boolean, false)"
)
_IS_ADMIN = (
    "COALESCE(NULLIF(current_setting('app.is_admin', true), '')::boolean, false)"
)
_CURRENT_USER_ID = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"


def _bind() -> sa.Connection:
    return op.get_bind()


def _inspector() -> sa.Inspector:
    return sa.inspect(_bind())


def _is_postgres() -> bool:
    return _bind().dialect.name == "postgresql"


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    indexes = _inspector().get_indexes(table_name)
    return any(index.get("name") == index_name for index in indexes)


def _has_policy(table_name: str, policy_name: str) -> bool:
    if not _is_postgres() or not _has_table(table_name):
        return False
    row = (
        _bind()
        .execute(
            sa.text(
                """
                SELECT 1
                FROM pg_policies
                WHERE schemaname = current_schema()
                  AND tablename = :table_name
                  AND policyname = :policy_name
                LIMIT 1
                """,
            ),
            {"table_name": table_name, "policy_name": policy_name},
        )
        .scalar_one_or_none()
    )
    return row is not None


def _space_access_condition(space_column: str) -> str:
    return f"""
        (
            {_BYPASS_RLS}
            OR {_IS_ADMIN}
            OR (
                {_CURRENT_USER_ID} IS NOT NULL
                AND {space_column} IN (
                    SELECT rsm.space_id
                    FROM research_space_memberships AS rsm
                    WHERE rsm.user_id = {_CURRENT_USER_ID}
                      AND rsm.is_active = TRUE
                    UNION
                    SELECT rs.id
                    FROM research_spaces AS rs
                    WHERE rs.owner_id = {_CURRENT_USER_ID}
                )
            )
        )
    """


def _entity_embedding_access_condition() -> str:
    return f"""
        (
            {_BYPASS_RLS}
            OR {_IS_ADMIN}
            OR EXISTS (
                SELECT 1
                FROM entities AS e
                WHERE e.id = entity_embeddings.entity_id
                  AND e.research_space_id = entity_embeddings.research_space_id
                  AND {_space_access_condition("e.research_space_id")}
            )
        )
    """


def _enable_rls(table_name: str) -> None:
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))


def _disable_rls(table_name: str) -> None:
    op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))


def _drop_policy_if_exists() -> None:
    if not _has_policy(_TABLE_NAME, _POLICY_NAME):
        return
    op.execute(sa.text(f'DROP POLICY "{_POLICY_NAME}" ON "{_TABLE_NAME}"'))


def _create_policy() -> None:
    if not _is_postgres() or not _has_table(_TABLE_NAME):
        return
    _enable_rls(_TABLE_NAME)
    _drop_policy_if_exists()
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "{_POLICY_NAME}"
            ON "{_TABLE_NAME}"
            FOR ALL
            USING ({_entity_embedding_access_condition()})
            WITH CHECK ({_entity_embedding_access_condition()})
            """,
        ),
    )


def upgrade() -> None:
    if not _has_table(_TABLE_NAME):
        op.create_table(
            _TABLE_NAME,
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("research_space_id", sa.UUID(), nullable=False),
            sa.Column("entity_id", sa.UUID(), nullable=False),
            sa.Column("embedding", VectorEmbedding(1536), nullable=False),
            sa.Column("embedding_model", sa.String(length=100), nullable=False),
            sa.Column(
                "embedding_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
            sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["entity_id"],
                ["entities.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["research_space_id"],
                ["research_spaces.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "entity_id",
                name="uq_entity_embeddings_entity_id",
            ),
            sa.UniqueConstraint(
                "research_space_id",
                "entity_id",
                name="uq_entity_embeddings_space_entity",
            ),
        )

    if not _has_index(_TABLE_NAME, "idx_entity_embeddings_space"):
        op.create_index(
            "idx_entity_embeddings_space",
            _TABLE_NAME,
            ["research_space_id"],
            unique=False,
        )

    if not _has_index(_TABLE_NAME, "idx_entity_embeddings_entity"):
        op.create_index(
            "idx_entity_embeddings_entity",
            _TABLE_NAME,
            ["entity_id"],
            unique=False,
        )

    if _is_postgres():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute(
            sa.text(
                """
                CREATE INDEX IF NOT EXISTS idx_entity_embeddings_embedding_hnsw
                ON entity_embeddings
                USING hnsw (embedding vector_cosine_ops)
                """,
            ),
        )
        _create_policy()


def downgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return

    if _is_postgres():
        _drop_policy_if_exists()
        _disable_rls(_TABLE_NAME)
        op.execute(
            sa.text("DROP INDEX IF EXISTS idx_entity_embeddings_embedding_hnsw"),
        )

    op.drop_index("idx_entity_embeddings_entity", table_name=_TABLE_NAME)
    op.drop_index("idx_entity_embeddings_space", table_name=_TABLE_NAME)
    op.drop_table(_TABLE_NAME)
