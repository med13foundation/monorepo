"""Compatibility marker for the split relation-evidence rollout.

Revision ID: 005_rel_evidence_rollout_marker
Revises: 004_rel_evidence_extract_queue
Create Date: 2026-02-14
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "005_rel_evidence_rollout_marker"
down_revision = "004_rel_evidence_extract_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Compatibility marker only; schema changes were completed in 004."""


def downgrade() -> None:
    """Compatibility marker only; no schema rollback required here."""
