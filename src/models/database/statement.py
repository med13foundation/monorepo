"""
Statement of Understanding SQLAlchemy model for MED13 Resource Library.

Represents hypothesis-stage mechanistic statements with phenotype links.
"""

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Column, Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.type_definitions.common import JSONObject  # noqa: TC001

from .base import Base

if TYPE_CHECKING:
    from .mechanism import MechanismModel
    from .phenotype import PhenotypeModel
    from .research_space import ResearchSpaceModel


statement_phenotypes = Table(
    "statement_phenotypes",
    Base.metadata,
    Column(
        "statement_id",
        ForeignKey("statements.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "phenotype_id",
        ForeignKey("phenotypes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class StatementModel(Base):
    """
    SQLAlchemy Statement model with mechanistic summary and phenotype links.
    """

    __tablename__ = "statements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    research_space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("research_spaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_tier: Mapped[str] = mapped_column(
        String(20),
        default="supporting",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
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
    promoted_mechanism_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("mechanisms.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    phenotypes: Mapped[list["PhenotypeModel"]] = relationship(
        secondary=statement_phenotypes,
        back_populates="statements",
    )
    research_space: Mapped["ResearchSpaceModel"] = relationship(
        "ResearchSpaceModel",
        back_populates="statements",
    )
    promoted_mechanism: Mapped["MechanismModel | None"] = relationship(
        "MechanismModel",
        foreign_keys=[promoted_mechanism_id],
    )

    __table_args__ = {"sqlite_autoincrement": True}  # noqa: RUF012


__all__ = ["StatementModel", "statement_phenotypes"]
