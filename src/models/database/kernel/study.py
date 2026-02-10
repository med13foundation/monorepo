"""
Study models — replaces the old ResearchSpace models.

A Study is the kernel equivalent of a Research Space:
a multi-tenant workspace scoped to a domain context.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.database.base import Base


class StudyModel(Base):
    """
    A Study (formerly Research Space).

    All entities, observations, and relations are scoped to a study.
    """

    __tablename__ = "studies"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Unique study identifier",
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Display name",
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        doc="URL-safe unique identifier",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Study description",
    )
    domain_context: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default="genomics",
        index=True,
        doc="Domain filter for dictionary lookups",
    )
    created_by: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        doc="Owner user ID",
    )
    is_default: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        doc="Default study for new users",
    )

    # Settings
    settings: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        doc="Study-specific settings",
    )
    tags: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
        doc="Searchable tags",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    owner = relationship("UserModel", back_populates="owned_studies")
    memberships = relationship(
        "StudyMembershipModel",
        back_populates="study",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_studies_owner", "created_by"),
        Index("idx_studies_domain", "domain_context"),
        Index("idx_studies_created_at", "created_at"),
        {"comment": "Studies (multi-tenant workspaces scoped to a domain)"},
    )

    def __repr__(self) -> str:
        return f"<StudyModel(id={self.id}, slug={self.slug}, name={self.name})>"


class StudyMembershipModel(Base):
    """
    Study membership — maps users to studies with roles.
    """

    __tablename__ = "study_memberships"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Unique membership identifier",
    )
    study_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("studies.id", ondelete="CASCADE"),
        nullable=False,
        doc="Study ID",
    )
    user_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        doc="User ID",
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="member",
        doc="Role: owner, admin, curator, researcher, viewer",
    )

    # Invitation workflow
    invited_by: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    invited_at: Mapped[datetime | None] = mapped_column(nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(nullable=True)

    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
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

    # Relationships
    study = relationship("StudyModel", back_populates="memberships")
    user = relationship(
        "UserModel",
        foreign_keys=[user_id],
        back_populates="study_memberships",
    )
    inviter = relationship(
        "UserModel",
        foreign_keys=[invited_by],
        back_populates="sent_study_invitations",
    )

    __table_args__ = (
        Index("idx_study_memberships_study", "study_id"),
        Index("idx_study_memberships_user", "user_id"),
        Index(
            "idx_study_memberships_unique",
            "study_id",
            "user_id",
            unique=True,
        ),
        {"comment": "Study memberships for role-based access control"},
    )

    def __repr__(self) -> str:
        return (
            f"<StudyMembershipModel(study_id={self.study_id}, "
            f"user_id={self.user_id}, role={self.role})>"
        )
