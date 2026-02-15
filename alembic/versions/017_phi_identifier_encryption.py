"""Add PHI identifier blind-index columns for column-level encryption.

Revision ID: 017_phi_identifier_encryption
Revises: 016_enable_kernel_rls
Create Date: 2026-02-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "017_phi_identifier_encryption"
down_revision = "016_enable_kernel_rls"
branch_labels = None
depends_on = None

_TABLE_NAME = "entity_identifiers"
_COLUMN_BLIND_INDEX = "identifier_blind_index"
_COLUMN_ENCRYPTION_KEY_VERSION = "encryption_key_version"
_COLUMN_BLIND_INDEX_VERSION = "blind_index_version"
_INDEX_BLIND_LOOKUP = "idx_identifier_blind_lookup"
_INDEX_ENTITY_NS_BLIND_UNIQUE = "idx_identifier_entity_ns_blind_unique"


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


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        index.get("name") == index_name
        for index in _inspector().get_indexes(table_name)
    )


def upgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return

    with op.batch_alter_table(_TABLE_NAME) as batch_op:
        if not _has_column(_TABLE_NAME, _COLUMN_BLIND_INDEX):
            batch_op.add_column(
                sa.Column(
                    _COLUMN_BLIND_INDEX,
                    sa.String(length=64),
                    nullable=True,
                ),
            )
        if not _has_column(_TABLE_NAME, _COLUMN_ENCRYPTION_KEY_VERSION):
            batch_op.add_column(
                sa.Column(
                    _COLUMN_ENCRYPTION_KEY_VERSION,
                    sa.String(length=32),
                    nullable=True,
                ),
            )
        if not _has_column(_TABLE_NAME, _COLUMN_BLIND_INDEX_VERSION):
            batch_op.add_column(
                sa.Column(
                    _COLUMN_BLIND_INDEX_VERSION,
                    sa.String(length=32),
                    nullable=True,
                ),
            )

    if not _has_index(_TABLE_NAME, _INDEX_BLIND_LOOKUP):
        op.create_index(
            _INDEX_BLIND_LOOKUP,
            _TABLE_NAME,
            ["namespace", _COLUMN_BLIND_INDEX],
            unique=False,
        )

    if not _has_index(_TABLE_NAME, _INDEX_ENTITY_NS_BLIND_UNIQUE):
        op.create_index(
            _INDEX_ENTITY_NS_BLIND_UNIQUE,
            _TABLE_NAME,
            ["entity_id", "namespace", _COLUMN_BLIND_INDEX],
            unique=True,
        )


def downgrade() -> None:
    if not _has_table(_TABLE_NAME):
        return

    if _has_index(_TABLE_NAME, _INDEX_ENTITY_NS_BLIND_UNIQUE):
        op.drop_index(_INDEX_ENTITY_NS_BLIND_UNIQUE, table_name=_TABLE_NAME)
    if _has_index(_TABLE_NAME, _INDEX_BLIND_LOOKUP):
        op.drop_index(_INDEX_BLIND_LOOKUP, table_name=_TABLE_NAME)

    with op.batch_alter_table(_TABLE_NAME) as batch_op:
        if _has_column(_TABLE_NAME, _COLUMN_BLIND_INDEX_VERSION):
            batch_op.drop_column(_COLUMN_BLIND_INDEX_VERSION)
        if _has_column(_TABLE_NAME, _COLUMN_ENCRYPTION_KEY_VERSION):
            batch_op.drop_column(_COLUMN_ENCRYPTION_KEY_VERSION)
        if _has_column(_TABLE_NAME, _COLUMN_BLIND_INDEX):
            batch_op.drop_column(_COLUMN_BLIND_INDEX)
