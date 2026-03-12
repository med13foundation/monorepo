"""Unit tests for SQLAlchemy claim-evidence repository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from src.infrastructure.repositories.kernel.kernel_claim_evidence_repository import (
    SqlAlchemyKernelClaimEvidenceRepository,
)
from src.infrastructure.repositories.kernel.kernel_relation_claim_repository import (
    SqlAlchemyKernelRelationClaimRepository,
)
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel


def _create_space_and_claim(db_session) -> tuple[str, str]:
    suffix = uuid4().hex
    user = UserModel(
        email=f"claim-evidence-repo-{suffix}@example.com",
        username=f"claim-evidence-repo-{suffix}",
        full_name="Claim Evidence Repo User",
        hashed_password="hashed_password",
        role="researcher",
        status="active",
        email_verified=True,
    )
    db_session.add(user)
    db_session.flush()

    space = ResearchSpaceModel(
        slug=f"claim-evidence-repo-{suffix[:16]}",
        name="Claim Evidence Repo Space",
        description="Space for claim evidence repository tests",
        owner_id=user.id,
        status="active",
    )
    db_session.add(space)
    db_session.flush()

    claim_repo = SqlAlchemyKernelRelationClaimRepository(db_session)
    claim = claim_repo.create(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="run-claim-evidence",
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
        claim_text="MED13 variants are associated with cardiomyopathy.",
        claim_section="results",
        linked_relation_id=None,
        metadata={},
    )
    return str(space.id), str(claim.id)


def test_claim_evidence_repository_create_list_and_preferred(db_session) -> None:
    _, claim_id = _create_space_and_claim(db_session)
    repository = SqlAlchemyKernelClaimEvidenceRepository(db_session)

    first = repository.create(
        claim_id=claim_id,
        source_document_id=None,
        agent_run_id="run-1",
        sentence="Older sentence",
        sentence_source="verbatim_span",
        sentence_confidence="high",
        sentence_rationale=None,
        figure_reference=None,
        table_reference=None,
        confidence=0.7,
        metadata={"rank": 1},
    )
    second = repository.create(
        claim_id=claim_id,
        source_document_id=None,
        agent_run_id="run-2",
        sentence=None,
        sentence_source=None,
        sentence_confidence=None,
        sentence_rationale="No sentence available.",
        figure_reference=None,
        table_reference=None,
        confidence=0.5,
        metadata={"rank": 2},
    )
    # Ensure deterministic ordering by created_at for preferred row.
    older_created_at = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    newer_created_at = datetime.now(UTC).isoformat()
    db_session.execute(
        text("UPDATE claim_evidence SET created_at = :created_at WHERE id = :id"),
        {
            "created_at": older_created_at,
            "id": str(first.id),
        },
    )
    db_session.execute(
        text("UPDATE claim_evidence SET created_at = :created_at WHERE id = :id"),
        {
            "created_at": newer_created_at,
            "id": str(second.id),
        },
    )
    db_session.flush()

    rows = repository.find_by_claim_id(claim_id)
    assert len(rows) == 2
    assert str(rows[0].id) == str(second.id)
    assert str(rows[1].id) == str(first.id)

    preferred = repository.get_preferred_for_claim(claim_id)
    assert preferred is not None
    assert str(preferred.id) == str(first.id)
    assert preferred.sentence == "Older sentence"


def test_claim_evidence_repository_find_by_claim_ids(db_session) -> None:
    space_id, claim_id = _create_space_and_claim(db_session)
    repository = SqlAlchemyKernelClaimEvidenceRepository(db_session)
    claim_repo = SqlAlchemyKernelRelationClaimRepository(db_session)
    second_claim = claim_repo.create(
        research_space_id=space_id,
        source_document_id=None,
        agent_run_id="run-claim-evidence-2",
        source_type="pubmed",
        relation_type="ASSOCIATED_WITH",
        target_type="DISEASE",
        source_label="MED13",
        target_label="Arrhythmia",
        confidence=0.51,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="OPEN",
        polarity="SUPPORT",
        claim_text="Second claim",
        claim_section=None,
        linked_relation_id=None,
        metadata={},
    )

    first_row = repository.create(
        claim_id=claim_id,
        source_document_id=None,
        agent_run_id="run-batch-1",
        sentence="Claim one evidence",
        sentence_source="verbatim_span",
        sentence_confidence="high",
        sentence_rationale=None,
        figure_reference=None,
        table_reference=None,
        confidence=0.8,
        metadata={},
    )
    second_row = repository.create(
        claim_id=str(second_claim.id),
        source_document_id=None,
        agent_run_id="run-batch-2",
        sentence="Claim two evidence",
        sentence_source="verbatim_span",
        sentence_confidence="medium",
        sentence_rationale=None,
        figure_reference=None,
        table_reference=None,
        confidence=0.6,
        metadata={},
    )

    grouped = repository.find_by_claim_ids([str(second_claim.id), claim_id])

    assert list(grouped.keys()) == [str(second_claim.id), claim_id]
    assert str(grouped[claim_id][0].id) == str(first_row.id)
    assert str(grouped[str(second_claim.id)][0].id) == str(second_row.id)
