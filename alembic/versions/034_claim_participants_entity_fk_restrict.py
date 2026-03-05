"""Harden claim_participants entity FK delete behavior.

Revision ID: 034_claim_participant_fk
Revises: 033_overlay_updated_at_columns
Create Date: 2026-03-05
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "034_claim_participant_fk"
down_revision = "033_overlay_updated_at_columns"
branch_labels = None
depends_on = None

_TABLE_NAME = "claim_participants"
_FK_NAME = "fk_claim_participants_entity_space"


def upgrade() -> None:
    _recreate_entity_space_fk(ondelete="RESTRICT")


def downgrade() -> None:
    _recreate_entity_space_fk(ondelete="SET NULL")


def _recreate_entity_space_fk(*, ondelete: str) -> None:
    if not _has_table(_TABLE_NAME):
        return

    with op.batch_alter_table(
        _TABLE_NAME,
        reflect_kwargs={"resolve_fks": False},
    ) as batch_op:
        if _has_foreign_key_constraint(_TABLE_NAME, _FK_NAME):
            batch_op.drop_constraint(_FK_NAME, type_="foreignkey")
        batch_op.create_foreign_key(
            _FK_NAME,
            "entities",
            ["entity_id", "research_space_id"],
            ["id", "research_space_id"],
            ondelete=ondelete,
        )


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_foreign_key_constraint(table_name: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        (fk.get("name") or "") == constraint_name
        for fk in inspector.get_foreign_keys(table_name)
    )
