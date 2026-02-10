"""
Phenotype SQLAlchemy model for MED13 Resource Library.
Database representation of clinical phenotypes with HPO ontology.
"""

from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .mechanism import mechanism_phenotypes
from .statement import statement_phenotypes

if TYPE_CHECKING:
    from .evidence import EvidenceModel
    from .mechanism import MechanismModel
    from .statement import StatementModel


class PhenotypeCategory(SQLEnum):
    """Phenotype category classification."""

    CONGENITAL = "congenital"
    DEVELOPMENTAL = "developmental"
    NEUROLOGICAL = "neurological"
    CARDIOVASCULAR = "cardiovascular"
    MUSCULOSKELETAL = "musculoskeletal"
    ENDOCRINE = "endocrine"
    IMMUNOLOGICAL = "immunological"
    ONCOLOGICAL = "oncological"
    OTHER = "other"


class PhenotypeModel(Base):
    """
    SQLAlchemy Phenotype model with HPO ontology integration.

    Represents clinical phenotypes in the MED13 knowledge base with
    HPO terms, descriptions, and relationships to genes and variants.
    """

    __tablename__ = "phenotypes"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # HPO identifiers
    hpo_id: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
    )
    hpo_term: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    # Phenotype information
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    synonyms: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )  # JSON array of synonyms

    # Classification
    category: Mapped[str] = mapped_column(String(20), default="other", nullable=False)

    # HPO hierarchy
    parent_hpo_id: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )
    is_root_term: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Clinical context
    frequency_in_med13: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    severity_score: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )  # 1-5 scale

    # Relationships
    evidence: Mapped[list["EvidenceModel"]] = relationship(back_populates="phenotype")
    mechanisms: Mapped[list["MechanismModel"]] = relationship(
        secondary=mechanism_phenotypes,
        back_populates="phenotypes",
    )
    statements: Mapped[list["StatementModel"]] = relationship(
        secondary=statement_phenotypes,
        back_populates="phenotypes",
    )

    __table_args__ = {"sqlite_autoincrement": True}  # noqa: RUF012
