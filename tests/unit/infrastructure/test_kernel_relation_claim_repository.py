"""Unit tests for SQLAlchemy relation-claim repository."""

from __future__ import annotations

from uuid import uuid4

from src.infrastructure.repositories.kernel.kernel_relation_claim_repository import (
    SqlAlchemyKernelRelationClaimRepository,
)
from src.infrastructure.repositories.kernel.kernel_relation_repository import (
    SqlAlchemyKernelRelationRepository,
)
from src.models.database.kernel.entities import EntityModel
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from tests.graph_seed_helpers import ensure_relation_constraint


def _create_space_and_user(db_session):
    suffix = uuid4().hex[:12]
    user = UserModel(
        email=f"claim-repo-{suffix}@example.com",
        username=f"claim-repo-{suffix}",
        full_name="Claim Repo User",
        hashed_password="hashed_password",
        role="researcher",
        status="active",
        email_verified=True,
    )
    db_session.add(user)
    db_session.flush()

    space = ResearchSpaceModel(
        slug=f"claim-repo-{suffix[:16]}",
        name="Claim Repo Space",
        description="Space for relation claim repository tests",
        owner_id=user.id,
        status="active",
    )
    db_session.add(space)
    db_session.flush()
    return user, space


def _create_linked_relation(
    db_session,
    *,
    research_space_id: str,
    relation_type: str,
) -> str:
    ensure_relation_constraint(
        db_session,
        source_type="GENE",
        relation_type=relation_type,
        target_type="DISEASE",
    )
    source_id = uuid4()
    target_id = uuid4()
    db_session.add_all(
        [
            EntityModel(
                id=source_id,
                research_space_id=research_space_id,
                entity_type="GENE",
                display_label="MED13",
                metadata_payload={},
            ),
            EntityModel(
                id=target_id,
                research_space_id=research_space_id,
                entity_type="DISEASE",
                display_label="Cardiomyopathy",
                metadata_payload={},
            ),
        ],
    )
    db_session.flush()
    relation = SqlAlchemyKernelRelationRepository(db_session).upsert_relation(
        research_space_id=research_space_id,
        source_id=str(source_id),
        relation_type=relation_type,
        target_id=str(target_id),
    )
    return str(relation.id)


def test_relation_claim_repository_create_list_count_and_triage(db_session) -> None:
    user, space = _create_space_and_user(db_session)
    repository = SqlAlchemyKernelRelationClaimRepository(db_session)

    open_claim = repository.create(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="run-1",
        source_type="pubmed",
        relation_type="ASSOCIATED_WITH",
        target_type="DISEASE",
        source_label="MED13",
        target_label="Cardiomyopathy",
        confidence=0.45,
        validation_state="FORBIDDEN",
        validation_reason="Constraint mismatch",
        persistability="NON_PERSISTABLE",
        claim_status="OPEN",
        polarity="REFUTE",
        claim_text="No significant association was observed.",
        claim_section="results",
        linked_relation_id=None,
        metadata={"case": "open"},
    )
    resolved_claim = repository.create(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="run-2",
        source_type="pubmed",
        relation_type="CAUSES",
        target_type="DISEASE",
        source_label="MED13",
        target_label="Arrhythmia",
        confidence=0.91,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        polarity="SUPPORT",
        claim_text="MED13 variants are associated with arrhythmia.",
        claim_section="results",
        linked_relation_id=None,
        metadata={"case": "resolved"},
    )

    listed = repository.find_by_research_space(
        str(space.id),
        claim_status="OPEN",
        limit=10,
        offset=0,
    )
    assert len(listed) == 1
    assert str(listed[0].id) == str(open_claim.id)
    assert listed[0].polarity == "REFUTE"
    assert listed[0].claim_text == "No significant association was observed."
    assert listed[0].claim_section == "results"

    total_all = repository.count_by_research_space(str(space.id))
    assert total_all == 2

    high_certainty_total = repository.count_by_research_space(
        str(space.id),
        certainty_band="HIGH",
    )
    assert high_certainty_total == 1

    non_persistable_total = repository.count_by_research_space(
        str(space.id),
        persistability="NON_PERSISTABLE",
    )
    assert non_persistable_total == 1

    refute_total = repository.count_by_research_space(
        str(space.id),
        polarity="REFUTE",
    )
    assert refute_total == 1

    updated = repository.update_triage_status(
        str(open_claim.id),
        claim_status="NEEDS_MAPPING",
        triaged_by=str(user.id),
    )
    assert updated.claim_status == "NEEDS_MAPPING"
    assert str(updated.triaged_by) == str(user.id)

    fetched_resolved = repository.get_by_id(str(resolved_claim.id))
    assert fetched_resolved is not None
    assert fetched_resolved.claim_status == "RESOLVED"


