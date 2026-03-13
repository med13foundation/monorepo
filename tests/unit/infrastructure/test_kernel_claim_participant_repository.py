"""Unit tests for SQLAlchemy claim-participant repository."""

from __future__ import annotations

from uuid import uuid4

from src.infrastructure.repositories.kernel.kernel_claim_participant_repository import (
    SqlAlchemyKernelClaimParticipantRepository,
)
from src.infrastructure.repositories.kernel.kernel_relation_claim_repository import (
    SqlAlchemyKernelRelationClaimRepository,
)
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel


def _create_space_and_claims(db_session) -> tuple[str, str, str]:
    suffix = uuid4().hex[:12]
    user = UserModel(
        email=f"claim-participant-repo-{suffix}@example.com",
        username=f"claim-participant-repo-{suffix}",
        full_name="Claim Participant Repo User",
        hashed_password="hashed_password",
        role="researcher",
        status="active",
        email_verified=True,
    )
    db_session.add(user)
    db_session.flush()

    space = ResearchSpaceModel(
        slug=f"claim-participant-repo-{suffix[:16]}",
        name="Claim Participant Repo Space",
        description="Space for claim participant repository tests",
        owner_id=user.id,
        status="active",
    )
    db_session.add(space)
    db_session.flush()

    claim_repo = SqlAlchemyKernelRelationClaimRepository(db_session)
    claim_a = claim_repo.create(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="run-claim-participant-a",
        source_type="pubmed",
        relation_type="ASSOCIATED_WITH",
        target_type="DISEASE",
        source_label="MED13",
        target_label="Cardiomyopathy",
        confidence=0.66,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="OPEN",
        polarity="SUPPORT",
        claim_text="Claim A",
        claim_section=None,
        linked_relation_id=None,
        metadata={},
    )
    claim_b = claim_repo.create(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="run-claim-participant-b",
        source_type="pubmed",
        relation_type="ASSOCIATED_WITH",
        target_type="DISEASE",
        source_label="MED13",
        target_label="Arrhythmia",
        confidence=0.55,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="OPEN",
        polarity="REFUTE",
        claim_text="Claim B",
        claim_section=None,
        linked_relation_id=None,
        metadata={},
    )
    return str(space.id), str(claim_a.id), str(claim_b.id)


def test_claim_participant_repository_find_by_claim_ids(db_session) -> None:
    space_id, claim_a_id, claim_b_id = _create_space_and_claims(db_session)
    repository = SqlAlchemyKernelClaimParticipantRepository(db_session)

    first = repository.create(
        claim_id=claim_a_id,
        research_space_id=space_id,
        role="SUBJECT",
        label="MED13",
        entity_id=None,
        position=1,
        qualifiers={},
    )
    second = repository.create(
        claim_id=claim_a_id,
        research_space_id=space_id,
        role="OBJECT",
        label="Cardiomyopathy",
        entity_id=None,
        position=2,
        qualifiers={},
    )
    third = repository.create(
        claim_id=claim_b_id,
        research_space_id=space_id,
        role="SUBJECT",
        label="MED13",
        entity_id=None,
        position=1,
        qualifiers={},
    )

    grouped = repository.find_by_claim_ids([claim_b_id, claim_a_id])

    assert list(grouped.keys()) == [claim_b_id, claim_a_id]
    assert [str(row.id) for row in grouped[claim_a_id]] == [
        str(first.id),
        str(second.id),
    ]
    assert [str(row.id) for row in grouped[claim_b_id]] == [str(third.id)]
