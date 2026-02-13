"""Add ClinVar source types to source enums.

Revision ID: 002_add_clinvar_source_types
Revises: 001_kernel_schema
Create Date: 2026-02-13
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "002_add_clinvar_source_types"
down_revision = "001_kernel_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add missing source type enum values for PubMed and ClinVar."""
    op.execute("ALTER TYPE sourcetypeenum ADD VALUE IF NOT EXISTS 'pubmed'")
    op.execute("ALTER TYPE sourcetypeenum ADD VALUE IF NOT EXISTS 'clinvar'")
    op.execute("ALTER TYPE usersourcetypeenum ADD VALUE IF NOT EXISTS 'clinvar'")


def downgrade() -> None:
    """Downgrade is intentionally a no-op because PostgreSQL enums are additive."""
    # PostgreSQL does not support removing enum values safely in place.
    # Reverting these values would require rebuilding enum types and migrating data.
    return
