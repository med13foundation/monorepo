"""Add extraction queue payload reference columns.

Revision ID: 006_queue_payload_refs
Revises: 005_rel_evidence_rollout_marker
Create Date: 2026-02-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "006_queue_payload_refs"
down_revision = "005_rel_evidence_rollout_marker"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name for column in _inspector().get_columns(table_name)
    )


def _has_index(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name for index in _inspector().get_indexes(table_name)
    )


def _coerce_non_empty_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _backfill_payload_reference_columns() -> None:
    bind = op.get_bind()

    extraction_queue = sa.table(
        "extraction_queue",
        sa.column("id", sa.String()),
        sa.column("metadata_payload", sa.JSON()),
        sa.column("raw_storage_key", sa.String()),
        sa.column("payload_ref", sa.String()),
    )

    rows = bind.execute(
        sa.select(
            extraction_queue.c.id,
            extraction_queue.c.metadata_payload,
            extraction_queue.c.raw_storage_key,
            extraction_queue.c.payload_ref,
        ),
    ).mappings()

    for row in rows:
        metadata_payload = row["metadata_payload"]
        metadata = metadata_payload if isinstance(metadata_payload, dict) else {}

        update_values: dict[str, str] = {}

        if row["raw_storage_key"] is None:
            raw_storage_key = _coerce_non_empty_string(
                metadata.get("raw_storage_key"),
            )
            if raw_storage_key is not None:
                update_values["raw_storage_key"] = raw_storage_key

        if row["payload_ref"] is None:
            payload_ref = _coerce_non_empty_string(metadata.get("payload_ref"))
            if payload_ref is not None:
                update_values["payload_ref"] = payload_ref

        if not update_values:
            continue

        bind.execute(
            extraction_queue.update()
            .where(extraction_queue.c.id == row["id"])
            .values(**update_values),
        )


def upgrade() -> None:
    if not _has_table("extraction_queue"):
        return

    if not _has_column("extraction_queue", "raw_storage_key"):
        op.add_column(
            "extraction_queue",
            sa.Column("raw_storage_key", sa.String(length=500), nullable=True),
        )

    if not _has_column("extraction_queue", "payload_ref"):
        op.add_column(
            "extraction_queue",
            sa.Column("payload_ref", sa.String(length=500), nullable=True),
        )

    _backfill_payload_reference_columns()

    if not _has_index("extraction_queue", "idx_extraction_queue_raw_storage_key"):
        op.create_index(
            "idx_extraction_queue_raw_storage_key",
            "extraction_queue",
            ["raw_storage_key"],
        )

    if not _has_index("extraction_queue", "idx_extraction_queue_payload_ref"):
        op.create_index(
            "idx_extraction_queue_payload_ref",
            "extraction_queue",
            ["payload_ref"],
        )


def downgrade() -> None:
    if not _has_table("extraction_queue"):
        return

    if _has_index("extraction_queue", "idx_extraction_queue_payload_ref"):
        op.drop_index(
            "idx_extraction_queue_payload_ref",
            table_name="extraction_queue",
        )

    if _has_index("extraction_queue", "idx_extraction_queue_raw_storage_key"):
        op.drop_index(
            "idx_extraction_queue_raw_storage_key",
            table_name="extraction_queue",
        )

    if _has_column("extraction_queue", "payload_ref"):
        with op.batch_alter_table("extraction_queue") as batch_op:
            batch_op.drop_column("payload_ref")

    if _has_column("extraction_queue", "raw_storage_key"):
        with op.batch_alter_table("extraction_queue") as batch_op:
            batch_op.drop_column("raw_storage_key")
