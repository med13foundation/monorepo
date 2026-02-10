"""
Relation model — the graph edges.

Replaces old EvidenceModel and implicit relationships between
entity-specific models. Every edge is now:
  source (entity) --[relation_type]--> target (entity)
with evidence, curation status, and provenance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.database.base import Base


class RelationModel(Base):
    """
    A graph edge with evidence and curation lifecycle.

    Represents typed relationships between any two entities:
      GENE --ASSOCIATED_WITH--> PHENOTYPE
      PUBLICATION --SUPPORTS--> VARIANT
      DRUG --TARGETS--> PATHWAY
    """

    __tablename__ = "relations"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Unique relation ID",
    )
    study_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("studies.id", ondelete="CASCADE"),
        nullable=False,
        doc="Owning study",
    )
    source_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        doc="Source entity",
    )
    relation_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Relationship type, e.g. CAUSES, ASSOCIATED_WITH",
    )
    target_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        doc="Target entity",
    )

    # Evidence metadata
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.5",
        doc="Confidence score 0.0-1.0",
    )
    evidence_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable evidence summary",
    )
    evidence_tier: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        doc="COMPUTATIONAL, LITERATURE, EXPERIMENTAL, CLINICAL, EXPERT_CURATED",
    )

    # Curation lifecycle
    curation_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="DRAFT",
        doc="DRAFT, UNDER_REVIEW, APPROVED, REJECTED, RETRACTED",
    )

    # Provenance
    provenance_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("provenance.id"),
        nullable=True,
        doc="Link to ingestion provenance",
    )

    # Review tracking
    reviewed_by: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_relations_source", "source_id"),
        Index("idx_relations_target", "target_id"),
        Index("idx_relations_study_type", "study_id", "relation_type"),
        Index("idx_relations_curation", "curation_status"),
        Index("idx_relations_provenance", "provenance_id"),
        {"comment": "Graph edges with evidence and curation lifecycle"},
    )

    def __repr__(self) -> str:
        return (
            f"<RelationModel(src={self.source_id}, "
            f"rel={self.relation_type}, tgt={self.target_id})>"
        )
