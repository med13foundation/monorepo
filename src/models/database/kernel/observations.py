"""
Observation model — typed facts (EAV with strict typing).

Replaces ad-hoc JSONB columns on old entity models (e.g. variant
structural annotations, phenotype longitudinal data) with a
properly typed, dictionary-validated observation table.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Float, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.database.base import Base


class ObservationModel(Base):
    """
    A typed observation — the core fact table.

    Each row represents a single measured/observed value for a
    specific variable on a specific entity at a point in time.

    Only one value column is populated per row, determined by the
    variable_definition's data_type.
    """

    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Unique observation ID",
    )
    study_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("studies.id", ondelete="CASCADE"),
        nullable=False,
        doc="Owning study",
    )
    subject_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        doc="Entity this observation belongs to",
    )
    variable_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("variable_definitions.id"),
        nullable=False,
        doc="What was measured, FK to dictionary",
    )

    # Typed value columns — only one is populated per row
    value_numeric: Mapped[float | None] = mapped_column(
        Numeric,
        nullable=True,
        doc="Numeric value (INTEGER, FLOAT)",
    )
    value_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Free-text value (STRING)",
    )
    value_date: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        doc="Date/timestamp value (DATE)",
    )
    value_coded: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Ontology code, e.g. HP:0001250 (CODED)",
    )
    value_json: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Complex structured value (JSON)",
    )

    # Context
    unit: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Normalised unit after transform",
    )
    observed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        doc="When the observation was recorded",
    )

    # Provenance and confidence
    provenance_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("provenance.id"),
        nullable=True,
        doc="Extraction/ingestion provenance chain",
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="1.0",
        doc="Confidence score 0.0-1.0",
    )

    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_obs_subject", "subject_id"),
        Index("idx_obs_study_variable", "study_id", "variable_id"),
        Index("idx_obs_subject_time", "subject_id", "observed_at"),
        Index("idx_obs_provenance", "provenance_id"),
        {"comment": "Typed observations (EAV with dictionary validation)"},
    )

    def __repr__(self) -> str:
        return f"<ObservationModel(subject={self.subject_id}, var={self.variable_id})>"
