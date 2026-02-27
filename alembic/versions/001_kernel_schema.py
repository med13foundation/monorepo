"""
001_kernel_schema — Clean-sheet database for Universal Study Graph Platform.

Replaces all 27 previous domain-specific migrations with a single
metadata-driven kernel schema.

Revision ID: 001_kernel_schema
Create Date: 2026-02-09
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "001_kernel_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:  # noqa: PLR0915
    # ── Users (surviving table, re-created clean) ──
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("username", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("ADMIN", "RESEARCHER", "CURATOR", "VIEWER", name="userrole"),
            nullable=False,
            server_default="VIEWER",
        ),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "PENDING_VERIFICATION",
                "SUSPENDED",
                "DEACTIVATED",
                name="userstatus",
            ),
            nullable=False,
            server_default="PENDING_VERIFICATION",
        ),
        sa.Column("email_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("email_verification_token", sa.String(255), nullable=True),
        sa.Column("password_reset_token", sa.String(255), nullable=True),
        sa.Column(
            "password_reset_expires",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column("last_login", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("login_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.TIMESTAMP(timezone=True), nullable=True),
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
    )
    op.create_index("idx_users_email_active", "users", ["email", "status"])
    op.create_index("idx_users_role_status", "users", ["role", "status"])
    op.create_index("idx_users_created_at", "users", ["created_at"])

    # ── Sessions (surviving table) ──
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("session_token", sa.Text, nullable=False),
        sa.Column("refresh_token", sa.Text, nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("device_fingerprint", sa.String(32), nullable=True),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "EXPIRED", "REVOKED", "SUSPENDED", name="sessionstatus"),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_activity",
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
    )
    op.create_index("idx_sessions_user_status", "sessions", ["user_id", "status"])
    op.create_index("idx_sessions_expires_at", "sessions", ["expires_at"])

    # ── Audit Logs (surviving table) ──
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("action", sa.String(64), index=True),
        sa.Column("entity_type", sa.String(50), index=True),
        sa.Column("entity_id", sa.String(128), index=True),
        sa.Column("user", sa.String(128), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True, index=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("success", sa.Boolean, nullable=True),
        sa.Column("details", sa.Text, nullable=True),
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
    )

    # ── System Status (surviving table) ──
    op.create_table(
        "system_status",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.JSON, nullable=False, server_default="{}"),
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
            onupdate=sa.func.now(),
        ),
    )

    # ══════════════════════════════════════════════════════════════
    # KERNEL LAYER 1: DICTIONARY TABLES (The Rules)
    # ══════════════════════════════════════════════════════════════

    op.create_table(
        "variable_definitions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("canonical_name", sa.String(128), unique=True, nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("data_type", sa.String(32), nullable=False),
        sa.Column("preferred_unit", sa.String(64), nullable=True),
        sa.Column("constraints", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "domain_context",
            sa.String(64),
            nullable=False,
            server_default="general",
            index=True,
        ),
        sa.Column(
            "sensitivity",
            sa.String(32),
            nullable=False,
            server_default="INTERNAL",
        ),
        sa.Column("description", sa.Text, nullable=True),
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
    )
    op.create_index("idx_vardef_data_type", "variable_definitions", ["data_type"])

    op.create_table(
        "variable_synonyms",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "variable_id",
            sa.String(64),
            sa.ForeignKey("variable_definitions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("synonym", sa.String(255), nullable=False),
        sa.Column("source", sa.String(64), nullable=True),
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
    )
    op.create_index(
        "idx_synonym_variable_unique",
        "variable_synonyms",
        ["variable_id", "synonym"],
        unique=True,
    )

    op.create_table(
        "transform_registry",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("input_unit", sa.String(64), nullable=False),
        sa.Column("output_unit", sa.String(64), nullable=False),
        sa.Column("implementation_ref", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
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
    )
    op.create_index(
        "idx_transform_units",
        "transform_registry",
        ["input_unit", "output_unit"],
    )

    op.create_table(
        "entity_resolution_policies",
        sa.Column("entity_type", sa.String(64), primary_key=True),
        sa.Column("policy_strategy", sa.String(32), nullable=False),
        sa.Column(
            "required_anchors",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "auto_merge_threshold",
            sa.Float,
            nullable=False,
            server_default="1.0",
        ),
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
    )

    op.create_table(
        "relation_constraints",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("relation_type", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("is_allowed", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "requires_evidence",
            sa.Boolean,
            nullable=False,
            server_default="true",
        ),
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
    )
    op.create_index(
        "idx_relation_constraint_unique",
        "relation_constraints",
        ["source_type", "relation_type", "target_type"],
        unique=True,
    )

    # ══════════════════════════════════════════════════════════════
    # KERNEL LAYER 2: DATA TABLES (The Facts)
    # ══════════════════════════════════════════════════════════════

    op.create_table(
        "research_spaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "inactive",
                "archived",
                "suspended",
                name="spacestatusenum",
            ),
            nullable=False,
            server_default="active",
            index=True,
        ),
        sa.Column("settings", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default="[]"),
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
    )
    op.create_index("idx_research_spaces_owner", "research_spaces", ["owner_id"])
    op.create_index("idx_research_spaces_status", "research_spaces", ["status"])
    op.create_index("idx_research_spaces_created_at", "research_spaces", ["created_at"])

    op.create_table(
        "research_space_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum(
                "owner",
                "admin",
                "curator",
                "researcher",
                "viewer",
                name="membershiproleenum",
            ),
            nullable=False,
            server_default="viewer",
        ),
        sa.Column(
            "invited_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("invited_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("joined_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
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
    )
    op.create_index(
        "idx_memberships_space",
        "research_space_memberships",
        ["space_id"],
    )
    op.create_index(
        "idx_memberships_user",
        "research_space_memberships",
        ["user_id"],
    )
    op.create_index(
        "idx_memberships_space_user",
        "research_space_memberships",
        ["space_id", "user_id"],
        unique=True,
    )
    op.create_index(
        "idx_memberships_invited_by",
        "research_space_memberships",
        ["invited_by"],
    )
    op.create_index(
        "idx_memberships_pending",
        "research_space_memberships",
        ["user_id", "invited_at", "joined_at"],
    )

    # ── Entities (graph nodes) ──
    op.create_table(
        "entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "research_space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(64), nullable=False, index=True),
        sa.Column("display_label", sa.String(512), nullable=True),
        sa.Column(
            "metadata_payload",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
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
    )
    op.create_index(
        "idx_entities_space_type",
        "entities",
        ["research_space_id", "entity_type"],
    )
    op.create_index("idx_entities_created_at", "entities", ["created_at"])

    # ── Entity identifiers (PHI-isolated) ──
    op.create_table(
        "entity_identifiers",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("namespace", sa.String(64), nullable=False),
        sa.Column("identifier_value", sa.String(512), nullable=False),
        sa.Column(
            "sensitivity",
            sa.String(32),
            nullable=False,
            server_default="INTERNAL",
        ),
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
    )
    op.create_index(
        "idx_identifier_lookup",
        "entity_identifiers",
        ["namespace", "identifier_value"],
    )
    op.create_index(
        "idx_identifier_entity_ns_unique",
        "entity_identifiers",
        ["entity_id", "namespace", "identifier_value"],
        unique=True,
    )

    # ── Provenance (must exist before observations/relations reference it) ──
    op.create_table(
        "provenance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "research_space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_ref", sa.String(1024), nullable=True),
        sa.Column("extraction_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mapping_method", sa.String(64), nullable=True),
        sa.Column("mapping_confidence", sa.Float, nullable=True),
        sa.Column("agent_model", sa.String(128), nullable=True),
        sa.Column("raw_input", postgresql.JSONB, nullable=True),
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
    )
    op.create_index("idx_provenance_space", "provenance", ["research_space_id"])
    op.create_index("idx_provenance_source_type", "provenance", ["source_type"])
    op.create_index("idx_provenance_extraction", "provenance", ["extraction_run_id"])

    # ── Observations (typed facts) ──
    op.create_table(
        "observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "research_space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "variable_id",
            sa.String(64),
            sa.ForeignKey("variable_definitions.id"),
            nullable=False,
        ),
        sa.Column("value_numeric", sa.Numeric, nullable=True),
        sa.Column("value_text", sa.Text, nullable=True),
        sa.Column("value_date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("value_coded", sa.String(255), nullable=True),
        sa.Column("value_boolean", sa.Boolean, nullable=True),
        sa.Column("value_json", postgresql.JSONB, nullable=True),
        sa.Column("unit", sa.String(64), nullable=True),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "provenance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("provenance.id"),
            nullable=True,
        ),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
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
        sa.CheckConstraint(
            (
                "(CASE WHEN value_numeric IS NOT NULL THEN 1 ELSE 0 END + "
                "CASE WHEN value_text IS NOT NULL THEN 1 ELSE 0 END + "
                "CASE WHEN value_date IS NOT NULL THEN 1 ELSE 0 END + "
                "CASE WHEN value_coded IS NOT NULL THEN 1 ELSE 0 END + "
                "CASE WHEN value_boolean IS NOT NULL THEN 1 ELSE 0 END + "
                "CASE WHEN value_json IS NOT NULL THEN 1 ELSE 0 END) = 1"
            ),
            name="ck_observations_exactly_one_value",
        ),
    )
    op.create_index("idx_obs_subject", "observations", ["subject_id"])
    op.create_index(
        "idx_obs_space_variable",
        "observations",
        ["research_space_id", "variable_id"],
    )
    op.create_index(
        "idx_obs_subject_time",
        "observations",
        ["subject_id", "observed_at"],
    )
    op.create_index("idx_obs_provenance", "observations", ["provenance_id"])

    # ── Relations (graph edges) ──
    op.create_table(
        "relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "research_space_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(64), nullable=False),
        sa.Column(
            "target_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("evidence_summary", sa.Text, nullable=True),
        sa.Column("evidence_tier", sa.String(32), nullable=True),
        sa.Column(
            "curation_status",
            sa.String(32),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column(
            "provenance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("provenance.id"),
            nullable=True,
        ),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
    )
    op.create_index("idx_relations_source", "relations", ["source_id"])
    op.create_index("idx_relations_target", "relations", ["target_id"])
    op.create_index(
        "idx_relations_space_type",
        "relations",
        ["research_space_id", "relation_type"],
    )
    op.create_index("idx_relations_curation", "relations", ["curation_status"])
    op.create_index("idx_relations_provenance", "relations", ["provenance_id"])

    # ══════════════════════════════════════════════════════════════
    # SURVIVING INFRASTRUCTURE TABLES
    # ══════════════════════════════════════════════════════════════

    # ── Source Templates ──
    op.create_table(
        "source_templates",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=False),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "category",
            sa.Enum(
                "clinical",
                "research",
                "literature",
                "genomic",
                "phenotypic",
                "ontology",
                "other",
                name="templatecategoryenum",
            ),
            nullable=False,
            server_default="other",
            index=True,
        ),
        sa.Column(
            "source_type",
            sa.Enum(
                "file_upload",
                "api",
                "database",
                "web_scraping",
                name="sourcetypeenum",
            ),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "schema_definition",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "validation_rules",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column("ui_config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_approved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "approval_required",
            sa.Boolean,
            nullable=False,
            server_default="true",
        ),
        sa.Column("usage_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("success_rate", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("approved_at", sa.String(30), nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("version", sa.String(20), nullable=False, server_default="1.0"),
        sa.Column(
            "compatibility_version",
            sa.String(20),
            nullable=False,
            server_default="1.0",
        ),
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
    )

    # ── Source Catalog Entries (Data Discovery) ──
    op.create_table(
        "source_catalog_entries",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("category", sa.String(100), nullable=False, index=True),
        sa.Column("subcategory", sa.String(100), nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "source_type",
            sa.String(50),
            nullable=False,
            server_default="api",
        ),
        sa.Column("param_type", sa.String(50), nullable=False, index=True),
        sa.Column("url_template", sa.Text, nullable=True),
        sa.Column("data_format", sa.String(50), nullable=True),
        sa.Column("api_endpoint", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "requires_auth",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
        sa.Column("usage_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("success_rate", sa.Float, nullable=False, server_default="0.0"),
        sa.Column(
            "query_capabilities",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "source_template_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("source_templates.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
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
    )

    # ── Data Source Activation Rules ──
    op.create_table(
        "data_source_activation_rules",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "catalog_entry_id",
            sa.String(100),
            sa.ForeignKey("source_catalog_entries.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "scope",
            sa.Enum(
                "global",
                "research_space",
                name="activationscopeenum",
            ),
            nullable=False,
            server_default="global",
            index=True,
        ),
        sa.Column(
            "research_space_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("research_spaces.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "permission_level",
            sa.Enum(
                "blocked",
                "visible",
                "available",
                name="data_source_permission_level",
            ),
            nullable=False,
            server_default="available",
            index=True,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
        sa.UniqueConstraint(
            "catalog_entry_id",
            "scope",
            "research_space_id",
            name="uq_data_source_activation_scope",
        ),
    )

    # ── Data Discovery Sessions ──
    op.create_table(
        "data_discovery_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), nullable=False, index=True),
        sa.Column(
            "research_space_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("research_spaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "name",
            sa.String(200),
            nullable=False,
            server_default="Untitled Session",
        ),
        sa.Column("gene_symbol", sa.String(100), nullable=True),
        sa.Column("search_term", sa.Text, nullable=True),
        sa.Column(
            "selected_sources",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "tested_sources",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "pubmed_search_config",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column("total_tests_run", sa.Integer, nullable=False, server_default="0"),
        sa.Column("successful_tests", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
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
        sa.Column(
            "last_activity_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── Query Test Results ──
    op.create_table(
        "query_test_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("data_discovery_sessions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "catalog_entry_id",
            sa.String(100),
            sa.ForeignKey("source_catalog_entries.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("status", sa.String(50), nullable=False, index=True),
        sa.Column("gene_symbol", sa.String(100), nullable=True),
        sa.Column("search_term", sa.Text, nullable=True),
        sa.Column("response_data", postgresql.JSONB, nullable=True),
        sa.Column("response_url", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "parameters_payload",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column("execution_time_ms", sa.Integer, nullable=True),
        sa.Column("data_quality_score", sa.Float, nullable=True),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
    )

    # ── Discovery Presets ──
    op.create_table(
        "discovery_presets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), nullable=False, index=True),
        sa.Column(
            "scope",
            sa.Enum("user", "space", name="presetscopeenum"),
            nullable=False,
            server_default="user",
        ),
        sa.Column("provider", sa.String(50), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "parameters",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "metadata_payload",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "research_space_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("research_spaces.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
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
    )

    # ── Discovery Search Jobs ──
    op.create_table(
        "discovery_search_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), nullable=False, index=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("data_discovery_sessions.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("provider", sa.String(50), nullable=False, index=True),
        sa.Column("status", sa.String(50), nullable=False, index=True),
        sa.Column("query_preview", sa.Text, nullable=False),
        sa.Column(
            "parameters",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column("total_results", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "result_payload",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("storage_key", sa.String(512), nullable=True),
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
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # ── User Data Sources (space-scoped via research_space_id) ──
    op.create_table(
        "user_data_sources",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "research_space_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("research_spaces.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "source_type",
            sa.Enum(
                "file_upload",
                "api",
                "database",
                "web_scraping",
                "pubmed",
                name="usersourcetypeenum",
            ),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("source_templates.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "configuration",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "active",
                "inactive",
                "error",
                "pending_review",
                "archived",
                name="sourcestatusenum",
            ),
            nullable=False,
            server_default="draft",
            index=True,
        ),
        sa.Column(
            "ingestion_schedule",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "quality_metrics",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column("last_ingested_at", sa.String(30), nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("version", sa.String(20), nullable=False, server_default="1.0"),
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
    )

    # ── Storage Configurations ──
    op.create_table(
        "storage_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column(
            "provider",
            sa.Enum(
                "local_filesystem",
                "google_cloud_storage",
                name="storageproviderenum",
            ),
            nullable=False,
            index=True,
        ),
        sa.Column("config_data", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "supported_capabilities",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "default_use_cases",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "metadata_payload",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
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
    )

    # ── Storage Operations ──
    op.create_table(
        "storage_operations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "configuration_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("storage_configurations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=True, index=True),
        sa.Column(
            "operation_type",
            sa.Enum(
                "store",
                "retrieve",
                "delete",
                "list",
                "test",
                name="storageoperationtypeenum",
            ),
            nullable=False,
            index=True,
        ),
        sa.Column("key", sa.String(512), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "success",
                "failed",
                "pending",
                name="storageoperationstatusenum",
            ),
            nullable=False,
            index=True,
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "metadata_payload",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
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
    )

    # ── Storage Health Snapshots ──
    op.create_table(
        "storage_health_snapshots",
        sa.Column(
            "configuration_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("storage_configurations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "provider",
            sa.Enum(
                "local_filesystem",
                "google_cloud_storage",
                name="storageproviderenum",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("healthy", "degraded", "offline", name="storagehealthstatusenum"),
            nullable=False,
        ),
        sa.Column(
            "last_checked_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("details", postgresql.JSONB, nullable=False, server_default="{}"),
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
    )

    # ── Ingestion Jobs (Data Sources module) ──
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user_data_sources.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "trigger",
            sa.Enum(
                "manual",
                "scheduled",
                "api",
                "webhook",
                "retry",
                name="ingestiontriggerenum",
            ),
            nullable=False,
            server_default="manual",
            index=True,
        ),
        sa.Column(
            "triggered_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("triggered_at", sa.String(30), nullable=False, index=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "failed",
                "cancelled",
                "partial",
                name="ingestionstatusenum",
            ),
            nullable=False,
            server_default="pending",
            index=True,
        ),
        sa.Column("started_at", sa.String(30), nullable=True),
        sa.Column("completed_at", sa.String(30), nullable=True),
        sa.Column("metrics", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("errors", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("provenance", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "job_metadata",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "source_config_snapshot",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
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
    )


def downgrade() -> None:
    # Drop in reverse order of creation
    # NOTE: This migration is iterated on frequently during the clean-sheet pivot.
    # Use IF EXISTS to keep downgrade resilient when schema details change.
    op.execute("DROP TABLE IF EXISTS ingestion_jobs CASCADE")
    op.execute("DROP TABLE IF EXISTS storage_health_snapshots CASCADE")
    op.execute("DROP TABLE IF EXISTS storage_operations CASCADE")
    op.execute("DROP TABLE IF EXISTS storage_configurations CASCADE")
    op.execute("DROP TABLE IF EXISTS user_data_sources CASCADE")
    op.execute("DROP TABLE IF EXISTS discovery_search_jobs CASCADE")
    op.execute("DROP TABLE IF EXISTS discovery_presets CASCADE")
    op.execute("DROP TABLE IF EXISTS query_test_results CASCADE")
    op.execute("DROP TABLE IF EXISTS data_discovery_sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS data_source_activation_rules CASCADE")
    op.execute("DROP TABLE IF EXISTS source_catalog_entries CASCADE")
    op.execute("DROP TABLE IF EXISTS source_templates CASCADE")
    op.execute("DROP TABLE IF EXISTS relations CASCADE")
    op.execute("DROP TABLE IF EXISTS observations CASCADE")
    op.execute("DROP TABLE IF EXISTS provenance CASCADE")
    op.execute("DROP TABLE IF EXISTS entity_identifiers CASCADE")
    op.execute("DROP TABLE IF EXISTS entities CASCADE")
    op.execute("DROP TABLE IF EXISTS research_space_memberships CASCADE")
    op.execute("DROP TABLE IF EXISTS research_spaces CASCADE")
    op.execute("DROP TABLE IF EXISTS relation_constraints CASCADE")
    op.execute("DROP TABLE IF EXISTS entity_resolution_policies CASCADE")
    op.execute("DROP TABLE IF EXISTS transform_registry CASCADE")
    op.execute("DROP TABLE IF EXISTS variable_synonyms CASCADE")
    op.execute("DROP TABLE IF EXISTS variable_definitions CASCADE")
    op.execute("DROP TABLE IF EXISTS system_status CASCADE")
    op.execute("DROP TABLE IF EXISTS audit_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    # Drop enums
    op.execute("DROP TYPE IF EXISTS userrole")
    op.execute("DROP TYPE IF EXISTS userstatus")
    op.execute("DROP TYPE IF EXISTS sessionstatus")
    op.execute("DROP TYPE IF EXISTS membershiproleenum")
    op.execute("DROP TYPE IF EXISTS spacestatusenum")
    op.execute("DROP TYPE IF EXISTS activationscopeenum")
    op.execute("DROP TYPE IF EXISTS data_source_permission_level")
    op.execute("DROP TYPE IF EXISTS presetscopeenum")
    op.execute("DROP TYPE IF EXISTS templatecategoryenum")
    op.execute("DROP TYPE IF EXISTS sourcetypeenum")
    op.execute("DROP TYPE IF EXISTS usersourcetypeenum")
    op.execute("DROP TYPE IF EXISTS sourcestatusenum")
    op.execute("DROP TYPE IF EXISTS storageproviderenum")
    op.execute("DROP TYPE IF EXISTS storageoperationtypeenum")
    op.execute("DROP TYPE IF EXISTS storageoperationstatusenum")
    op.execute("DROP TYPE IF EXISTS storagehealthstatusenum")
    op.execute("DROP TYPE IF EXISTS ingestionstatusenum")
    op.execute("DROP TYPE IF EXISTS ingestiontriggerenum")
