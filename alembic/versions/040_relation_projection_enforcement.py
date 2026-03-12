"""Enforce claim-backed lineage for canonical relations.

Revision ID: 040_relation_projection_enforce
Revises: 039_relation_projection_lineage
Create Date: 2026-03-11
"""

# ruff: noqa: S608

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "040_relation_projection_enforce"
down_revision = "039_relation_projection_lineage"
branch_labels = None
depends_on = None

_RELATIONS_TABLE = "relations"
_PROJECTION_TABLE = "relation_projection_sources"
_DIAGNOSTIC_FUNCTION = "find_orphan_relations_without_projection"
_TRIGGER_FUNCTION = "enforce_relation_projection_lineage"
_TRIGGER_NAME = "trg_enforce_relation_projection_lineage"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not _has_table(_RELATIONS_TABLE) or not _has_table(_PROJECTION_TABLE):
        return
    _create_orphan_diagnostic_function()
    _create_constraint_trigger()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if _has_table(_RELATIONS_TABLE):
        op.execute(
            sa.text(
                f'DROP TRIGGER IF EXISTS "{_TRIGGER_NAME}" ON "{_RELATIONS_TABLE}"',
            ),
        )
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_TRIGGER_FUNCTION}() CASCADE"))
    op.execute(
        sa.text(
            "DROP FUNCTION IF EXISTS "
            f"{_DIAGNOSTIC_FUNCTION}(uuid, integer, integer) CASCADE",
        ),
    )


def _create_orphan_diagnostic_function() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {_DIAGNOSTIC_FUNCTION}(
                in_research_space_id uuid DEFAULT NULL,
                in_limit integer DEFAULT NULL,
                in_offset integer DEFAULT 0
            )
            RETURNS TABLE (
                relation_id uuid,
                research_space_id uuid
            )
            LANGUAGE sql
            STABLE
            AS $$
                SELECT r.id, r.research_space_id
                FROM relations AS r
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM relation_projection_sources AS rps
                    WHERE rps.relation_id = r.id
                      AND rps.research_space_id = r.research_space_id
                )
                  AND (
                    in_research_space_id IS NULL
                    OR r.research_space_id = in_research_space_id
                  )
                ORDER BY r.created_at ASC, r.id ASC
                LIMIT COALESCE(in_limit, 2147483647)
                OFFSET COALESCE(in_offset, 0)
            $$;
            """,
        ),
    )


def _create_constraint_trigger() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {_TRIGGER_FUNCTION}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM relation_projection_sources AS rps
                    WHERE rps.relation_id = NEW.id
                      AND rps.research_space_id = NEW.research_space_id
                ) THEN
                    RAISE EXCEPTION
                        'Canonical relation % in research space % is missing claim-backed projection lineage',
                        NEW.id,
                        NEW.research_space_id
                        USING ERRCODE = '23514';
                END IF;
                RETURN NULL;
            END;
            $$;
            """,
        ),
    )
    op.execute(
        sa.text(
            f'DROP TRIGGER IF EXISTS "{_TRIGGER_NAME}" ON "{_RELATIONS_TABLE}"',
        ),
    )
    op.execute(
        sa.text(
            f"""
            CREATE CONSTRAINT TRIGGER "{_TRIGGER_NAME}"
            AFTER INSERT OR UPDATE ON "{_RELATIONS_TABLE}"
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            EXECUTE FUNCTION {_TRIGGER_FUNCTION}();
            """,
        ),
    )


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()
