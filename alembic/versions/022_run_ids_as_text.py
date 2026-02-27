"""Store agent/provenance run identifiers as opaque text values.

Revision ID: 022_run_ids_as_text
Revises: 021_add_page_load_perf_indexes
Create Date: 2026-02-26
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "022_run_ids_as_text"
down_revision = "021_add_page_load_perf_indexes"
branch_labels = None
depends_on = None

_TEXT_RUN_ID_TYPE = sa.String(length=255)
_UUID_REGEX = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _upgrade_postgres()
        return
    _upgrade_generic()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _downgrade_postgres()
        return
    _downgrade_generic()


def _upgrade_postgres() -> None:
    op.execute(
        """
        ALTER TABLE source_documents
        ALTER COLUMN enrichment_agent_run_id TYPE TEXT
        USING enrichment_agent_run_id::text
        """,
    )
    op.execute(
        """
        ALTER TABLE source_documents
        ALTER COLUMN extraction_agent_run_id TYPE TEXT
        USING extraction_agent_run_id::text
        """,
    )
    op.execute(
        """
        ALTER TABLE relation_evidence
        ALTER COLUMN agent_run_id TYPE TEXT
        USING agent_run_id::text
        """,
    )
    op.execute(
        """
        ALTER TABLE provenance
        ALTER COLUMN extraction_run_id TYPE TEXT
        USING extraction_run_id::text
        """,
    )


def _upgrade_generic() -> None:
    if _has_table("source_documents"):
        with op.batch_alter_table(
            "source_documents",
            reflect_kwargs={"resolve_fks": False},
        ) as batch_op:
            batch_op.alter_column(
                "enrichment_agent_run_id",
                existing_type=postgresql.UUID(as_uuid=False),
                type_=_TEXT_RUN_ID_TYPE,
                existing_nullable=True,
            )
            batch_op.alter_column(
                "extraction_agent_run_id",
                existing_type=postgresql.UUID(as_uuid=False),
                type_=_TEXT_RUN_ID_TYPE,
                existing_nullable=True,
            )
    if _has_table("relation_evidence"):
        with op.batch_alter_table(
            "relation_evidence",
            reflect_kwargs={"resolve_fks": False},
        ) as batch_op:
            batch_op.alter_column(
                "agent_run_id",
                existing_type=postgresql.UUID(as_uuid=True),
                type_=_TEXT_RUN_ID_TYPE,
                existing_nullable=True,
            )
    if _has_table("provenance"):
        with op.batch_alter_table(
            "provenance",
            reflect_kwargs={"resolve_fks": False},
        ) as batch_op:
            batch_op.alter_column(
                "extraction_run_id",
                existing_type=postgresql.UUID(as_uuid=True),
                type_=_TEXT_RUN_ID_TYPE,
                existing_nullable=True,
            )


def _downgrade_postgres() -> None:
    # Non-UUID run ids are intentionally nulled when downgrading to UUID columns.
    op.execute(
        f"""
        ALTER TABLE source_documents
        ALTER COLUMN enrichment_agent_run_id TYPE UUID
        USING (
            CASE
                WHEN enrichment_agent_run_id ~* '{_UUID_REGEX}'
                THEN enrichment_agent_run_id::uuid
                ELSE NULL
            END
        )
        """,
    )
    op.execute(
        f"""
        ALTER TABLE source_documents
        ALTER COLUMN extraction_agent_run_id TYPE UUID
        USING (
            CASE
                WHEN extraction_agent_run_id ~* '{_UUID_REGEX}'
                THEN extraction_agent_run_id::uuid
                ELSE NULL
            END
        )
        """,
    )
    op.execute(
        f"""
        ALTER TABLE relation_evidence
        ALTER COLUMN agent_run_id TYPE UUID
        USING (
            CASE
                WHEN agent_run_id ~* '{_UUID_REGEX}'
                THEN agent_run_id::uuid
                ELSE NULL
            END
        )
        """,
    )
    op.execute(
        f"""
        ALTER TABLE provenance
        ALTER COLUMN extraction_run_id TYPE UUID
        USING (
            CASE
                WHEN extraction_run_id ~* '{_UUID_REGEX}'
                THEN extraction_run_id::uuid
                ELSE NULL
            END
        )
        """,
    )


def _downgrade_generic() -> None:
    if _has_table("source_documents"):
        with op.batch_alter_table(
            "source_documents",
            reflect_kwargs={"resolve_fks": False},
        ) as batch_op:
            batch_op.alter_column(
                "enrichment_agent_run_id",
                existing_type=_TEXT_RUN_ID_TYPE,
                type_=sa.String(length=36),
                existing_nullable=True,
            )
            batch_op.alter_column(
                "extraction_agent_run_id",
                existing_type=_TEXT_RUN_ID_TYPE,
                type_=sa.String(length=36),
                existing_nullable=True,
            )
    if _has_table("relation_evidence"):
        with op.batch_alter_table(
            "relation_evidence",
            reflect_kwargs={"resolve_fks": False},
        ) as batch_op:
            batch_op.alter_column(
                "agent_run_id",
                existing_type=_TEXT_RUN_ID_TYPE,
                type_=sa.String(length=36),
                existing_nullable=True,
            )
    if _has_table("provenance"):
        with op.batch_alter_table(
            "provenance",
            reflect_kwargs={"resolve_fks": False},
        ) as batch_op:
            batch_op.alter_column(
                "extraction_run_id",
                existing_type=_TEXT_RUN_ID_TYPE,
                type_=sa.String(length=36),
                existing_nullable=True,
            )


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()
