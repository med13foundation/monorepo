"""Relation claim ledger model."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.database.base import Base
from src.type_definitions.common import JSONObject  # noqa: TC001


class RelationClaimModel(Base):
    """One extracted relation candidate captured for review."""

    __tablename__ = "relation_claims"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_spaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    agent_run_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    target_label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.0",
    )
    validation_state: Mapped[str] = mapped_column(String(32), nullable=False)
    validation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    persistability: Mapped[str] = mapped_column(String(32), nullable=False)
    claim_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="OPEN",
    )
    linked_relation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("relations.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    triaged_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    triaged_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_relation_claims_space", "research_space_id"),
        Index("idx_relation_claims_status", "claim_status"),
        Index("idx_relation_claims_validation_state", "validation_state"),
        Index("idx_relation_claims_persistability", "persistability"),
        Index("idx_relation_claims_source_document_id", "source_document_id"),
        Index("idx_relation_claims_linked_relation_id", "linked_relation_id"),
        Index(
            "idx_relation_claims_space_created_at",
            "research_space_id",
            "created_at",
        ),
        {"comment": "Extracted relation candidate ledger for claim-first curation"},
    )


__all__ = ["RelationClaimModel"]
