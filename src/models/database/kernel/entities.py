"""
Entity models — the graph nodes.

Replaces the old GeneModel, VariantModel, PhenotypeModel, etc.
with a single generic entity table + identifier isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.database.base import Base
from src.type_definitions.common import JSONObject  # noqa: TC001


class EntityModel(Base):
    """
    A generic graph node.

    Represents any typed entity: GENE, VARIANT, PHENOTYPE, DRUG,
    PATHWAY, MECHANISM, PUBLICATION, PATIENT, etc.

    No PHI or high-volume data lives here — only stable metadata.
    """

    __tablename__ = "entities"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Unique entity identifier",
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_spaces.id", ondelete="CASCADE"),
        nullable=False,
        doc="Owning research space",
    )
    entity_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        doc="Entity type, e.g. GENE, VARIANT, PATIENT",
    )
    display_label: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        doc="Human-readable label",
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        doc="Sparse, low-velocity metadata only",
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
        Index("idx_entities_space_type", "research_space_id", "entity_type"),
        Index("idx_entities_created_at", "created_at"),
        {"comment": "Generic graph nodes (entities) for all domain types"},
    )

    def __repr__(self) -> str:
        return (
            f"<EntityModel(id={self.id}, type={self.entity_type}, "
            f"label={self.display_label})>"
        )


class EntityIdentifierModel(Base):
    """
    Entity identifiers — isolated for PHI protection.

    Stores lookup keys (MRN, HGNC, DOI, HPO ID, etc.) separately
    from the entity itself. PHI identifiers are encrypted at rest
    and protected by RLS.
    """

    __tablename__ = "entity_identifiers"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        doc="Owning entity",
    )
    namespace: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Identifier namespace: MRN, HGNC, DOI, HPOID",
    )
    identifier_value: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        doc="Identifier value (encrypted if PHI)",
    )
    identifier_blind_index: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Deterministic blind index for encrypted PHI equality lookup",
    )
    encryption_key_version: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        doc="Key version used to encrypt identifier_value",
    )
    blind_index_version: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        doc="Key version used to generate identifier_blind_index",
    )
    sensitivity: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="INTERNAL",
        doc="Sensitivity level: PUBLIC, INTERNAL, PHI",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index(
            "idx_identifier_lookup",
            "namespace",
            "identifier_value",
        ),
        Index(
            "idx_identifier_blind_lookup",
            "namespace",
            "identifier_blind_index",
        ),
        Index(
            "idx_identifier_entity_ns_unique",
            "entity_id",
            "namespace",
            "identifier_value",
            unique=True,
        ),
        Index(
            "idx_identifier_entity_ns_blind_unique",
            "entity_id",
            "namespace",
            "identifier_blind_index",
            unique=True,
        ),
        {"comment": "PHI-isolated entity identifiers for secure lookup"},
    )

    def __repr__(self) -> str:
        return (
            f"<EntityIdentifierModel(entity={self.entity_id}, "
            f"ns={self.namespace}, val={self.identifier_value})>"
        )
