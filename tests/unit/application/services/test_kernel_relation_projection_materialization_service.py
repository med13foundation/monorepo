"""Unit tests for claim-backed relation projection materialization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from src.application.services.kernel.dictionary_management_service import (
    DictionaryManagementService,
)
from src.application.services.kernel.kernel_relation_projection_materialization_service import (
    KernelRelationProjectionMaterializationService,
    RelationProjectionMaterializationError,
)
from src.domain.entities.user import UserRole, UserStatus
from src.domain.ports.dictionary_search_harness_port import DictionarySearchHarnessPort
from src.infrastructure.repositories.kernel import (
    SqlAlchemyDictionaryRepository,
    SqlAlchemyKernelClaimEvidenceRepository,
    SqlAlchemyKernelClaimParticipantRepository,
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelRelationClaimRepository,
    SqlAlchemyKernelRelationProjectionSourceRepository,
    SqlAlchemyKernelRelationRepository,
)
from src.models.database.kernel.dictionary import DictionaryDomainContextModel
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.domain.entities.kernel.dictionary import DictionarySearchResult
    from src.domain.entities.kernel.relation_claims import (
        RelationClaimPersistability,
        RelationClaimPolarity,
        RelationClaimStatus,
    )


class _DeterministicHarness(DictionarySearchHarnessPort):
    """Dictionary harness that delegates to the real repository search."""

    def __init__(self, repository: SqlAlchemyDictionaryRepository) -> None:
        self._repository = repository

    def search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        return self._repository.search_dictionary(
            terms=terms,
            dimensions=dimensions,
            domain_context=domain_context,
            limit=limit,
            query_embeddings=None,
            include_inactive=include_inactive,
        )


@dataclass(frozen=True)
class _EvidenceSeed:
    summary: str
    confidence: float
    tier: str
    sentence: str


@dataclass(frozen=True)
class _ProjectionFixture:
    service: KernelRelationProjectionMaterializationService
    relation_repo: SqlAlchemyKernelRelationRepository
    claim_repo: SqlAlchemyKernelRelationClaimRepository
    participant_repo: SqlAlchemyKernelClaimParticipantRepository
    claim_evidence_repo: SqlAlchemyKernelClaimEvidenceRepository
    projection_repo: SqlAlchemyKernelRelationProjectionSourceRepository
    research_space_id: str
    source_entity_id: str
    target_entity_id: str


def _build_fixture(db_session: Session) -> _ProjectionFixture:
    domain_context_id = f"projection_materializer_{uuid4().hex[:12]}"
    db_session.add(
        DictionaryDomainContextModel(
            id=domain_context_id,
            display_name="Clinical",
            description="Clinical domain for projection materialization tests",
        ),
    )
    db_session.flush()

    user = UserModel(
        email=f"projection-materializer-{uuid4().hex}@example.com",
        username=f"projection-materializer-{uuid4().hex}",
        full_name="Projection Materializer Tester",
        hashed_password="hashed",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.flush()

    space = ResearchSpaceModel(
        slug=f"projection-materializer-{uuid4().hex[:12]}",
        name="Projection Materializer Space",
        description="Unit test space for claim-backed relation projections",
        owner_id=user.id,
        status="active",
    )
    db_session.add(space)
    db_session.flush()

    dictionary_repo = SqlAlchemyDictionaryRepository(db_session)
    dictionary_service = DictionaryManagementService(
        dictionary_repo=dictionary_repo,
        dictionary_search_harness=_DeterministicHarness(dictionary_repo),
        embedding_provider=None,
    )
    dictionary_service.create_entity_type(
        entity_type="GENE",
        display_name="Gene",
        description="Gene entity type",
        domain_context=domain_context_id,
        created_by="manual:test",
        source_ref="tests:projection-materializer",
    )
    dictionary_service.create_entity_type(
        entity_type="PHENOTYPE",
        display_name="Phenotype",
        description="Phenotype entity type",
        domain_context=domain_context_id,
        created_by="manual:test",
        source_ref="tests:projection-materializer",
    )
    dictionary_service.create_relation_type(
        relation_type="ASSOCIATED_WITH",
        display_name="Associated with",
        description="Association relation type",
        domain_context=domain_context_id,
        created_by="manual:test",
        source_ref="tests:projection-materializer",
    )
    dictionary_service.create_relation_constraint(
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        is_allowed=True,
        requires_evidence=False,
        created_by="manual:test",
        source_ref="tests:projection-materializer",
    )

    entity_repo = SqlAlchemyKernelEntityRepository(db_session)
    source_entity = entity_repo.create(
        research_space_id=str(space.id),
        entity_type="GENE",
        display_label="MED13",
        metadata={},
    )
    target_entity = entity_repo.create(
        research_space_id=str(space.id),
        entity_type="PHENOTYPE",
        display_label="Cardiomyopathy",
        metadata={},
    )

    relation_repo = SqlAlchemyKernelRelationRepository(db_session)
    claim_repo = SqlAlchemyKernelRelationClaimRepository(db_session)
    participant_repo = SqlAlchemyKernelClaimParticipantRepository(db_session)
    claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(db_session)
    projection_repo = SqlAlchemyKernelRelationProjectionSourceRepository(db_session)
    service = KernelRelationProjectionMaterializationService(
        relation_repo=relation_repo,
        relation_claim_repo=claim_repo,
        claim_participant_repo=participant_repo,
        claim_evidence_repo=claim_evidence_repo,
        entity_repo=entity_repo,
        dictionary_repo=dictionary_repo,
        relation_projection_repo=projection_repo,
    )
    return _ProjectionFixture(
        service=service,
        relation_repo=relation_repo,
        claim_repo=claim_repo,
        participant_repo=participant_repo,
        claim_evidence_repo=claim_evidence_repo,
        projection_repo=projection_repo,
        research_space_id=str(space.id),
        source_entity_id=str(source_entity.id),
        target_entity_id=str(target_entity.id),
    )


def _create_claim(
    fixture: _ProjectionFixture,
    *,
    polarity: RelationClaimPolarity = "SUPPORT",
    claim_status: RelationClaimStatus = "RESOLVED",
    persistability: RelationClaimPersistability = "PERSISTABLE",
    with_participants: bool = True,
    evidence_seeds: list[_EvidenceSeed] | None = None,
) -> str:
    claim = fixture.claim_repo.create(
        research_space_id=fixture.research_space_id,
        source_document_id=None,
        agent_run_id="projection-test-run",
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Cardiomyopathy",
        confidence=0.82,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability=persistability,
        claim_status=claim_status,
        polarity=polarity,
        claim_text="MED13 is associated with cardiomyopathy.",
        claim_section="results",
        linked_relation_id=None,
        metadata={},
    )
    claim_id = str(claim.id)

    if with_participants:
        fixture.participant_repo.create(
            claim_id=claim_id,
            research_space_id=fixture.research_space_id,
            role="SUBJECT",
            label="MED13",
            entity_id=fixture.source_entity_id,
            position=0,
            qualifiers={},
        )
        fixture.participant_repo.create(
            claim_id=claim_id,
            research_space_id=fixture.research_space_id,
            role="OBJECT",
            label="Cardiomyopathy",
            entity_id=fixture.target_entity_id,
            position=1,
            qualifiers={},
        )

    for index, evidence_seed in enumerate(evidence_seeds or []):
        fixture.claim_evidence_repo.create(
            claim_id=claim_id,
            source_document_id=None,
            agent_run_id=f"projection-evidence-{index}",
            sentence=evidence_seed.sentence,
            sentence_source="verbatim_span",
            sentence_confidence="high",
            sentence_rationale="Direct supporting span",
            figure_reference=None,
            table_reference=None,
            confidence=evidence_seed.confidence,
            metadata={
                "evidence_summary": evidence_seed.summary,
                "evidence_tier": evidence_seed.tier,
            },
        )

    return claim_id


@pytest.mark.database
def test_materialize_support_claim_creates_claim_backed_relation_and_derived_evidence(
    db_session: Session,
) -> None:
    fixture = _build_fixture(db_session)
    claim_id = _create_claim(
        fixture,
        evidence_seeds=[
            _EvidenceSeed(
                summary="Cohort study linked MED13 to cardiomyopathy.",
                confidence=0.65,
                tier="LITERATURE",
                sentence="MED13 variants were associated with cardiomyopathy in cohort A.",
            ),
        ],
    )

    result = fixture.service.materialize_support_claim(
        claim_id=claim_id,
        research_space_id=fixture.research_space_id,
        projection_origin="EXTRACTION",
    )

    assert result.relation is not None
    relation = result.relation
    assert result.rebuilt_relation_ids == (str(relation.id),)
    assert result.derived_evidence_rows == 1
    assert relation.source_count == 1
    assert relation.aggregate_confidence == pytest.approx(0.65)
    assert relation.highest_evidence_tier == "LITERATURE"

    persisted_claim = fixture.claim_repo.get_by_id(claim_id)
    assert persisted_claim is not None
    assert persisted_claim.linked_relation_id is not None
    assert str(persisted_claim.linked_relation_id) == str(relation.id)

    persisted_relations = fixture.relation_repo.find_by_research_space(
        fixture.research_space_id,
        limit=10,
        offset=0,
    )
    assert [str(item.id) for item in persisted_relations] == [str(relation.id)]

    projection_rows = fixture.projection_repo.find_by_relation_id(str(relation.id))
    assert len(projection_rows) == 1
    assert str(projection_rows[0].claim_id) == claim_id

    evidence_rows = fixture.relation_repo.list_evidence_for_relation(
        research_space_id=fixture.research_space_id,
        relation_id=str(relation.id),
    )
    assert len(evidence_rows) == 1
    assert evidence_rows[0].evidence_summary == (
        "Cohort study linked MED13 to cardiomyopathy."
    )
    assert evidence_rows[0].evidence_sentence == (
        "MED13 variants were associated with cardiomyopathy in cohort A."
    )


@pytest.mark.database
def test_materialize_support_claim_reuses_existing_relation_for_same_triple(
    db_session: Session,
) -> None:
    fixture = _build_fixture(db_session)
    first_claim_id = _create_claim(
        fixture,
        evidence_seeds=[
            _EvidenceSeed(
                summary="Paper A linked MED13 to cardiomyopathy.",
                confidence=0.65,
                tier="LITERATURE",
                sentence="Paper A reported a MED13 association with cardiomyopathy.",
            ),
        ],
    )
    second_claim_id = _create_claim(
        fixture,
        evidence_seeds=[
            _EvidenceSeed(
                summary="Experiment B validated the MED13 association.",
                confidence=0.9,
                tier="EXPERIMENTAL",
                sentence="Experiment B confirmed the MED13-cardiomyopathy association.",
            ),
        ],
    )

    first_result = fixture.service.materialize_support_claim(
        claim_id=first_claim_id,
        research_space_id=fixture.research_space_id,
        projection_origin="EXTRACTION",
    )
    second_result = fixture.service.materialize_support_claim(
        claim_id=second_claim_id,
        research_space_id=fixture.research_space_id,
        projection_origin="GRAPH_CONNECTION",
    )

    assert first_result.relation is not None
    assert second_result.relation is not None
    assert second_result.relation.id == first_result.relation.id
    assert second_result.derived_evidence_rows == 2

    relation_id = str(second_result.relation.id)
    projection_rows = fixture.projection_repo.find_by_relation_id(relation_id)
    assert len(projection_rows) == 2
    assert {str(row.claim_id) for row in projection_rows} == {
        first_claim_id,
        second_claim_id,
    }

    relation = fixture.relation_repo.get_by_id(relation_id)
    assert relation is not None
    assert relation.source_count == 2
    assert relation.aggregate_confidence == pytest.approx(0.965)
    assert relation.highest_evidence_tier == "EXPERIMENTAL"

    evidence_rows = fixture.relation_repo.list_evidence_for_relation(
        research_space_id=fixture.research_space_id,
        relation_id=relation_id,
    )
    assert len(evidence_rows) == 2
    assert {row.evidence_summary for row in evidence_rows} == {
        "Paper A linked MED13 to cardiomyopathy.",
        "Experiment B validated the MED13 association.",
    }


@pytest.mark.database
@pytest.mark.parametrize("polarity", ["REFUTE", "UNCERTAIN", "HYPOTHESIS"])
def test_materialize_support_claim_rejects_non_support_claims(
    db_session: Session,
    polarity: RelationClaimPolarity,
) -> None:
    fixture = _build_fixture(db_session)
    claim_id = _create_claim(
        fixture,
        polarity=polarity,
        evidence_seeds=[
            _EvidenceSeed(
                summary="Non-support claim evidence.",
                confidence=0.55,
                tier="COMPUTATIONAL",
                sentence="The claim polarity is not support.",
            ),
        ],
    )

    with pytest.raises(
        RelationProjectionMaterializationError,
        match="Only SUPPORT claims can materialize canonical relations",
    ):
        fixture.service.materialize_support_claim(
            claim_id=claim_id,
            research_space_id=fixture.research_space_id,
            projection_origin="CLAIM_RESOLUTION",
        )

    assert (
        fixture.relation_repo.find_by_research_space(
            fixture.research_space_id,
            limit=10,
            offset=0,
        )
        == []
    )
    assert (
        fixture.projection_repo.find_by_claim_id(
            research_space_id=fixture.research_space_id,
            claim_id=claim_id,
        )
        == []
    )


@pytest.mark.database
def test_detach_claim_projection_deletes_relation_when_last_source_is_removed(
    db_session: Session,
) -> None:
    fixture = _build_fixture(db_session)
    claim_id = _create_claim(
        fixture,
        evidence_seeds=[
            _EvidenceSeed(
                summary="Single support claim evidence.",
                confidence=0.77,
                tier="LITERATURE",
                sentence="One support claim backed the relation.",
            ),
        ],
    )

    materialized = fixture.service.materialize_support_claim(
        claim_id=claim_id,
        research_space_id=fixture.research_space_id,
        projection_origin="MANUAL_RELATION",
    )

    assert materialized.relation is not None
    relation_id = str(materialized.relation.id)

    detached = fixture.service.detach_claim_projection(
        claim_id=claim_id,
        research_space_id=fixture.research_space_id,
    )

    assert detached.deleted_relation_ids == (relation_id,)
    assert fixture.relation_repo.get_by_id(relation_id, claim_backed_only=False) is None
    assert (
        fixture.projection_repo.find_by_claim_id(
            research_space_id=fixture.research_space_id,
            claim_id=claim_id,
        )
        == []
    )
    detached_claim = fixture.claim_repo.get_by_id(claim_id)
    assert detached_claim is not None
    assert detached_claim.linked_relation_id is None


@pytest.mark.database
def test_materialize_support_claim_requires_claim_participants(
    db_session: Session,
) -> None:
    fixture = _build_fixture(db_session)
    claim_id = _create_claim(
        fixture,
        with_participants=False,
        evidence_seeds=[
            _EvidenceSeed(
                summary="Claim without participants.",
                confidence=0.61,
                tier="LITERATURE",
                sentence="The claim was missing anchored participants.",
            ),
        ],
    )

    with pytest.raises(
        RelationProjectionMaterializationError,
        match="requires SUBJECT/OBJECT participants with entity anchors",
    ):
        fixture.service.materialize_support_claim(
            claim_id=claim_id,
            research_space_id=fixture.research_space_id,
            projection_origin="EXTRACTION",
        )

    assert (
        fixture.relation_repo.find_by_research_space(
            fixture.research_space_id,
            limit=10,
            offset=0,
        )
        == []
    )
