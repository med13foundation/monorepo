"""Add Concept Manager foundation schema.

Revision ID: 026_concept_manager_foundation
Revises: 025_graph_dict_hard_guarantees
Create Date: 2026-03-03
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision = "026_concept_manager_foundation"
down_revision = "025_graph_dict_hard_guarantees"
branch_labels = None
depends_on = None

_ACTIVE_VALIDITY_CHECK = (
    "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))"
)
_REVIEW_STATUS_CHECK = "review_status IN ('ACTIVE', 'PENDING_REVIEW', 'REVOKED')"


def upgrade() -> None:
    _create_concept_sets()
    _create_concept_members()
    _create_concept_aliases()
    _create_concept_links()
    _create_concept_policies()
    _create_concept_decisions()
    _create_concept_harness_results()
    _create_partial_indexes()


def downgrade() -> None:
    op.drop_table("concept_harness_results")
    op.drop_table("concept_decisions")
    op.drop_table("concept_policies")
    op.drop_table("concept_links")
    op.drop_table("concept_aliases")
    op.drop_table("concept_members")
    op.drop_table("concept_sets")


def _create_concept_sets() -> None:
    op.create_table(
        "concept_sets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("research_space_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain_context", sa.String(length=64), nullable=False),
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
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "valid_from",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("valid_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.UUID(), nullable=True),
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
            ["research_space_id"],
            ["research_spaces.id"],
            name="fk_concept_sets_research_space_id_research_spaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["domain_context"],
            ["dictionary_domain_contexts.id"],
            name="fk_concept_sets_domain_context_dictionary_domain_contexts",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by"],
            ["concept_sets.id"],
            name="fk_concept_sets_superseded_by_concept_sets",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_concept_sets"),
        sa.UniqueConstraint(
            "research_space_id",
            "slug",
            name="uq_concept_sets_space_slug",
        ),
        sa.UniqueConstraint("id", "research_space_id", name="uq_concept_sets_id_space"),
        sa.CheckConstraint(
            _ACTIVE_VALIDITY_CHECK,
            name="ck_concept_sets_active_validity",
        ),
        sa.CheckConstraint(_REVIEW_STATUS_CHECK, name="ck_concept_sets_review_status"),
        sa.CheckConstraint(
            "length(trim(slug)) > 0",
            name="ck_concept_sets_slug_non_empty",
        ),
    )
    op.create_index(
        "idx_concept_sets_space_created_at",
        "concept_sets",
        ["research_space_id", "created_at"],
    )
    op.create_index(
        "idx_concept_sets_space_active",
        "concept_sets",
        ["research_space_id", "is_active"],
    )


def _create_concept_members() -> None:
    op.create_table(
        "concept_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("concept_set_id", sa.UUID(), nullable=False),
        sa.Column("research_space_id", sa.UUID(), nullable=False),
        sa.Column("domain_context", sa.String(length=64), nullable=False),
        sa.Column("dictionary_dimension", sa.String(length=32), nullable=True),
        sa.Column("dictionary_entry_id", sa.String(length=128), nullable=True),
        sa.Column("canonical_label", sa.String(length=255), nullable=False),
        sa.Column("normalized_label", sa.String(length=255), nullable=False),
        sa.Column(
            "sense_key",
            sa.String(length=128),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "is_provisional",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("metadata_payload", JSONB, nullable=False, server_default="{}"),
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
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "valid_from",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("valid_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.UUID(), nullable=True),
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
            ["concept_set_id"],
            ["concept_sets.id"],
            name="fk_concept_members_concept_set_id_concept_sets",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_space_id"],
            ["research_spaces.id"],
            name="fk_concept_members_research_space_id_research_spaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["domain_context"],
            ["dictionary_domain_contexts.id"],
            name="fk_concept_members_domain_context_dictionary_domain_contexts",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by"],
            ["concept_members.id"],
            name="fk_concept_members_superseded_by_concept_members",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["concept_set_id", "research_space_id"],
            ["concept_sets.id", "concept_sets.research_space_id"],
            name="fk_concept_members_set_space_concept_sets",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_concept_members"),
        sa.UniqueConstraint(
            "id",
            "research_space_id",
            name="uq_concept_members_id_space",
        ),
        sa.CheckConstraint(
            _ACTIVE_VALIDITY_CHECK,
            name="ck_concept_members_active_validity",
        ),
        sa.CheckConstraint(
            _REVIEW_STATUS_CHECK,
            name="ck_concept_members_review_status",
        ),
        sa.CheckConstraint(
            "((dictionary_dimension IS NULL AND dictionary_entry_id IS NULL) OR "
            "(dictionary_dimension IS NOT NULL AND dictionary_entry_id IS NOT NULL))",
            name="ck_concept_members_dictionary_binding",
        ),
        sa.CheckConstraint(
            "((NOT is_provisional) OR review_status = 'PENDING_REVIEW')",
            name="ck_concept_members_provisional_review_status",
        ),
    )
    op.create_index(
        "idx_concept_members_set_active",
        "concept_members",
        ["concept_set_id", "is_active"],
    )
    op.create_index(
        "idx_concept_members_space_domain",
        "concept_members",
        ["research_space_id", "domain_context"],
    )


def _create_concept_aliases() -> None:
    op.create_table(
        "concept_aliases",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("concept_member_id", sa.UUID(), nullable=False),
        sa.Column("research_space_id", sa.UUID(), nullable=False),
        sa.Column("domain_context", sa.String(length=64), nullable=False),
        sa.Column("alias_label", sa.String(length=255), nullable=False),
        sa.Column("alias_normalized", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
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
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "valid_from",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("valid_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.Integer(), nullable=True),
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
            ["concept_member_id"],
            ["concept_members.id"],
            name="fk_concept_aliases_concept_member_id_concept_members",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_space_id"],
            ["research_spaces.id"],
            name="fk_concept_aliases_research_space_id_research_spaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["domain_context"],
            ["dictionary_domain_contexts.id"],
            name="fk_concept_aliases_domain_context_dictionary_domain_contexts",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by"],
            ["concept_aliases.id"],
            name="fk_concept_aliases_superseded_by_concept_aliases",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["concept_member_id", "research_space_id"],
            ["concept_members.id", "concept_members.research_space_id"],
            name="fk_concept_aliases_member_space_concept_members",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_concept_aliases"),
        sa.CheckConstraint(
            _ACTIVE_VALIDITY_CHECK,
            name="ck_concept_aliases_active_validity",
        ),
        sa.CheckConstraint(
            _REVIEW_STATUS_CHECK,
            name="ck_concept_aliases_review_status",
        ),
    )
    op.create_index(
        "idx_concept_aliases_member_active",
        "concept_aliases",
        ["concept_member_id", "is_active"],
    )
    op.create_index(
        "idx_concept_aliases_space_domain",
        "concept_aliases",
        ["research_space_id", "domain_context"],
    )


def _create_concept_links() -> None:
    op.create_table(
        "concept_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("research_space_id", sa.UUID(), nullable=False),
        sa.Column("source_member_id", sa.UUID(), nullable=False),
        sa.Column("target_member_id", sa.UUID(), nullable=False),
        sa.Column("link_type", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("metadata_payload", JSONB, nullable=False, server_default="{}"),
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
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "valid_from",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("valid_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.UUID(), nullable=True),
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
            ["research_space_id"],
            ["research_spaces.id"],
            name="fk_concept_links_research_space_id_research_spaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_member_id"],
            ["concept_members.id"],
            name="fk_concept_links_source_member_id_concept_members",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_member_id"],
            ["concept_members.id"],
            name="fk_concept_links_target_member_id_concept_members",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_member_id", "research_space_id"],
            ["concept_members.id", "concept_members.research_space_id"],
            name="fk_concept_links_source_member_space_concept_members",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_member_id", "research_space_id"],
            ["concept_members.id", "concept_members.research_space_id"],
            name="fk_concept_links_target_member_space_concept_members",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by"],
            ["concept_links.id"],
            name="fk_concept_links_superseded_by_concept_links",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_concept_links"),
        sa.UniqueConstraint(
            "id",
            "research_space_id",
            name="uq_concept_links_id_space",
        ),
        sa.CheckConstraint(
            _ACTIVE_VALIDITY_CHECK,
            name="ck_concept_links_active_validity",
        ),
        sa.CheckConstraint(_REVIEW_STATUS_CHECK, name="ck_concept_links_review_status"),
        sa.CheckConstraint(
            "source_member_id <> target_member_id",
            name="ck_concept_links_no_self_loop",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_concept_links_confidence_bounds",
        ),
    )
    op.create_index(
        "idx_concept_links_space_type",
        "concept_links",
        ["research_space_id", "link_type"],
    )
    op.create_index(
        "idx_concept_links_source_target",
        "concept_links",
        ["source_member_id", "target_member_id"],
    )


def _create_concept_policies() -> None:
    op.create_table(
        "concept_policies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("research_space_id", sa.UUID(), nullable=False),
        sa.Column(
            "profile_name",
            sa.String(length=64),
            nullable=False,
            server_default="default",
        ),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column(
            "minimum_edge_confidence",
            sa.Float(),
            nullable=False,
            server_default="0.6",
        ),
        sa.Column(
            "minimum_distinct_documents",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "allow_generic_relations",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("max_edges_per_document", sa.Integer(), nullable=True),
        sa.Column("policy_payload", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_by",
            sa.String(length=128),
            nullable=False,
            server_default="seed",
        ),
        sa.Column("source_ref", sa.String(length=1024), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
            ["research_space_id"],
            ["research_spaces.id"],
            name="fk_concept_policies_research_space_id_research_spaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_concept_policies"),
        sa.UniqueConstraint(
            "research_space_id",
            "profile_name",
            name="uq_concept_policies_space_profile_name",
        ),
        sa.CheckConstraint(
            "mode IN ('PRECISION', 'BALANCED', 'DISCOVERY')",
            name="ck_concept_policies_mode",
        ),
        sa.CheckConstraint(
            "minimum_edge_confidence >= 0.0 AND minimum_edge_confidence <= 1.0",
            name="ck_concept_policies_minimum_edge_confidence",
        ),
        sa.CheckConstraint(
            "minimum_distinct_documents >= 1",
            name="ck_concept_policies_minimum_distinct_documents",
        ),
        sa.CheckConstraint(
            "(max_edges_per_document IS NULL OR max_edges_per_document >= 1)",
            name="ck_concept_policies_max_edges_per_document",
        ),
    )
    op.create_index(
        "idx_concept_policies_space_created_at",
        "concept_policies",
        ["research_space_id", "created_at"],
    )


def _create_concept_decisions() -> None:
    op.create_table(
        "concept_decisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("research_space_id", sa.UUID(), nullable=False),
        sa.Column("concept_set_id", sa.UUID(), nullable=True),
        sa.Column("concept_member_id", sa.UUID(), nullable=True),
        sa.Column("concept_link_id", sa.UUID(), nullable=True),
        sa.Column("decision_type", sa.String(length=32), nullable=False),
        sa.Column("decision_status", sa.String(length=32), nullable=False),
        sa.Column("proposed_by", sa.String(length=128), nullable=False),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("evidence_payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("decision_payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("harness_outcome", sa.String(length=32), nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
            ["research_space_id"],
            ["research_spaces.id"],
            name="fk_concept_decisions_research_space_id_research_spaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concept_set_id"],
            ["concept_sets.id"],
            name="fk_concept_decisions_concept_set_id_concept_sets",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["concept_member_id"],
            ["concept_members.id"],
            name="fk_concept_decisions_concept_member_id_concept_members",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["concept_link_id"],
            ["concept_links.id"],
            name="fk_concept_decisions_concept_link_id_concept_links",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["concept_set_id", "research_space_id"],
            ["concept_sets.id", "concept_sets.research_space_id"],
            name="fk_concept_decisions_set_space_concept_sets",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["concept_member_id", "research_space_id"],
            ["concept_members.id", "concept_members.research_space_id"],
            name="fk_concept_decisions_member_space_concept_members",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["concept_link_id", "research_space_id"],
            ["concept_links.id", "concept_links.research_space_id"],
            name="fk_concept_decisions_link_space_concept_links",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_concept_decisions"),
        sa.UniqueConstraint(
            "id",
            "research_space_id",
            name="uq_concept_decisions_id_space",
        ),
        sa.CheckConstraint(
            "decision_type IN ('CREATE', 'MAP', 'MERGE', 'SPLIT', 'LINK', 'PROMOTE', 'DEMOTE')",
            name="ck_concept_decisions_decision_type",
        ),
        sa.CheckConstraint(
            "decision_status IN ('PROPOSED', 'NEEDS_REVIEW', 'APPROVED', 'REJECTED', 'APPLIED')",
            name="ck_concept_decisions_decision_status",
        ),
        sa.CheckConstraint(
            "(harness_outcome IS NULL OR harness_outcome IN ('PASS', 'FAIL', 'NEEDS_REVIEW'))",
            name="ck_concept_decisions_harness_outcome",
        ),
        sa.CheckConstraint(
            "(confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0))",
            name="ck_concept_decisions_confidence_bounds",
        ),
        sa.CheckConstraint(
            "(concept_set_id IS NOT NULL OR concept_member_id IS NOT NULL OR concept_link_id IS NOT NULL)",
            name="ck_concept_decisions_subject_present",
        ),
    )
    op.create_index(
        "idx_concept_decisions_space_status",
        "concept_decisions",
        ["research_space_id", "decision_status"],
    )
    op.create_index(
        "idx_concept_decisions_space_created_at",
        "concept_decisions",
        ["research_space_id", "created_at"],
    )


def _create_concept_harness_results() -> None:
    op.create_table(
        "concept_harness_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("research_space_id", sa.UUID(), nullable=False),
        sa.Column("decision_id", sa.UUID(), nullable=True),
        sa.Column("harness_name", sa.String(length=64), nullable=False),
        sa.Column("harness_version", sa.String(length=32), nullable=True),
        sa.Column("run_id", sa.String(length=255), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("checks_payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("errors_payload", JSONB, nullable=False, server_default="[]"),
        sa.Column("metadata_payload", JSONB, nullable=False, server_default="{}"),
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
            ["research_space_id"],
            ["research_spaces.id"],
            name="fk_concept_harness_results_research_space_id_research_spaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["concept_decisions.id"],
            name="fk_concept_harness_results_decision_id_concept_decisions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id", "research_space_id"],
            ["concept_decisions.id", "concept_decisions.research_space_id"],
            name="fk_concept_harness_results_decision_space_concept_decisions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_concept_harness_results"),
        sa.CheckConstraint(
            "outcome IN ('PASS', 'FAIL', 'NEEDS_REVIEW')",
            name="ck_concept_harness_results_outcome",
        ),
    )
    op.create_index(
        "idx_concept_harness_results_space_outcome",
        "concept_harness_results",
        ["research_space_id", "outcome"],
    )
    op.create_index(
        "idx_concept_harness_results_decision_id",
        "concept_harness_results",
        ["decision_id"],
    )


def _create_partial_indexes() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            "uq_concept_members_active_dictionary_binding",
            "concept_members",
            ["research_space_id", "dictionary_dimension", "dictionary_entry_id"],
            unique=True,
            postgresql_where=sa.text("is_active AND dictionary_entry_id IS NOT NULL"),
        )
        op.create_index(
            "uq_concept_members_active_provisional_identity",
            "concept_members",
            ["research_space_id", "domain_context", "normalized_label", "sense_key"],
            unique=True,
            postgresql_where=sa.text("is_active AND dictionary_entry_id IS NULL"),
        )
        op.create_index(
            "uq_concept_aliases_active_alias_scope",
            "concept_aliases",
            ["research_space_id", "domain_context", "alias_normalized"],
            unique=True,
            postgresql_where=sa.text("is_active"),
        )
        op.create_index(
            "uq_concept_links_active_unique_edge",
            "concept_links",
            ["research_space_id", "source_member_id", "link_type", "target_member_id"],
            unique=True,
            postgresql_where=sa.text("is_active"),
        )
        op.create_index(
            "uq_concept_policies_active_space",
            "concept_policies",
            ["research_space_id"],
            unique=True,
            postgresql_where=sa.text("is_active"),
        )
        return

    op.create_index(
        "uq_concept_members_active_dictionary_binding",
        "concept_members",
        ["research_space_id", "dictionary_dimension", "dictionary_entry_id"],
        unique=True,
    )
    op.create_index(
        "uq_concept_members_active_provisional_identity",
        "concept_members",
        ["research_space_id", "domain_context", "normalized_label", "sense_key"],
        unique=True,
    )
    op.create_index(
        "uq_concept_aliases_active_alias_scope",
        "concept_aliases",
        ["research_space_id", "domain_context", "alias_normalized"],
        unique=True,
    )
    op.create_index(
        "uq_concept_links_active_unique_edge",
        "concept_links",
        ["research_space_id", "source_member_id", "link_type", "target_member_id"],
        unique=True,
    )
    op.create_index(
        "uq_concept_policies_active_space",
        "concept_policies",
        ["research_space_id"],
        unique=True,
    )
