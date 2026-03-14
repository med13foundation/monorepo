"""Unit tests for claim-backed relation projection materialization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from src.application.services.kernel.dictionary_management_service import (
    DictionaryManagementService,
)
from src.application.services.kernel.kernel_relation_projection_materialization_service import (
    KernelRelationProjectionMaterializationService,
    RelationProjectionMaterializationError,
)
from src.domain.entities.kernel.claim_participants import KernelClaimParticipant
from src.domain.entities.user import UserRole, UserStatus
from src.domain.ports.dictionary_search_harness_port import DictionarySearchHarnessPort
from src.graph.core.read_model import (
    GraphReadModelUpdate,
    NullGraphReadModelUpdateDispatcher,
)
from src.graph.core.relation_autopromotion_policy import AutoPromotionPolicy
from src.graph.pack_registry import resolve_graph_domain_pack
from src.infrastructure.repositories.kernel import (
    SqlAlchemyDictionaryRepository,
    SqlAlchemyKernelClaimEvidenceRepository,
    SqlAlchemyKernelClaimParticipantRepository,
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelRelationClaimRepository,
    SqlAlchemyKernelRelationProjectionSourceRepository,
    SqlAlchemyKernelRelationRepository,
)
from src.models.database.kernel.claim_evidence import ClaimEvidenceModel
from src.models.database.kernel.claim_participants import ClaimParticipantModel
from src.models.database.kernel.dictionary import DictionaryDomainContextModel
from src.models.database.kernel.relation_claims import RelationClaimModel
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel

pytestmark = pytest.mark.graph

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
    dispatcher: _RecordingReadModelDispatcher
    research_space_id: str
    source_entity_id: str
    target_entity_id: str


@dataclass
class _RecordingReadModelDispatcher(NullGraphReadModelUpdateDispatcher):
    updates: list[GraphReadModelUpdate]

    def dispatch(self, update: GraphReadModelUpdate) -> int:
        self.updates.append(update)
        return 1

    def dispatch_many(self, updates: tuple[GraphReadModelUpdate, ...]) -> int:
        self.updates.extend(updates)
        return len(updates)


def _build_relation_repository(
    db_session: Session,
) -> SqlAlchemyKernelRelationRepository:
    return SqlAlchemyKernelRelationRepository(
        db_session,
        auto_promotion_policy=AutoPromotionPolicy(),
    )


def _build_fixture(db_session: Session) -> _ProjectionFixture:
    domain_context_id = f"projection_materializer_{uuid4().hex[:12]}"
    user_suffix = uuid4().hex[:10]
    db_session.add(
        DictionaryDomainContextModel(
            id=domain_context_id,
            display_name="Clinical",
            description="Clinical domain for projection materialization tests",
        ),
    )
    db_session.flush()

    user = UserModel(
        email=f"pm-{user_suffix}@example.com",
        username=f"pm-{user_suffix}",
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

    dictionary_repo = SqlAlchemyDictionaryRepository(
        db_session,
        builtin_domain_contexts=resolve_graph_domain_pack().dictionary_domain_contexts,
    )
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

    relation_repo = _build_relation_repository(db_session)
    claim_repo = SqlAlchemyKernelRelationClaimRepository(db_session)
    participant_repo = SqlAlchemyKernelClaimParticipantRepository(db_session)
    claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(db_session)
    projection_repo = SqlAlchemyKernelRelationProjectionSourceRepository(db_session)
    dispatcher = _RecordingReadModelDispatcher(updates=[])
    service = KernelRelationProjectionMaterializationService(
        relation_repo=relation_repo,
        relation_claim_repo=claim_repo,
        claim_participant_repo=participant_repo,
        claim_evidence_repo=claim_evidence_repo,
        entity_repo=entity_repo,
        dictionary_repo=dictionary_repo,
        relation_projection_repo=projection_repo,
        read_model_update_dispatcher=dispatcher,
    )
    return _ProjectionFixture(
        service=service,
        relation_repo=relation_repo,
        claim_repo=claim_repo,
        participant_repo=participant_repo,
        claim_evidence_repo=claim_evidence_repo,
        projection_repo=projection_repo,
        dispatcher=dispatcher,
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
    source_document_ref: str | None = None,
) -> str:
    claim = fixture.claim_repo.create(
        research_space_id=fixture.research_space_id,
        source_document_id=None,
        source_document_ref=source_document_ref,
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
            source_document_ref=source_document_ref,
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
def test_materialize_support_claim_dispatches_projection_read_model_updates(
    db_session: Session,
) -> None:
    fixture = _build_fixture(db_session)
    claim_id = _create_claim(
        fixture,
        evidence_seeds=[
            _EvidenceSeed(
                summary="Dispatcher evidence.",
                confidence=0.88,
                tier="LITERATURE",
                sentence="MED13 has dispatcher-backed projection updates.",
            ),
        ],
    )

    fixture.service.materialize_support_claim(
        claim_id=claim_id,
        research_space_id=fixture.research_space_id,
        projection_origin="CLAIM_RESOLUTION",
    )

    assert [update.model_name for update in fixture.dispatcher.updates] == [
        "entity_neighbors",
        "entity_relation_summary",
        "entity_claim_summary",
    ]
    assert all(
        update.trigger == "projection_change" for update in fixture.dispatcher.updates
    )
    assert all(update.claim_ids == (claim_id,) for update in fixture.dispatcher.updates)
    assert all(
        update.space_id == fixture.research_space_id
        for update in fixture.dispatcher.updates
    )
    assert all(update.entity_ids for update in fixture.dispatcher.updates)


@pytest.mark.database
def test_materialize_support_claim_preserves_external_document_refs(
    db_session: Session,
) -> None:
    fixture = _build_fixture(db_session)
    external_document_ref = "https://example.org/papers/materialized-evidence"
    claim_id = _create_claim(
        fixture,
        source_document_ref=external_document_ref,
        evidence_seeds=[
            _EvidenceSeed(
                summary="External document reference is preserved across projection.",
                confidence=0.71,
                tier="LITERATURE",
                sentence="Evidence with an external document reference was retained.",
            ),
        ],
    )

    result = fixture.service.materialize_support_claim(
        claim_id=claim_id,
        research_space_id=fixture.research_space_id,
        projection_origin="CLAIM_RESOLUTION",
    )

    assert result.relation is not None
    projection_rows = fixture.projection_repo.find_by_relation_id(
        str(result.relation.id),
    )
    assert len(projection_rows) == 1
    assert projection_rows[0].source_document_ref == external_document_ref

    evidence_rows = fixture.relation_repo.list_evidence_for_relation(
        research_space_id=fixture.research_space_id,
        relation_id=str(result.relation.id),
    )
    assert len(evidence_rows) == 1
    assert evidence_rows[0].source_document_ref == external_document_ref


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


@pytest.mark.database
@pytest.mark.parametrize(
    ("claim_status", "persistability", "error_message"),
    [
        (
            "OPEN",
            "PERSISTABLE",
            "Only RESOLVED claims can materialize canonical relations",
        ),
        (
            "RESOLVED",
            "NON_PERSISTABLE",
            "Only PERSISTABLE claims can materialize canonical relations",
        ),
    ],
)
def test_materialize_support_claim_enforces_materializable_state(
    db_session: Session,
    claim_status: RelationClaimStatus,
    persistability: RelationClaimPersistability,
    error_message: str,
) -> None:
    fixture = _build_fixture(db_session)
    claim_id = _create_claim(
        fixture,
        claim_status=claim_status,
        persistability=persistability,
        evidence_seeds=[
            _EvidenceSeed(
                summary="Inactive support claim evidence.",
                confidence=0.5,
                tier="COMPUTATIONAL",
                sentence="This claim should not materialize.",
            ),
        ],
    )

    with pytest.raises(RelationProjectionMaterializationError, match=error_message):
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


@pytest.mark.database
def test_materialize_support_claim_rejects_unresolved_endpoint_entities(
    db_session: Session,
) -> None:
    fixture = _build_fixture(db_session)
    claim_id = _create_claim(
        fixture,
        evidence_seeds=[
            _EvidenceSeed(
                summary="Support claim with deleted entity.",
                confidence=0.62,
                tier="LITERATURE",
                sentence="An endpoint entity was removed before projection.",
            ),
        ],
    )

    subject_participant = db_session.scalars(
        select(ClaimParticipantModel).where(
            ClaimParticipantModel.claim_id == UUID(claim_id),
            ClaimParticipantModel.role == "SUBJECT",
        ),
    ).one()
    subject_participant.entity_id = None
    db_session.flush()
    db_session.expire_all()

    with pytest.raises(
        RelationProjectionMaterializationError,
        match=(
            "Claim-backed materialization requires SUBJECT/OBJECT participants "
            "with entity anchors"
        ),
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


@pytest.mark.database
@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("polarity", "REFUTE"),
        ("claim_status", "OPEN"),
        ("persistability", "NON_PERSISTABLE"),
    ],
)
def test_rebuild_relation_projection_prunes_invalidated_claim_sources(
    db_session: Session,
    field_name: str,
    value: str,
) -> None:
    fixture = _build_fixture(db_session)
    claim_id = _create_claim(
        fixture,
        evidence_seeds=[
            _EvidenceSeed(
                summary="Support claim before invalidation.",
                confidence=0.81,
                tier="LITERATURE",
                sentence="This support claim is initially valid.",
            ),
        ],
    )

    materialized = fixture.service.materialize_support_claim(
        claim_id=claim_id,
        research_space_id=fixture.research_space_id,
        projection_origin="CLAIM_RESOLUTION",
    )
    assert materialized.relation is not None
    relation_id = str(materialized.relation.id)

    claim_model = db_session.get(RelationClaimModel, UUID(claim_id))
    assert claim_model is not None
    setattr(claim_model, field_name, value)
    db_session.flush()

    rebuilt = fixture.service.rebuild_relation_projection(
        relation_id=relation_id,
        research_space_id=fixture.research_space_id,
    )

    assert rebuilt.relation is None
    assert rebuilt.deleted_relation_ids == (relation_id,)
    assert fixture.relation_repo.get_by_id(relation_id, claim_backed_only=False) is None
    assert fixture.projection_repo.find_by_relation_id(relation_id) == []


@pytest.mark.database
def test_materialize_support_claim_is_idempotent_for_same_claim(
    db_session: Session,
) -> None:
    fixture = _build_fixture(db_session)
    claim_id = _create_claim(
        fixture,
        evidence_seeds=[
            _EvidenceSeed(
                summary="Idempotent support claim evidence.",
                confidence=0.73,
                tier="LITERATURE",
                sentence="The same support claim is materialized twice.",
            ),
        ],
    )

    first = fixture.service.materialize_support_claim(
        claim_id=claim_id,
        research_space_id=fixture.research_space_id,
        projection_origin="EXTRACTION",
    )
    second = fixture.service.materialize_support_claim(
        claim_id=claim_id,
        research_space_id=fixture.research_space_id,
        projection_origin="EXTRACTION",
    )

    assert first.relation is not None
    assert second.relation is not None
    assert second.relation.id == first.relation.id
    relation_id = str(second.relation.id)
    assert len(fixture.projection_repo.find_by_relation_id(relation_id)) == 1
    assert (
        len(
            fixture.relation_repo.list_evidence_for_relation(
                research_space_id=fixture.research_space_id,
                relation_id=relation_id,
            ),
        )
        == 1
    )


@pytest.mark.database
def test_rebuild_relation_projection_refreshes_derived_evidence_after_claim_update(
    db_session: Session,
) -> None:
    fixture = _build_fixture(db_session)
    claim_id = _create_claim(
        fixture,
        evidence_seeds=[
            _EvidenceSeed(
                summary="Original evidence summary.",
                confidence=0.66,
                tier="LITERATURE",
                sentence="Original support evidence sentence.",
            ),
        ],
    )

    materialized = fixture.service.materialize_support_claim(
        claim_id=claim_id,
        research_space_id=fixture.research_space_id,
        projection_origin="EXTRACTION",
    )
    assert materialized.relation is not None
    relation_id = str(materialized.relation.id)

    claim_evidence = (
        db_session.query(ClaimEvidenceModel)
        .filter_by(
            claim_id=UUID(claim_id),
        )
        .one()
    )
    claim_evidence.sentence = "Updated support evidence sentence."
    claim_evidence.metadata_payload = {
        "evidence_summary": "Updated evidence summary.",
        "evidence_tier": "EXPERIMENTAL",
    }
    db_session.flush()

    rebuilt = fixture.service.rebuild_relation_projection(
        relation_id=relation_id,
        research_space_id=fixture.research_space_id,
    )

    assert rebuilt.relation is not None
    evidence_rows = fixture.relation_repo.list_evidence_for_relation(
        research_space_id=fixture.research_space_id,
        relation_id=relation_id,
    )
    assert len(evidence_rows) == 1
    assert evidence_rows[0].evidence_summary == "Updated evidence summary."
    assert evidence_rows[0].evidence_sentence == "Updated support evidence sentence."
    assert evidence_rows[0].evidence_tier == "EXPERIMENTAL"

    projection_rows = fixture.projection_repo.find_by_relation_id(relation_id)
    assert len(projection_rows) == 1
    projection_claim_id = str(projection_rows[0].claim_id)
    assert projection_claim_id == claim_id
    assert fixture.claim_evidence_repo.find_by_claim_id(projection_claim_id)[
        0
    ].sentence == ("Updated support evidence sentence.")


@pytest.mark.database
def test_projection_endpoint_resolution_rejects_cross_space_entities(
    db_session: Session,
) -> None:
    fixture = _build_fixture(db_session)
    claim_id = _create_claim(
        fixture,
        with_participants=False,
        evidence_seeds=[
            _EvidenceSeed(
                summary="Cross-space projection attempt.",
                confidence=0.7,
                tier="LITERATURE",
                sentence="A foreign-space entity should not materialize here.",
            ),
        ],
    )
    claim = fixture.claim_repo.get_by_id(claim_id)
    assert claim is not None

    foreign_user = UserModel(
        email=f"foreign-projection-{uuid4().hex}@example.com",
        username=f"foreign-projection-{uuid4().hex[:8]}",
        full_name="Foreign Projection Tester",
        hashed_password="hashed",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )
    db_session.add(foreign_user)
    db_session.flush()
    foreign_space = ResearchSpaceModel(
        slug=f"foreign-projection-{uuid4().hex[:12]}",
        name="Foreign Projection Space",
        description="Cross-space projection isolation test",
        owner_id=foreign_user.id,
        status="active",
    )
    db_session.add(foreign_space)
    db_session.flush()
    foreign_entity = SqlAlchemyKernelEntityRepository(db_session).create(
        research_space_id=str(foreign_space.id),
        entity_type="PHENOTYPE",
        display_label="Foreign phenotype",
        metadata={},
    )

    participants = [
        KernelClaimParticipant(
            id=uuid4(),
            claim_id=UUID(claim_id),
            research_space_id=UUID(fixture.research_space_id),
            label="MED13",
            entity_id=UUID(fixture.source_entity_id),
            role="SUBJECT",
            position=0,
            qualifiers={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        KernelClaimParticipant(
            id=uuid4(),
            claim_id=UUID(claim_id),
            research_space_id=UUID(fixture.research_space_id),
            label="Foreign phenotype",
            entity_id=foreign_entity.id,
            role="OBJECT",
            position=1,
            qualifiers={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    ]

    with pytest.raises(
        RelationProjectionMaterializationError,
        match="is not in research space",
    ):
        fixture.service._resolve_projection_endpoints(
            claim=claim,
            research_space_id=fixture.research_space_id,
            participants=participants,
        )
