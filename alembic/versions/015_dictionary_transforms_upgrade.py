"""Upgrade transform registry with safety and verification metadata.

Revision ID: 015_dict_transforms_upgrade
Revises: 014_dict_version_validity
Create Date: 2026-02-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "015_dict_transforms_upgrade"
down_revision = "014_dict_version_validity"
branch_labels = None
depends_on = None

_TABLE_NAME = "transform_registry"
_DATA_TYPE_TABLE = "dictionary_data_types"
_CATEGORY_CONSTRAINT = "ck_transform_registry_category"
_INPUT_DATA_TYPE_FK = "fk_transform_registry_input_data_type_dictionary_data_types"
_OUTPUT_DATA_TYPE_FK = "fk_transform_registry_output_data_type_dictionary_data_types"


def _bind() -> sa.Connection:
    return op.get_bind()


def _inspector() -> sa.Inspector:
    return sa.inspect(_bind())


def _is_postgres() -> bool:
    return _bind().dialect.name == "postgresql"


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    if _is_postgres():
        exists = (
            _bind()
            .execute(
                sa.text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = :table_name
                      AND column_name = :column_name
                      AND table_schema = ANY(current_schemas(false))
                    LIMIT 1
                    """,
                ),
                {
                    "table_name": table_name,
                    "column_name": column_name,
                },
            )
            .scalar_one_or_none()
        )
        return exists is not None
    return column_name in {
        column["name"] for column in _inspector().get_columns(table_name)
    }


def _has_check_constraint(table_name: str, constraint_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        constraint.get("name") == constraint_name
        for constraint in _inspector().get_check_constraints(table_name)
    )


def _has_foreign_key(table_name: str, foreign_key_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        fk.get("name") == foreign_key_name
        for fk in _inspector().get_foreign_keys(table_name)
    )


def _add_upgrade_columns() -> None:
    if not _has_table(_TABLE_NAME):
        return

    with op.batch_alter_table(_TABLE_NAME) as batch_op:
        if not _has_column(_TABLE_NAME, "category"):
            batch_op.add_column(
                sa.Column(
                    "category",
                    sa.String(length=32),
                    nullable=False,
                    server_default="UNIT_CONVERSION",
                ),
            )
        if not _has_column(_TABLE_NAME, "input_data_type"):
            batch_op.add_column(
                sa.Column(
                    "input_data_type",
                    sa.String(length=32),
                    nullable=True,
                ),
            )
        if not _has_column(_TABLE_NAME, "output_data_type"):
            batch_op.add_column(
                sa.Column(
                    "output_data_type",
                    sa.String(length=32),
                    nullable=True,
                ),
            )
        if not _has_column(_TABLE_NAME, "is_deterministic"):
            batch_op.add_column(
                sa.Column(
                    "is_deterministic",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.true(),
                ),
            )
        if not _has_column(_TABLE_NAME, "is_production_allowed"):
            batch_op.add_column(
                sa.Column(
                    "is_production_allowed",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            )
        if not _has_column(_TABLE_NAME, "test_input"):
            batch_op.add_column(
                sa.Column(
                    "test_input",
                    sa.JSON(),
                    nullable=True,
                ),
            )
        if not _has_column(_TABLE_NAME, "expected_output"):
            batch_op.add_column(
                sa.Column(
                    "expected_output",
                    sa.JSON(),
                    nullable=True,
                ),
            )
        if not _has_column(_TABLE_NAME, "description"):
            batch_op.add_column(
                sa.Column(
                    "description",
                    sa.Text(),
                    nullable=True,
                ),
            )


def _add_upgrade_constraints() -> None:
    if not _has_table(_TABLE_NAME):
        return

    with op.batch_alter_table(_TABLE_NAME) as batch_op:
        if _has_table(_DATA_TYPE_TABLE) and not _has_foreign_key(
            _TABLE_NAME,
            _INPUT_DATA_TYPE_FK,
        ):
            batch_op.create_foreign_key(
                _INPUT_DATA_TYPE_FK,
                _DATA_TYPE_TABLE,
                ["input_data_type"],
                ["id"],
            )

        if _has_table(_DATA_TYPE_TABLE) and not _has_foreign_key(
            _TABLE_NAME,
            _OUTPUT_DATA_TYPE_FK,
        ):
            batch_op.create_foreign_key(
                _OUTPUT_DATA_TYPE_FK,
                _DATA_TYPE_TABLE,
                ["output_data_type"],
                ["id"],
            )

        if not _has_check_constraint(_TABLE_NAME, _CATEGORY_CONSTRAINT):
            batch_op.create_check_constraint(
                _CATEGORY_CONSTRAINT,
                "category IN ('UNIT_CONVERSION', 'NORMALIZATION', 'DERIVATION')",
            )


def _backfill_upgrade_columns() -> None:
    if not _has_table(_TABLE_NAME):
        return

    transform_table = sa.table(
        _TABLE_NAME,
        sa.column("category", sa.String()),
        sa.column("is_deterministic", sa.Boolean()),
        sa.column("is_production_allowed", sa.Boolean()),
    )

    op.execute(
        sa.update(transform_table).values(
            category=sa.func.coalesce(
                transform_table.c.category,
                "UNIT_CONVERSION",
            ),
            is_deterministic=sa.func.coalesce(
                transform_table.c.is_deterministic,
                sa.true(),
            ),
            is_production_allowed=sa.func.coalesce(
                transform_table.c.is_production_allowed,
                sa.false(),
            ),
        ),
    )


def _drop_upgrade_constraints() -> None:
    if not _has_table(_TABLE_NAME):
        return

    with op.batch_alter_table(_TABLE_NAME) as batch_op:
        if _has_check_constraint(_TABLE_NAME, _CATEGORY_CONSTRAINT):
            batch_op.drop_constraint(_CATEGORY_CONSTRAINT, type_="check")
        if _has_foreign_key(_TABLE_NAME, _INPUT_DATA_TYPE_FK):
            batch_op.drop_constraint(_INPUT_DATA_TYPE_FK, type_="foreignkey")
        if _has_foreign_key(_TABLE_NAME, _OUTPUT_DATA_TYPE_FK):
            batch_op.drop_constraint(_OUTPUT_DATA_TYPE_FK, type_="foreignkey")


def _drop_upgrade_columns() -> None:
    if not _has_table(_TABLE_NAME):
        return

    with op.batch_alter_table(_TABLE_NAME) as batch_op:
        if _has_column(_TABLE_NAME, "description"):
            batch_op.drop_column("description")
        if _has_column(_TABLE_NAME, "expected_output"):
            batch_op.drop_column("expected_output")
        if _has_column(_TABLE_NAME, "test_input"):
            batch_op.drop_column("test_input")
        if _has_column(_TABLE_NAME, "is_production_allowed"):
            batch_op.drop_column("is_production_allowed")
        if _has_column(_TABLE_NAME, "is_deterministic"):
            batch_op.drop_column("is_deterministic")
        if _has_column(_TABLE_NAME, "output_data_type"):
            batch_op.drop_column("output_data_type")
        if _has_column(_TABLE_NAME, "input_data_type"):
            batch_op.drop_column("input_data_type")
        if _has_column(_TABLE_NAME, "category"):
            batch_op.drop_column("category")


def upgrade() -> None:
    _add_upgrade_columns()
    _backfill_upgrade_columns()
    _add_upgrade_constraints()


def downgrade() -> None:
    _drop_upgrade_constraints()
    _drop_upgrade_columns()
