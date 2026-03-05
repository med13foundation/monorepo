"""Add first-class semantic fields to relation_claims.

Revision ID: 029_relation_claim_semantics
Revises: 028_evidence_sentence_prov
Create Date: 2026-03-04
"""

# ruff: noqa: S608

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "029_relation_claim_semantics"
down_revision = "028_evidence_sentence_prov"
branch_labels = None
depends_on = None

_TABLE_NAME = "relation_claims"
_POLARITY_COLUMN = "polarity"
_CLAIM_TEXT_COLUMN = "claim_text"
_CLAIM_SECTION_COLUMN = "claim_section"
_POLARITY_CHECK = "ck_relation_claims_polarity"
_POLARITY_INDEX = "idx_relation_claims_space_polarity"
_POLARITY_VALUES: tuple[str, ...] = (
    "SUPPORT",
    "REFUTE",
    "UNCERTAIN",
    "HYPOTHESIS",
)


def upgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return

    with op.batch_alter_table(
        _TABLE_NAME,
        reflect_kwargs={"resolve_fks": False},
    ) as batch_op:
        if not _has_column(_TABLE_NAME, _POLARITY_COLUMN):
            batch_op.add_column(
                sa.Column(
                    _POLARITY_COLUMN,
                    sa.String(length=16),
                    nullable=False,
                    server_default="UNCERTAIN",
                ),
            )
        if not _has_column(_TABLE_NAME, _CLAIM_TEXT_COLUMN):
            batch_op.add_column(
                sa.Column(
                    _CLAIM_TEXT_COLUMN,
                    sa.Text(),
                    nullable=True,
                ),
            )
        if not _has_column(_TABLE_NAME, _CLAIM_SECTION_COLUMN):
            batch_op.add_column(
                sa.Column(
                    _CLAIM_SECTION_COLUMN,
                    sa.String(length=64),
                    nullable=True,
                ),
            )

    if _find_check_constraint_name(_TABLE_NAME, _POLARITY_CHECK) is None:
        with op.batch_alter_table(
            _TABLE_NAME,
            reflect_kwargs={"resolve_fks": False},
        ) as batch_op:
            batch_op.create_check_constraint(
                _POLARITY_CHECK,
                f"{_POLARITY_COLUMN} IN ({_quoted_values(_POLARITY_VALUES)})",
            )

    if not _has_index(_TABLE_NAME, _POLARITY_INDEX):
        op.create_index(
            _POLARITY_INDEX,
            _TABLE_NAME,
            ["research_space_id", _POLARITY_COLUMN],
        )


def downgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return

    bind = op.get_bind()

    if _has_index(_TABLE_NAME, _POLARITY_INDEX):
        op.drop_index(_POLARITY_INDEX, table_name=_TABLE_NAME)

    if bind.dialect.name == "sqlite":
        _downgrade_sqlite_relation_claims_table()
        return

    check_constraint_name = _find_check_constraint_name(_TABLE_NAME, _POLARITY_CHECK)
    if check_constraint_name is not None:
        with op.batch_alter_table(
            _TABLE_NAME,
            reflect_kwargs={"resolve_fks": False},
        ) as batch_op:
            batch_op.drop_constraint(check_constraint_name, type_="check")

    with op.batch_alter_table(
        _TABLE_NAME,
        reflect_kwargs={"resolve_fks": False},
    ) as batch_op:
        if _has_column(_TABLE_NAME, _CLAIM_SECTION_COLUMN):
            batch_op.drop_column(_CLAIM_SECTION_COLUMN)
        if _has_column(_TABLE_NAME, _CLAIM_TEXT_COLUMN):
            batch_op.drop_column(_CLAIM_TEXT_COLUMN)
        if _has_column(_TABLE_NAME, _POLARITY_COLUMN):
            batch_op.drop_column(_POLARITY_COLUMN)


def _downgrade_sqlite_relation_claims_table() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(_TABLE_NAME)
    keep_columns = [
        column
        for column in columns
        if column["name"]
        not in {_POLARITY_COLUMN, _CLAIM_TEXT_COLUMN, _CLAIM_SECTION_COLUMN}
    ]
    if not keep_columns:
        return

    table_name = _TABLE_NAME
    temp_table_name = f"{table_name}__downgrade_tmp"
    quoted_temp_name = _quote_identifier(temp_table_name)
    quoted_table_name = _quote_identifier(table_name)

    column_defs = ", ".join(
        _sqlite_column_definition(column=column, bind=bind) for column in keep_columns
    )
    pk_columns = (
        inspector.get_pk_constraint(table_name).get("constrained_columns") or []
    )
    if pk_columns:
        pk_expr = ", ".join(_quote_identifier(column) for column in pk_columns)
        column_defs = f"{column_defs}, PRIMARY KEY ({pk_expr})"

    op.execute(
        sa.text(f"CREATE TABLE {quoted_temp_name} ({column_defs})"),
    )  # noqa: S608
    keep_column_names = ", ".join(
        _quote_identifier(column["name"]) for column in keep_columns
    )
    op.execute(
        sa.text(
            # Uses quoted identifiers derived from SQLAlchemy reflection.
            f"INSERT INTO {quoted_temp_name} ({keep_column_names}) "
            f"SELECT {keep_column_names} FROM {quoted_table_name}",
        ),
    )
    op.execute(sa.text(f"DROP TABLE {quoted_table_name}"))  # noqa: S608
    op.execute(
        sa.text(
            f"ALTER TABLE {quoted_temp_name} RENAME TO {quoted_table_name}",  # noqa: S608
        ),
    )


def _sqlite_column_definition(*, column: dict[str, object], bind: sa.Connection) -> str:
    column_name = str(column["name"])
    compiled_type = bind.dialect.type_compiler.process(column["type"])
    nullable = bool(column.get("nullable", True))
    default = column.get("default")
    parts = [_quote_identifier(column_name), compiled_type]
    if not nullable:
        parts.append("NOT NULL")
    if isinstance(default, str) and default.strip():
        parts.append(f"DEFAULT {default}")
    return " ".join(parts)


def _quote_identifier(identifier: str) -> str:
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def _quoted_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        index.get("name") == index_name for index in inspector.get_indexes(table_name)
    )


def _find_check_constraint_name(
    table_name: str,
    constraint_name: str,
) -> str | None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for constraint in inspector.get_check_constraints(table_name):
        name = constraint.get("name")
        if not isinstance(name, str):
            continue
        if name == constraint_name or name.endswith(f"_{constraint_name}"):
            return name
    return None
