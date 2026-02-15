"""Add dictionary versioning and validity columns.

Revision ID: 014_dict_version_validity
Revises: 013_dictionary_embeddings
Create Date: 2026-02-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "014_dict_version_validity"
down_revision = "013_dictionary_embeddings"
branch_labels = None
depends_on = None

_VERSIONED_TABLES: tuple[str, ...] = (
    "variable_definitions",
    "variable_synonyms",
    "dictionary_domain_contexts",
    "dictionary_sensitivity_levels",
    "dictionary_entity_types",
    "dictionary_relation_types",
    "entity_resolution_policies",
    "relation_constraints",
    "transform_registry",
)


def _bind() -> sa.Connection:
    return op.get_bind()


def _inspector() -> sa.Inspector:
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
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


def _add_versioning_columns(table_name: str) -> None:
    if not _has_table(table_name):
        return

    with op.batch_alter_table(table_name) as batch_op:
        if not _has_column(table_name, "is_active"):
            batch_op.add_column(
                sa.Column(
                    "is_active",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.true(),
                ),
            )
        if not _has_column(table_name, "valid_from"):
            batch_op.add_column(
                sa.Column(
                    "valid_from",
                    sa.TIMESTAMP(timezone=True),
                    nullable=False,
                    server_default=sa.func.now(),
                ),
            )
        if not _has_column(table_name, "valid_to"):
            batch_op.add_column(
                sa.Column(
                    "valid_to",
                    sa.TIMESTAMP(timezone=True),
                    nullable=True,
                ),
            )
        if not _has_column(table_name, "superseded_by"):
            batch_op.add_column(
                sa.Column(
                    "superseded_by",
                    sa.String(length=64),
                    nullable=True,
                ),
            )


def _backfill_versioning_state(table_name: str) -> None:  # noqa: C901
    if not _has_table(table_name):
        return

    has_review_status = _has_column(table_name, "review_status")
    has_created_at = _has_column(table_name, "created_at")
    has_reviewed_at = _has_column(table_name, "reviewed_at")
    has_updated_at = _has_column(table_name, "updated_at")

    columns: list[sa.ColumnClause[object]] = [
        sa.column("is_active", sa.Boolean()),
        sa.column("valid_from", sa.TIMESTAMP(timezone=True)),
        sa.column("valid_to", sa.TIMESTAMP(timezone=True)),
    ]
    if has_review_status:
        columns.append(sa.column("review_status", sa.String()))
    if has_created_at:
        columns.append(sa.column("created_at", sa.TIMESTAMP(timezone=True)))
    if has_reviewed_at:
        columns.append(sa.column("reviewed_at", sa.TIMESTAMP(timezone=True)))
    if has_updated_at:
        columns.append(sa.column("updated_at", sa.TIMESTAMP(timezone=True)))

    table = sa.table(
        table_name,
        *columns,
    )

    is_active_expr: sa.ColumnElement[bool] = sa.func.coalesce(
        table.c.is_active,
        sa.true(),
    )
    if has_review_status:
        is_active_expr = sa.case(
            (table.c.review_status == "REVOKED", sa.false()),
            else_=is_active_expr,
        )

    valid_from_candidates: list[sa.ColumnElement[object]] = [table.c.valid_from]
    if has_created_at:
        valid_from_candidates.append(table.c.created_at)
    valid_from_candidates.append(sa.func.now())
    valid_from_expr = sa.func.coalesce(*valid_from_candidates)

    if has_review_status:
        revoked_valid_to_candidates: list[sa.ColumnElement[object]] = [table.c.valid_to]
        if has_reviewed_at:
            revoked_valid_to_candidates.append(table.c.reviewed_at)
        if has_updated_at:
            revoked_valid_to_candidates.append(table.c.updated_at)
        revoked_valid_to_candidates.append(sa.func.now())
        valid_to_expr: sa.ColumnElement[object] = sa.case(
            (
                table.c.review_status == "REVOKED",
                sa.func.coalesce(*revoked_valid_to_candidates),
            ),
            else_=sa.null(),
        )
    else:
        valid_to_expr = sa.null()

    # Align versioning fields with existing review lifecycle where available.
    op.execute(
        sa.update(table).values(
            is_active=is_active_expr,
            valid_from=valid_from_expr,
            valid_to=valid_to_expr,
        ),
    )


def _add_temporal_consistency_constraint(table_name: str) -> None:
    if not _has_table(table_name):
        return

    constraint_name = f"ck_{table_name}_active_validity"
    if _has_check_constraint(table_name, constraint_name):
        return

    with op.batch_alter_table(table_name) as batch_op:
        batch_op.create_check_constraint(
            constraint_name,
            "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))",
        )


def _drop_temporal_consistency_constraint(table_name: str) -> None:
    if not _has_table(table_name):
        return

    constraint_name = f"ck_{table_name}_active_validity"
    if not _has_check_constraint(table_name, constraint_name):
        return

    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_constraint(constraint_name, type_="check")


def _drop_versioning_columns(table_name: str) -> None:
    if not _has_table(table_name):
        return

    with op.batch_alter_table(table_name) as batch_op:
        if _has_column(table_name, "superseded_by"):
            batch_op.drop_column("superseded_by")
        if _has_column(table_name, "valid_to"):
            batch_op.drop_column("valid_to")
        if _has_column(table_name, "valid_from"):
            batch_op.drop_column("valid_from")
        if _has_column(table_name, "is_active"):
            batch_op.drop_column("is_active")


def upgrade() -> None:
    for table_name in _VERSIONED_TABLES:
        _add_versioning_columns(table_name)
    for table_name in _VERSIONED_TABLES:
        _backfill_versioning_state(table_name)
    for table_name in _VERSIONED_TABLES:
        _add_temporal_consistency_constraint(table_name)


def downgrade() -> None:
    for table_name in _VERSIONED_TABLES:
        _drop_temporal_consistency_constraint(table_name)
    for table_name in _VERSIONED_TABLES:
        _drop_versioning_columns(table_name)
