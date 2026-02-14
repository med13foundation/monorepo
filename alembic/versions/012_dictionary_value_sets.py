"""Add coded dictionary value set tables.

Revision ID: 012_dictionary_value_sets
Revises: 011_dictionary_type_tables
Create Date: 2026-02-14
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "012_dictionary_value_sets"
down_revision = "011_dictionary_type_tables"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name for index in _inspector().get_indexes(table_name)
    )


def _has_unique_constraint(table_name: str, constraint_name: str) -> bool:
    return any(
        constraint.get("name") == constraint_name
        for constraint in _inspector().get_unique_constraints(table_name)
    )


def _ensure_coded_variable_unique_key() -> None:
    """Ensure `(id, data_type)` can be referenced by a composite foreign key."""
    if not _has_table("variable_definitions"):
        return
    if _has_unique_constraint("variable_definitions", "uq_vardef_id_data_type"):
        return
    with op.batch_alter_table("variable_definitions") as batch_op:
        batch_op.create_unique_constraint(
            "uq_vardef_id_data_type",
            ["id", "data_type"],
        )


def _create_value_sets_table() -> None:
    if _has_table("value_sets"):
        return

    op.create_table(
        "value_sets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("variable_id", sa.String(length=64), nullable=False),
        sa.Column(
            "variable_data_type",
            sa.String(length=32),
            nullable=False,
            server_default="CODED",
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        sa.Column(
            "is_extensible",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "created_by",
            sa.String(length=128),
            nullable=False,
            server_default="seed",
        ),
        sa.Column("source_ref", sa.String(length=1024), nullable=True),
        sa.Column(
            "review_status",
            sa.String(length=32),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["variable_id", "variable_data_type"],
            ["variable_definitions.id", "variable_definitions.data_type"],
            name="fk_value_sets_variable_coded",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("variable_id", name="uq_value_sets_variable_id"),
        sa.CheckConstraint(
            "variable_data_type = 'CODED'",
            name="ck_value_sets_variable_data_type_coded",
        ),
        comment="Enumerated value sets for CODED variables",
    )


def _create_value_set_items_table() -> None:
    if _has_table("value_set_items"):
        return

    op.create_table(
        "value_set_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("value_set_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("display_label", sa.String(length=255), nullable=False),
        sa.Column(
            "synonyms",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "created_by",
            sa.String(length=128),
            nullable=False,
            server_default="seed",
        ),
        sa.Column("source_ref", sa.String(length=1024), nullable=True),
        sa.Column(
            "review_status",
            sa.String(length=32),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["value_set_id"],
            ["value_sets.id"],
            name="fk_value_set_items_value_set_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "value_set_id",
            "code",
            name="uq_value_set_items_value_set_code",
        ),
        comment="Allowed canonical codes and synonyms per value set",
    )

    if not _has_index("value_set_items", "idx_value_set_items_value_set"):
        op.create_index(
            "idx_value_set_items_value_set",
            "value_set_items",
            ["value_set_id"],
            unique=False,
        )


def _seed_value_sets_for_existing_coded_variables() -> None:
    if not _has_table("value_sets") or not _has_table("variable_definitions"):
        return

    op.execute(
        sa.text(
            """
            INSERT INTO value_sets (
                id,
                variable_id,
                variable_data_type,
                name,
                description,
                is_extensible,
                created_by,
                review_status
            )
            SELECT
                vd.id,
                vd.id,
                'CODED',
                COALESCE(vd.display_name, vd.canonical_name) || ' Value Set',
                'Autogenerated value set backfilled for existing CODED variable.',
                FALSE,
                'migration:012_dictionary_value_sets',
                'ACTIVE'
            FROM variable_definitions vd
            WHERE
                vd.data_type = 'CODED'
                AND NOT EXISTS (
                    SELECT 1 FROM value_sets vs WHERE vs.variable_id = vd.id
                )
            """,
        ),
    )


def upgrade() -> None:
    _ensure_coded_variable_unique_key()
    _create_value_sets_table()
    _create_value_set_items_table()
    _seed_value_sets_for_existing_coded_variables()


def downgrade() -> None:
    if _has_table("value_set_items"):
        if _has_index("value_set_items", "idx_value_set_items_value_set"):
            op.drop_index(
                "idx_value_set_items_value_set",
                table_name="value_set_items",
            )
        op.drop_table("value_set_items")

    if _has_table("value_sets"):
        op.drop_table("value_sets")

    if _has_table("variable_definitions") and _has_unique_constraint(
        "variable_definitions",
        "uq_vardef_id_data_type",
    ):
        with op.batch_alter_table("variable_definitions") as batch_op:
            batch_op.drop_constraint("uq_vardef_id_data_type", type_="unique")
