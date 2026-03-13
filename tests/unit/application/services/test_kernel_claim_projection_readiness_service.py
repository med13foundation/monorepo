"""Unit coverage for global claim-backed projection readiness and repair."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.application.services.kernel.kernel_claim_participant_backfill_service import (
    KernelClaimParticipantBackfillService,
)
from src.application.services.kernel.kernel_claim_participant_service import (
    KernelClaimParticipantService,
)
from src.application.services.kernel.kernel_claim_projection_readiness_service import (
    KernelClaimProjectionReadinessService,
)
from src.application.services.kernel.kernel_relation_claim_service import (
    KernelRelationClaimService,
)
from src.application.services.kernel.kernel_relation_projection_invariant_service import (
    KernelRelationProjectionInvariantService,
)
from src.application.services.kernel.kernel_relation_projection_materialization_service import (
    KernelRelationProjectionMaterializationService,
)
from src.database.seeds.seeder import seed_relation_constraints
from src.domain.entities.kernel.relations import RelationEvidenceWrite
from src.domain.ports.concept_port import ConceptPort
from src.infrastructure.repositories.kernel import (
    SqlAlchemyDictionaryRepository,
    SqlAlchemyKernelClaimEvidenceRepository,
    SqlAlchemyKernelClaimParticipantRepository,
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelRelationClaimRepository,
    SqlAlchemyKernelRelationProjectionSourceRepository,
    SqlAlchemyKernelRelationRepository,
)
from src.models.database.base import Base
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from tests.db_reset import reset_database

pytestmark = pytest.mark.graph


class _ConceptPortStub(ConceptPort):
    def create_concept_set(self, **_kwargs):
        raise NotImplementedError

    def list_concept_sets(self, **_kwargs):
        raise NotImplementedError

    def create_concept_member(self, **_kwargs):
        raise NotImplementedError

    def list_concept_members(self, **_kwargs):
        return []

    def create_concept_alias(self, **_kwargs):
        raise NotImplementedError

    def list_concept_aliases(self, **_kwargs):
        raise NotImplementedError

    def resolve_member_by_alias(self, **_kwargs):
        raise NotImplementedError

    def upsert_active_policy(self, **_kwargs):
        raise NotImplementedError

    def get_active_policy(self, **_kwargs):
        raise NotImplementedError

    def list_policies(self, **_kwargs):
        raise NotImplementedError

    def propose_decision(self, **_kwargs):
        raise NotImplementedError

    def set_decision_status(self, *args, **kwargs):
        raise NotImplementedError

    def get_decision(self, **_kwargs):
        raise NotImplementedError

    def list_decisions(self, **_kwargs):
        raise NotImplementedError

    def mark_decision_applied(self, **_kwargs):
        raise NotImplementedError


def _create_user_and_space(db_session):
    user = UserModel(
        email=f"graph-readiness-{uuid4().hex}@example.com",
        username=f"graph-readiness-{uuid4().hex[:8]}",
        full_name="Graph Readiness",
        hashed_password="hashed_password",
        role="admin",
        status="active",
    )
    db_session.add(user)
    db_session.flush()
    space = ResearchSpaceModel(
        slug=f"graph-readiness-{uuid4().hex[:8]}",
        name="Graph Readiness",
        description="Graph readiness test space",
        owner_id=user.id,
        status="active",
        settings={},
        tags=[],
    )
    db_session.add(space)
    db_session.flush()
    return user, space


def _build_services(db_session):
    relation_repo = SqlAlchemyKernelRelationRepository(db_session)
    relation_claim_repo = SqlAlchemyKernelRelationClaimRepository(db_session)
    claim_participant_repo = SqlAlchemyKernelClaimParticipantRepository(db_session)
    claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(db_session)
    entity_repo = SqlAlchemyKernelEntityRepository(
        db_session,
        phi_encryption_service=None,
        enable_phi_encryption=False,
    )
    projection_repo = SqlAlchemyKernelRelationProjectionSourceRepository(db_session)
    relation_claim_service = KernelRelationClaimService(
        relation_claim_repo=relation_claim_repo,
    )
    claim_participant_service = KernelClaimParticipantService(
        claim_participant_repo=claim_participant_repo,
    )
    backfill_service = KernelClaimParticipantBackfillService(
        session=db_session,
        relation_claim_service=relation_claim_service,
        claim_participant_service=claim_participant_service,
        entity_repository=entity_repo,
        concept_service=_ConceptPortStub(),
    )
    materialization_service = KernelRelationProjectionMaterializationService(
        relation_repo=relation_repo,
        relation_claim_repo=relation_claim_repo,
        claim_participant_repo=claim_participant_repo,
        claim_evidence_repo=claim_evidence_repo,
        entity_repo=entity_repo,
        dictionary_repo=SqlAlchemyDictionaryRepository(db_session),
        relation_projection_repo=projection_repo,
    )
    readiness_service = KernelClaimProjectionReadinessService(
        session=db_session,
        relation_projection_invariant_service=(
            KernelRelationProjectionInvariantService(
                relation_projection_repo=projection_repo,
            )
        ),
        relation_projection_materialization_service=materialization_service,
        claim_participant_backfill_service=backfill_service,
    )
    return (
        relation_repo,
        relation_claim_service,
        claim_participant_service,
        KernelRelationProjectionInvariantService(
            relation_projection_repo=projection_repo,
        ),
        materialization_service,
        readiness_service,
    )


def _clear_graph_state(db_session) -> None:
    db_session.rollback()
    reset_database(db_session.get_bind(), Base.metadata)


def _create_entities(db_session, *, space_id: str):
    entity_repo = SqlAlchemyKernelEntityRepository(
        db_session,
        phi_encryption_service=None,
        enable_phi_encryption=False,
    )
    source = entity_repo.create(
        research_space_id=space_id,
        entity_type="GENE",
        display_label="MED13",
        metadata={"kind": "source"},
    )
    target = entity_repo.create(
        research_space_id=space_id,
        entity_type="PHENOTYPE",
        display_label="Cardiomyopathy",
        metadata={"kind": "target"},
    )
    return source, target


def _test_relation_evidence(tag: str) -> RelationEvidenceWrite:
    return RelationEvidenceWrite(
        confidence=0.8,
        evidence_summary=f"{tag} evidence summary",
        evidence_sentence=f"{tag} evidence sentence",
        evidence_sentence_source="artana_generated",
        evidence_sentence_confidence="low",
        evidence_sentence_rationale=None,
        evidence_tier="LITERATURE",
        provenance_id=None,
        source_document_id=None,
        agent_run_id=f"{tag}-run",
    )


def test_readiness_audit_counts_failure_categories(db_session) -> None:
    _clear_graph_state(db_session)
    seed_relation_constraints(db_session)
    _, space = _create_user_and_space(db_session)
    (
        relation_repo,
        claim_service,
        participant_service,
        _invariants,
        _materializer,
        readiness_service,
    ) = _build_services(
        db_session,
    )
    source, target = _create_entities(db_session, space_id=str(space.id))

    orphan_relation = relation_repo.upsert_relation(
        research_space_id=str(space.id),
        source_id=str(source.id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target.id),
    )
    _, invalid_target = _create_entities(db_session, space_id=str(space.id))
    invalid_projection_relation = relation_repo.upsert_relation(
        research_space_id=str(space.id),
        source_id=str(source.id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(invalid_target.id),
    )
    relation_repo.replace_derived_evidence_cache(
        str(orphan_relation.id),
        evidences=[_test_relation_evidence("problematic-orphan")],
    )
    relation_repo.replace_derived_evidence_cache(
        str(invalid_projection_relation.id),
        evidences=[_test_relation_evidence("problematic-invalid-projection")],
    )

    missing_projection_claim = claim_service.create_claim(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="audit-problematic",
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Cardiomyopathy",
        confidence=0.9,
        validation_state="ALLOWED",
        validation_reason="problematic",
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        polarity="SUPPORT",
        claim_text="MED13 associated with cardiomyopathy.",
        claim_section=None,
        linked_relation_id=str(orphan_relation.id),
        metadata={},
    )
    SqlAlchemyKernelRelationProjectionSourceRepository(db_session).create(
        research_space_id=str(space.id),
        relation_id=str(orphan_relation.id),
        claim_id=str(missing_projection_claim.id),
        projection_origin="MANUAL_RELATION",
        source_document_id=None,
        agent_run_id="audit-problematic",
        metadata={"origin": "test"},
    )

    invalid_source_claim = claim_service.create_claim(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="audit-invalid-source",
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Cardiomyopathy",
        confidence=0.7,
        validation_state="ALLOWED",
        validation_reason="invalid projection source",
        persistability="PERSISTABLE",
        claim_status="OPEN",
        polarity="SUPPORT",
        claim_text="Legacy linked support claim.",
        claim_section=None,
        linked_relation_id=None,
        metadata={},
    )
    participant_service.create_participant(
        claim_id=str(invalid_source_claim.id),
        research_space_id=str(space.id),
        role="SUBJECT",
        label="MED13",
        entity_id=str(source.id),
        position=0,
        qualifiers={"origin": "test"},
    )
    participant_service.create_participant(
        claim_id=str(invalid_source_claim.id),
        research_space_id=str(space.id),
        role="OBJECT",
        label="Cardiomyopathy",
        entity_id=str(target.id),
        position=1,
        qualifiers={"origin": "test"},
    )
    SqlAlchemyKernelClaimEvidenceRepository(db_session).create(
        claim_id=str(invalid_source_claim.id),
        source_document_id=None,
        agent_run_id="audit-invalid-source",
        sentence="Legacy evidence exists.",
        sentence_source="artana_generated",
        sentence_confidence="low",
        sentence_rationale=None,
        figure_reference=None,
        table_reference=None,
        confidence=0.6,
        metadata={"origin": "test"},
    )
    SqlAlchemyKernelRelationProjectionSourceRepository(db_session).create(
        research_space_id=str(space.id),
        relation_id=str(invalid_projection_relation.id),
        claim_id=str(invalid_source_claim.id),
        projection_origin="MANUAL_RELATION",
        source_document_id=None,
        agent_run_id="audit-invalid-source",
        metadata={"origin": "test"},
    )
    db_session.commit()

    report = readiness_service.audit(sample_limit=5)

    assert report.ready is False
    assert report.orphan_relations.count == 0
    assert report.missing_claim_participants.count == 1
    assert report.missing_claim_evidence.count == 1
    assert report.linked_relation_mismatches.count == 2
    assert report.invalid_projection_relations.count == 2


def test_readiness_audit_returns_ready_for_clean_projection_graph(db_session) -> None:
    _clear_graph_state(db_session)
    seed_relation_constraints(db_session)
    _, space = _create_user_and_space(db_session)
    (
        relation_repo,
        claim_service,
        participant_service,
        _invariants,
        _materializer,
        readiness_service,
    ) = _build_services(db_session)
    source, target = _create_entities(db_session, space_id=str(space.id))

    relation = relation_repo.upsert_relation(
        research_space_id=str(space.id),
        source_id=str(source.id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target.id),
    )
    relation_repo.replace_derived_evidence_cache(
        str(relation.id),
        evidences=[_test_relation_evidence("clean")],
    )
    claim = claim_service.create_claim(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="audit-clean",
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Cardiomyopathy",
        confidence=0.9,
        validation_state="ALLOWED",
        validation_reason="clean",
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        polarity="SUPPORT",
        claim_text="MED13 associated with cardiomyopathy.",
        claim_section=None,
        linked_relation_id=str(relation.id),
        metadata={
            "source_entity_id": str(source.id),
            "target_entity_id": str(target.id),
        },
    )
    participant_service.create_participant(
        claim_id=str(claim.id),
        research_space_id=str(space.id),
        role="SUBJECT",
        label="MED13",
        entity_id=str(source.id),
        position=0,
        qualifiers={"origin": "test"},
    )
    participant_service.create_participant(
        claim_id=str(claim.id),
        research_space_id=str(space.id),
        role="OBJECT",
        label="Cardiomyopathy",
        entity_id=str(target.id),
        position=1,
        qualifiers={"origin": "test"},
    )
    SqlAlchemyKernelClaimEvidenceRepository(db_session).create(
        claim_id=str(claim.id),
        source_document_id=None,
        agent_run_id="audit-clean",
        sentence="Evidence exists.",
        sentence_source="artana_generated",
        sentence_confidence="low",
        sentence_rationale=None,
        figure_reference=None,
        table_reference=None,
        confidence=0.8,
        metadata={"origin": "test"},
    )
    SqlAlchemyKernelRelationProjectionSourceRepository(db_session).create(
        research_space_id=str(space.id),
        relation_id=str(relation.id),
        claim_id=str(claim.id),
        projection_origin="MANUAL_RELATION",
        source_document_id=None,
        agent_run_id="audit-clean",
        metadata={"origin": "test"},
    )
    db_session.commit()

    report = readiness_service.audit(sample_limit=5)

    assert report.ready is True
    assert report.orphan_relations.count == 0
    assert report.missing_claim_participants.count == 0
    assert report.missing_claim_evidence.count == 0
    assert report.linked_relation_mismatches.count == 0
    assert report.invalid_projection_relations.count == 0


def test_repair_global_backfills_participants_and_leaves_ambiguous_evidence_visible(
    db_session,
) -> None:
    _clear_graph_state(db_session)
    seed_relation_constraints(db_session)
    _, space = _create_user_and_space(db_session)
    (
        relation_repo,
        claim_service,
        _participant_service,
        _invariants,
        _materializer,
        readiness_service,
    ) = _build_services(db_session)
    source, target = _create_entities(db_session, space_id=str(space.id))

    relation_a = relation_repo.upsert_relation(
        research_space_id=str(space.id),
        source_id=str(source.id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target.id),
    )
    relation_repo.replace_derived_evidence_cache(
        str(relation_a.id),
        evidences=[
            RelationEvidenceWrite(
                confidence=0.9,
                evidence_summary="Single-source evidence",
                evidence_sentence="Single-source evidence",
                evidence_sentence_source="artana_generated",
                evidence_sentence_confidence="low",
                evidence_sentence_rationale=None,
                evidence_tier="LITERATURE",
                provenance_id=None,
                source_document_id=None,
                agent_run_id="repair-single",
            ),
        ],
    )
    claim_a = claim_service.create_claim(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="repair-single",
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Cardiomyopathy",
        confidence=0.9,
        validation_state="ALLOWED",
        validation_reason="repair-single",
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        polarity="SUPPORT",
        claim_text="Single-source support claim.",
        claim_section=None,
        linked_relation_id=str(relation_a.id),
        metadata={
            "source_entity_id": str(source.id),
            "target_entity_id": str(target.id),
        },
    )
    SqlAlchemyKernelRelationProjectionSourceRepository(db_session).create(
        research_space_id=str(space.id),
        relation_id=str(relation_a.id),
        claim_id=str(claim_a.id),
        projection_origin="CLAIM_RESOLUTION",
        source_document_id=None,
        agent_run_id="repair-single",
        metadata={"origin": "test"},
    )

    _, target_b = _create_entities(db_session, space_id=str(space.id))
    relation_b = relation_repo.upsert_relation(
        research_space_id=str(space.id),
        source_id=str(source.id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_b.id),
    )
    relation_repo.replace_derived_evidence_cache(
        str(relation_b.id),
        evidences=[
            RelationEvidenceWrite(
                confidence=0.85,
                evidence_summary="Ambiguous cached evidence",
                evidence_sentence="Ambiguous cached evidence",
                evidence_sentence_source="artana_generated",
                evidence_sentence_confidence="low",
                evidence_sentence_rationale=None,
                evidence_tier="LITERATURE",
                provenance_id=None,
                source_document_id=None,
                agent_run_id="repair-ambiguous",
            ),
        ],
    )
    claim_b1 = claim_service.create_claim(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="repair-ambiguous",
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Cardiomyopathy",
        confidence=0.8,
        validation_state="ALLOWED",
        validation_reason="repair-ambiguous-1",
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        polarity="SUPPORT",
        claim_text="Ambiguous support claim 1.",
        claim_section=None,
        linked_relation_id=str(relation_b.id),
        metadata={
            "source_entity_id": str(source.id),
            "target_entity_id": str(target_b.id),
        },
    )
    claim_b2 = claim_service.create_claim(
        research_space_id=str(space.id),
        source_document_id=None,
        agent_run_id="repair-ambiguous",
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Cardiomyopathy",
        confidence=0.81,
        validation_state="ALLOWED",
        validation_reason="repair-ambiguous-2",
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        polarity="SUPPORT",
        claim_text="Ambiguous support claim 2.",
        claim_section=None,
        linked_relation_id=str(relation_b.id),
        metadata={
            "source_entity_id": str(source.id),
            "target_entity_id": str(target_b.id),
        },
    )
    projection_repo = SqlAlchemyKernelRelationProjectionSourceRepository(db_session)
    projection_repo.create(
        research_space_id=str(space.id),
        relation_id=str(relation_b.id),
        claim_id=str(claim_b1.id),
        projection_origin="CLAIM_RESOLUTION",
        source_document_id=None,
        agent_run_id="repair-ambiguous",
        metadata={"origin": "test"},
    )
    projection_repo.create(
        research_space_id=str(space.id),
        relation_id=str(relation_b.id),
        claim_id=str(claim_b2.id),
        projection_origin="CLAIM_RESOLUTION",
        source_document_id=None,
        agent_run_id="repair-ambiguous",
        metadata={"origin": "test"},
    )
    db_session.commit()

    repair_summary = readiness_service.repair_global(dry_run=False)
    db_session.commit()
    report = readiness_service.audit(sample_limit=5)

    assert repair_summary.participant_backfill.created_participants == 6
    assert repair_summary.materialized_claims >= 3
    assert report.ready is False
    assert report.missing_claim_participants.count == 0
    assert report.missing_claim_evidence.count == 2
    claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(db_session)
    assert len(claim_evidence_repo.find_by_claim_id(str(claim_a.id))) == 1
    assert claim_evidence_repo.find_by_claim_id(str(claim_b1.id)) == []
    assert claim_evidence_repo.find_by_claim_id(str(claim_b2.id)) == []
