"""
Kernel Dictionary Models — Layer 1 (The Rules).

These tables define what is allowed in the system. No data enters
unless it maps to a definition here.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.database.base import Base
from src.type_definitions.common import JSONObject  # noqa: TC001


class VariableDefinitionModel(Base):
    """
    The Vocabulary — defines every allowed data element.

    Examples: systolic_bp, gene_symbol, algorithm_accuracy
    """

    __tablename__ = "variable_definitions"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        doc="Variable identifier, e.g. VAR_SYSTOLIC_BP",
    )
    canonical_name: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        doc="Snake-case canonical name, e.g. systolic_bp",
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Human-readable display name",
    )
    data_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Data type: INTEGER, FLOAT, STRING, DATE, CODED, BOOLEAN, JSON",
    )
    preferred_unit: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="UCUM-standard preferred unit, e.g. mmHg",
    )
    constraints: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        doc='Validation constraints, e.g. {"min": 0, "max": 300}',
    )
    domain_context: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default="general",
        index=True,
        doc="Domain: clinical, genomics, cs_benchmarking, general",
    )
    sensitivity: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="INTERNAL",
        doc="Sensitivity: PUBLIC, INTERNAL, PHI",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Optional longer description",
    )

    __table_args__ = (
        Index("idx_vardef_domain", "domain_context"),
        Index("idx_vardef_data_type", "data_type"),
        {"comment": "Master dictionary of allowed data variables"},
    )


class VariableSynonymModel(Base):
    """
    Synonym table for fuzzy field-name mapping.

    Allows deterministic mapping before falling back to
    vector or LLM-based mapping.
    """

    __tablename__ = "variable_synonyms"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    variable_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("variable_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="FK to variable_definitions.id",
    )
    synonym: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Alternative name for the variable",
    )
    source: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Source of synonym: manual, ai_mapped",
    )

    __table_args__ = (
        Index(
            "idx_synonym_variable_unique",
            "variable_id",
            "synonym",
            unique=True,
        ),
        {"comment": "Synonyms for deterministic field-name matching"},
    )


class TransformRegistryModel(Base):
    """
    Safe unit/format transformations.

    Each transform references a pre-compiled function — no user-defined
    code is allowed.
    """

    __tablename__ = "transform_registry"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        doc="Transform ID, e.g. TR_LBS_KG",
    )
    input_unit: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Source unit",
    )
    output_unit: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Target unit",
    )
    implementation_ref: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Function reference, e.g. func:std_lib.convert.lbs_to_kg",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ACTIVE",
        doc="ACTIVE or DEPRECATED",
    )

    __table_args__ = (
        Index("idx_transform_units", "input_unit", "output_unit"),
        {"comment": "Registry of safe, pre-compiled unit conversions"},
    )


class EntityResolutionPolicyModel(Base):
    """
    Deduplication policies per entity type.

    Controls how duplicate entities are detected and merged.
    """

    __tablename__ = "entity_resolution_policies"

    entity_type: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        doc="Entity type, e.g. PATIENT, GENE, PAPER",
    )
    policy_strategy: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Strategy: STRICT_MATCH, LOOKUP, FUZZY, NONE",
    )
    required_anchors: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
        doc='Required identifiers for matching, e.g. ["mrn", "issuer"]',
    )
    auto_merge_threshold: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="1.0",
        doc="Similarity threshold for auto-merge (1.0 = exact only)",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = ({"comment": "Entity deduplication policies by type"},)


class RelationConstraintModel(Base):
    """
    Allowed relationship types between entity types.

    Used by the triple validator to block invalid edges.
    """

    __tablename__ = "relation_constraints"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    source_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Source entity type, e.g. GENE",
    )
    relation_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Relation type, e.g. ASSOCIATED_WITH",
    )
    target_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Target entity type, e.g. DISEASE",
    )
    is_allowed: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        doc="Whether this edge type is permitted",
    )
    requires_evidence: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        doc="Whether an evidence reference is mandatory",
    )

    __table_args__ = (
        Index(
            "idx_relation_constraint_unique",
            "source_type",
            "relation_type",
            "target_type",
            unique=True,
        ),
        {"comment": "Allowed triple patterns for graph edges"},
    )
