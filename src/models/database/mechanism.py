"""
Mechanism SQLAlchemy model for MED13 Resource Library.
Database representation of mechanistic nodes with phenotype links.
"""

from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Column,
    Float,
    ForeignKey,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.type_definitions.common import JSONObject  # noqa: TC001

from .base import Base

if TYPE_CHECKING:
    from .phenotype import PhenotypeModel
    from .research_space import ResearchSpaceModel


mechanism_phenotypes = Table(
    "mechanism_phenotypes",
    Base.metadata,
    Column(
        "mechanism_id",
        ForeignKey("mechanisms.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "phenotype_id",
        ForeignKey("phenotypes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class MechanismModel(Base):
    """
    SQLAlchemy Mechanism model with mechanistic metadata and phenotype links.
    """

    __tablename__ = "mechanisms"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    research_space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("research_spaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_tier: Mapped[str] = mapped_column(
        String(20),
        default="supporting",
        nullable=False,
    )
    lifecycle_state: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        nullable=False,
    )
    confidence_score: Mapped[float] = mapped_column(
        Float,
        default=0.5,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(100),
        default="manual_curation",
        nullable=False,
    )

    protein_domains: Mapped[list[JSONObject]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    phenotypes: Mapped[list["PhenotypeModel"]] = relationship(
        secondary=mechanism_phenotypes,
        back_populates="mechanisms",
    )
    research_space: Mapped["ResearchSpaceModel"] = relationship(
        "ResearchSpaceModel",
        back_populates="mechanisms",
    )

    __table_args__ = (
        UniqueConstraint(
            "research_space_id",
            "name",
            name="uq_mechanisms_space_name",
        ),
        {"sqlite_autoincrement": True},
    )  # noqa: RUF012


__all__ = ["MechanismModel", "mechanism_phenotypes"]