def test_relation_claim_repository_conflict_detection(db_session) -> None:
    _, space = _create_space_and_user(db_session)
    repository = SqlAlchemyKernelRelationClaimRepository(db_session)
    linked_relation_id = _create_linked_relation(
        db_session,
        research_space_id=str(space.id),
        relation_type="ASSOCIATED_WITH",
    )

    _ = repository.create(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="run-support",
        source_type="pubmed",
        relation_type="ASSOCIATED_WITH",
        target_type="DISEASE",
        source_label="MED13",
        target_label="Cardiomyopathy",
        confidence=0.88,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="OPEN",
        polarity="SUPPORT",
        claim_text=None,
        claim_section=None,
        linked_relation_id=linked_relation_id,
        metadata={},
    )
    _ = repository.create(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="run-refute",
        source_type="pubmed",
        relation_type="ASSOCIATED_WITH",
        target_type="DISEASE",
        source_label="MED13",
        target_label="Cardiomyopathy",
        confidence=0.72,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="OPEN",
        polarity="REFUTE",
        claim_text=None,
        claim_section=None,
        linked_relation_id=linked_relation_id,
        metadata={},
    )

    conflicts = repository.find_conflicts_by_research_space(
        str(space.id),
        limit=10,
        offset=0,
    )
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert str(conflict.relation_id) == linked_relation_id
    assert conflict.support_count == 1
    assert conflict.refute_count == 1
    assert len(conflict.support_claim_ids) == 1
    assert len(conflict.refute_claim_ids) == 1
    assert repository.count_conflicts_by_research_space(str(space.id)) == 1


def test_relation_claim_repository_find_by_linked_relation_ids(db_session) -> None:
    _, space = _create_space_and_user(db_session)
    repository = SqlAlchemyKernelRelationClaimRepository(db_session)
    relation_id_a = _create_linked_relation(
        db_session,
        research_space_id=str(space.id),
        relation_type="ASSOCIATED_WITH",
    )
    relation_id_b = _create_linked_relation(
        db_session,
        research_space_id=str(space.id),
        relation_type="ASSOCIATED_WITH",
    )

    claim_a = repository.create(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="run-a",
        source_type="pubmed",
        relation_type="ASSOCIATED_WITH",
        target_type="DISEASE",
        source_label="MED13",
        target_label="Cardiomyopathy",
        confidence=0.88,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="OPEN",
        polarity="SUPPORT",
        claim_text="Support claim",
        claim_section=None,
        linked_relation_id=relation_id_a,
        metadata={},
    )
    claim_b = repository.create(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="run-b",
        source_type="pubmed",
        relation_type="ASSOCIATED_WITH",
        target_type="DISEASE",
        source_label="MED13",
        target_label="Arrhythmia",
        confidence=0.77,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="OPEN",
        polarity="REFUTE",
        claim_text="Refute claim",
        claim_section=None,
        linked_relation_id=relation_id_b,
        metadata={},
    )
    _ = repository.create(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="run-c",
        source_type="pubmed",
        relation_type="CAUSES",
        target_type="DISEASE",
        source_label="MED13",
        target_label="Other",
        confidence=0.61,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="OPEN",
        polarity="SUPPORT",
        claim_text="Unlinked elsewhere",
        claim_section=None,
        linked_relation_id=_create_linked_relation(
            db_session,
            research_space_id=str(space.id),
            relation_type="CAUSES",
        ),
        metadata={},
    )

    rows = repository.find_by_linked_relation_ids(
        research_space_id=str(space.id),
        linked_relation_ids=[relation_id_b, relation_id_a],
    )

    returned_ids = {str(row.id) for row in rows}
    assert returned_ids == {str(claim_a.id), str(claim_b.id)}
