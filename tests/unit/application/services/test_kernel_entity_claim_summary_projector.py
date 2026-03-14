"""Unit tests for the entity-claim summary projector."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.application.services.kernel.kernel_entity_claim_summary_projector import (
    KernelEntityClaimSummaryProjector,
)
from src.domain.entities.user import UserRole, UserStatus
from src.graph.core.read_model import GraphReadModelTrigger, GraphReadModelUpdate
from src.models.database.kernel.claim_participants import ClaimParticipantModel
from src.models.database.kernel.dictionary import (
    DictionaryDomainContextModel,
    DictionaryEntityTypeModel,
    DictionaryRelationTypeModel,
)
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.read_models import EntityClaimSummaryModel
from src.models.database.kernel.relation_claims import RelationClaimModel
from src.models.database.kernel.relation_projection_sources import (
    RelationProjectionSourceModel,
)
from src.models.database.kernel.relations import RelationModel
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from tests.graph_seed_helpers import ensure_relation_constraint

pytestmark = pytest.mark.graph


def _seed_space(db_session) -> ResearchSpaceModel:
    user = UserModel(
        email=f"claim-summary-{uuid4().hex}@example.com",
        username=f"claim-summary-{uuid4().hex[:8]}",
        full_name="Claim Summary Tester",
        hashed_password="hashed",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.flush()

    space = ResearchSpaceModel(
        slug=f"entity-claim-summary-{uuid4().hex[:12]}",
        name="Entity Claim Summary Space",
        description="Unit test space for entity claim summary projector",
        owner_id=user.id,
        status="active",
    )
    db_session.add(space)
    db_session.flush()
    return space


def _seed_dictionary(db_session) -> tuple[str, str, str]:
    suffix = uuid4().hex[:8].upper()
    gene_type = f"CS_GENE_{suffix}"
    phenotype_type = f"CS_PHENOTYPE_{suffix}"
    relation_type = f"CS_ASSOCIATED_WITH_{suffix}"
    if db_session.get(DictionaryDomainContextModel, "general") is None:
        db_session.add(
            DictionaryDomainContextModel(
                id="general",
                display_name="General",
                description="General domain",
            ),
        )
        db_session.flush()
    db_session.add_all(
        [
            DictionaryEntityTypeModel(
                id=gene_type,
                display_name="Gene",
                description="Gene",
                domain_context="general",
                expected_properties={},
            ),
            DictionaryEntityTypeModel(
                id=phenotype_type,
                display_name="Phenotype",
                description="Phenotype",
                domain_context="general",
                expected_properties={},
            ),
            DictionaryRelationTypeModel(
                id=relation_type,
                display_name="Associated with",
                description="Association",
                domain_context="general",
                is_directional=True,
                inverse_label=None,
            ),
        ],
    )
    db_session.flush()
    ensure_relation_constraint(
        db_session,
        source_type=gene_type,
        relation_type=relation_type,
        target_type=phenotype_type,
        domain_context="general",
        requires_evidence=False,
    )
    return gene_type, phenotype_type, relation_type


def _seed_linked_relation(
    db_session,
    *,
    space_id,
    source_id,
    target_id,
    relation_type: str,
) -> UUID:
    relation = RelationModel(
        research_space_id=space_id,
        source_id=source_id,
        relation_type=relation_type,
        target_id=target_id,
        aggregate_confidence=0.8,
        source_count=1,
        highest_evidence_tier="LITERATURE",
        curation_status="DRAFT",
        provenance_id=None,
    )
    db_session.add(relation)
    db_session.flush()
    return relation.id


def _seed_claim(
    db_session,
    *,
    space_id,
    relation_type: str,
    target_type: str,
    source_label: str,
    target_label: str,
    participant_entity_ids: tuple[UUID, ...],
    claim_status: str,
    polarity: str,
    linked_relation_id: UUID | None = None,
    projected: bool = False,
) -> UUID:
    claim = RelationClaimModel(
        research_space_id=space_id,
        source_document_id=None,
        source_document_ref=None,
        agent_run_id="claim-summary-test",
        source_type="pubmed",
        relation_type=relation_type,
        target_type=target_type,
        source_label=source_label,
        target_label=target_label,
        confidence=0.8,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status=claim_status,
        polarity=polarity,
        claim_text=f"{source_label} relation claim",
        claim_section="results",
        linked_relation_id=linked_relation_id,
        metadata_payload={},
    )
    db_session.add(claim)
    db_session.flush()

    roles = ("SUBJECT", "OBJECT")
    for index, entity_id in enumerate(participant_entity_ids):
        db_session.add(
            ClaimParticipantModel(
                claim_id=claim.id,
                research_space_id=space_id,
                entity_id=entity_id,
                label=None,
                role=roles[index] if index < len(roles) else "CONTEXT",
                position=index,
                qualifiers={},
            ),
        )
    db_session.flush()

    if projected and linked_relation_id is not None:
        db_session.add(
            RelationProjectionSourceModel(
                research_space_id=space_id,
                relation_id=linked_relation_id,
                claim_id=claim.id,
                projection_origin="CLAIM_RESOLUTION",
                source_document_id=None,
                source_document_ref=None,
                agent_run_id="claim-summary-test",
                metadata_payload={},
            ),
        )
        db_session.flush()

    return claim.id


def test_rebuild_populates_entity_claim_summary(db_session) -> None:
    gene_type, phenotype_type, relation_type = _seed_dictionary(db_session)
    space = _seed_space(db_session)
    source = EntityModel(
        research_space_id=space.id,
        entity_type=gene_type,
        display_label="MED13",
        metadata_payload={},
    )
    target = EntityModel(
        research_space_id=space.id,
        entity_type=phenotype_type,
        display_label="Cardiomyopathy",
        metadata_payload={},
    )
    db_session.add_all([source, target])
    db_session.flush()

    linked_relation_id = _seed_linked_relation(
        db_session,
        space_id=space.id,
        source_id=source.id,
        target_id=target.id,
        relation_type=relation_type,
    )
    _seed_claim(
        db_session,
        space_id=space.id,
        relation_type=relation_type,
        target_type=phenotype_type,
        source_label="MED13",
        target_label="Cardiomyopathy",
        participant_entity_ids=(source.id, target.id),
        claim_status="RESOLVED",
        polarity="SUPPORT",
        linked_relation_id=linked_relation_id,
        projected=True,
    )
    _seed_claim(
        db_session,
        space_id=space.id,
        relation_type=relation_type,
        target_type=phenotype_type,
        source_label="MED13",
        target_label="Arrhythmia",
        participant_entity_ids=(source.id,),
        claim_status="OPEN",
        polarity="HYPOTHESIS",
    )

    projector = KernelEntityClaimSummaryProjector(db_session)

    rebuilt_rows = projector.rebuild(space_id=str(space.id))

    assert rebuilt_rows == 2
    source_summary = db_session.get(EntityClaimSummaryModel, source.id)
    assert source_summary is not None
    assert source_summary.total_claim_count == 2
    assert source_summary.support_claim_count == 1
    assert source_summary.resolved_claim_count == 1
    assert source_summary.open_claim_count == 1
    assert source_summary.linked_claim_count == 1
    assert source_summary.projected_claim_count == 1
    assert source_summary.last_claim_activity_at is not None

    target_summary = db_session.get(EntityClaimSummaryModel, target.id)
    assert target_summary is not None
    assert target_summary.total_claim_count == 1
    assert target_summary.support_claim_count == 1
    assert target_summary.resolved_claim_count == 1
    assert target_summary.open_claim_count == 0
    assert target_summary.linked_claim_count == 1
    assert target_summary.projected_claim_count == 1


def test_apply_update_resolves_entities_from_claim_ids(db_session) -> None:
    gene_type, phenotype_type, relation_type = _seed_dictionary(db_session)
    space = _seed_space(db_session)
    source = EntityModel(
        research_space_id=space.id,
        entity_type=gene_type,
        display_label="MED13",
        metadata_payload={},
    )
    target = EntityModel(
        research_space_id=space.id,
        entity_type=phenotype_type,
        display_label="Cardiomyopathy",
        metadata_payload={},
    )
    db_session.add_all([source, target])
    db_session.flush()

    linked_relation_id = _seed_linked_relation(
        db_session,
        space_id=space.id,
        source_id=source.id,
        target_id=target.id,
        relation_type=relation_type,
    )
    _seed_claim(
        db_session,
        space_id=space.id,
        relation_type=relation_type,
        target_type=phenotype_type,
        source_label="MED13",
        target_label="Cardiomyopathy",
        participant_entity_ids=(source.id, target.id),
        claim_status="RESOLVED",
        polarity="SUPPORT",
        linked_relation_id=linked_relation_id,
        projected=True,
    )
    open_claim_id = _seed_claim(
        db_session,
        space_id=space.id,
        relation_type=relation_type,
        target_type=phenotype_type,
        source_label="MED13",
        target_label="Arrhythmia",
        participant_entity_ids=(source.id,),
        claim_status="OPEN",
        polarity="SUPPORT",
    )

    projector = KernelEntityClaimSummaryProjector(db_session)
    assert projector.rebuild(space_id=str(space.id)) == 2

    claim = db_session.get(RelationClaimModel, open_claim_id)
    assert claim is not None
    claim.claim_status = "RESOLVED"
    db_session.flush()

    updated_rows = projector.apply_update(
        GraphReadModelUpdate(
            model_name="entity_claim_summary",
            trigger=GraphReadModelTrigger.CLAIM_CHANGE,
            claim_ids=(str(open_claim_id),),
            space_id=str(space.id),
        ),
    )

    assert updated_rows == 1
    source_summary = db_session.get(EntityClaimSummaryModel, source.id)
    assert source_summary is not None
    assert source_summary.total_claim_count == 2
    assert source_summary.support_claim_count == 2
    assert source_summary.resolved_claim_count == 2
    assert source_summary.open_claim_count == 0
