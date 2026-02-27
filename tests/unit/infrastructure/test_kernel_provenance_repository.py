"""Unit tests for the SQLAlchemy kernel provenance repository adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.domain.entities.user import UserRole, UserStatus
from src.infrastructure.repositories.kernel.kernel_provenance_repository import (
    SqlAlchemyProvenanceRepository,
)
from src.models.database.research_space import ResearchSpaceModel, SpaceStatusEnum
from src.models.database.user import UserModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _seed_research_space(db_session: Session) -> UUID:
    owner_id = uuid4()
    db_session.add(
        UserModel(
            id=owner_id,
            email=f"{owner_id}@example.org",
            username=f"user_{str(owner_id).replace('-', '')[:8]}",
            full_name="Test User",
            hashed_password="hashed",
            role=UserRole.RESEARCHER,
            status=UserStatus.ACTIVE,
            email_verified=True,
        ),
    )
    research_space_id = uuid4()
    db_session.add(
        ResearchSpaceModel(
            id=research_space_id,
            slug=f"space-{str(research_space_id).replace('-', '')[:8]}",
            name="Test Space",
            description="Test research space",
            owner_id=owner_id,
            status=SpaceStatusEnum.ACTIVE,
            settings={},
            tags=[],
        ),
    )
    db_session.flush()
    return research_space_id


def test_create_and_find_by_non_uuid_extraction_run_id(db_session: Session) -> None:
    research_space_id = _seed_research_space(db_session)
    repository = SqlAlchemyProvenanceRepository(db_session)

    created = repository.create(
        research_space_id=str(research_space_id),
        source_type="AI_EXTRACTION",
        source_ref="test://pubmed/1001",
        extraction_run_id="extract:pubmed:sha256:run-001",
        mapping_method="llm",
        mapping_confidence=0.95,
        raw_input={"record_id": "1001"},
    )
    db_session.commit()

    rows = repository.find_by_extraction_run("extract:pubmed:sha256:run-001")

    assert created.extraction_run_id == "extract:pubmed:sha256:run-001"
    assert len(rows) == 1
    assert rows[0].id == created.id
    assert rows[0].extraction_run_id == "extract:pubmed:sha256:run-001"
