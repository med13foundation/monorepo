"""Enable row-level security policies on kernel tables.

Revision ID: 016_enable_kernel_rls
Revises: 015_dict_transforms_upgrade
Create Date: 2026-02-15
"""

# ruff: noqa: S608

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "016_enable_kernel_rls"
down_revision = "015_dict_transforms_upgrade"
branch_labels = None
depends_on = None

_SPACE_TABLES: tuple[str, ...] = (
    "entities",
    "observations",
    "relations",
    "provenance",
)
_ENTITY_IDENTIFIERS_TABLE = "entity_identifiers"
_RELATION_EVIDENCE_TABLE = "relation_evidence"

_BYPASS_RLS = (
    "COALESCE(NULLIF(current_setting('app.bypass_rls', true), '')::boolean, false)"
)
_IS_ADMIN = (
    "COALESCE(NULLIF(current_setting('app.is_admin', true), '')::boolean, false)"
)
_HAS_PHI_ACCESS = (
    "COALESCE(NULLIF(current_setting('app.has_phi_access', true), '')::boolean, false)"
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


def _policy_name(table_name: str) -> str:
    return f"rls_{table_name}_access"


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


def _entity_identifier_access_condition() -> str:
    return f"""
        (
            {_BYPASS_RLS}
            OR {_IS_ADMIN}
            OR (
                EXISTS (
                    SELECT 1
                    FROM entities AS e
                    WHERE e.id = entity_identifiers.entity_id
                      AND {_space_access_condition("e.research_space_id")}
                )
                AND (
                    entity_identifiers.sensitivity <> 'PHI'
                    OR {_HAS_PHI_ACCESS}
                )
            )
        )
    """


def _relation_evidence_access_condition() -> str:
    return f"""
        (
            {_BYPASS_RLS}
            OR {_IS_ADMIN}
            OR EXISTS (
                SELECT 1
                FROM relations AS r
                WHERE r.id = relation_evidence.relation_id
                  AND {_space_access_condition("r.research_space_id")}
            )
        )
    """


def _enable_rls(table_name: str) -> None:
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))


def _disable_rls(table_name: str) -> None:
    op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))


def _drop_policy_if_exists(table_name: str) -> None:
    policy_name = _policy_name(table_name)
    if not _has_policy(table_name, policy_name):
        return
    op.execute(
        sa.text(f'DROP POLICY "{policy_name}" ON "{table_name}"'),
    )


def _create_policy(table_name: str, condition: str) -> None:
    if not _has_table(table_name):
        return

    _enable_rls(table_name)
    _drop_policy_if_exists(table_name)

    policy_name = _policy_name(table_name)
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "{policy_name}"
            ON "{table_name}"
            FOR ALL
            USING ({condition})
            WITH CHECK ({condition})
            """,
        ),
    )


def upgrade() -> None:
    if not _is_postgres():
        return

    for table_name in _SPACE_TABLES:
        _create_policy(table_name, _space_access_condition("research_space_id"))

    _create_policy(
        _ENTITY_IDENTIFIERS_TABLE,
        _entity_identifier_access_condition(),
    )

    if _has_table(_RELATION_EVIDENCE_TABLE):
        _create_policy(
            _RELATION_EVIDENCE_TABLE,
            _relation_evidence_access_condition(),
        )


def downgrade() -> None:
    if not _is_postgres():
        return

    tables_to_reset: tuple[str, ...] = (
        *_SPACE_TABLES,
        _ENTITY_IDENTIFIERS_TABLE,
        _RELATION_EVIDENCE_TABLE,
    )
    for table_name in tables_to_reset:
        if not _has_table(table_name):
            continue
        _drop_policy_if_exists(table_name)
        _disable_rls(table_name)
