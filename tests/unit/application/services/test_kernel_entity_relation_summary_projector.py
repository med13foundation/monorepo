"""Unit tests for the entity-relation summary projector."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select

from src.application.services.kernel.kernel_entity_relation_summary_projector import (
    KernelEntityRelationSummaryProjector,
)
from src.domain.entities.user import UserRole, UserStatus
from src.graph.core.read_model import GraphReadModelTrigger, GraphReadModelUpdate
from src.models.database.kernel.dictionary import (
    DictionaryDomainContextModel,
    DictionaryEntityTypeModel,
    DictionaryRelationTypeModel,
)
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.read_models import EntityRelationSummaryModel
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
        email=f"read-model-{uuid4().hex}@example.com",
        username=f"read-model-{uuid4().hex[:8]}",
        full_name="Read Model Tester",
        hashed_password="hashed",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.flush()

    space = ResearchSpaceModel(
        slug=f"entity-relation-summary-{uuid4().hex[:12]}",
        name="Entity Relation Summary Space",
        description="Unit test space for entity relation summary projector",
        owner_id=user.id,
        status="active",
    )
    db_session.add(space)
    db_session.flush()
    return space


def _seed_dictionary(db_session) -> tuple[str, str, str]:
    suffix = uuid4().hex[:8].upper()
    gene_type = f"RM_GENE_{suffix}"
    phenotype_type = f"RM_PHENOTYPE_{suffix}"
    relation_type = f"RM_ASSOCIATED_WITH_{suffix}"
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
    ensure_relation_constraint(
        db_session,
        source_type=phenotype_type,
        relation_type=relation_type,
        target_type=gene_type,
        domain_context="general",
        requires_evidence=False,
    )
    return gene_type, phenotype_type, relation_type


def _seed_relation_bundle(
    db_session,
    *,
    space_id,
    source_id,
    target_id,
    relation_type: str,
    target_type: str,
) -> tuple[UUID, UUID]:
    claim = RelationClaimModel(
        research_space_id=space_id,
        source_document_id=None,
        source_document_ref=None,
        agent_run_id="read-model-test",
        source_type="pubmed",
        relation_type=relation_type,
        target_type=target_type,
        source_label="MED13",
        target_label="Cardiomyopathy",
        confidence=0.7,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        polarity="SUPPORT",
        claim_text="MED13 is associated with cardiomyopathy.",
        claim_section="results",
        linked_relation_id=None,
        metadata_payload={},
    )
    db_session.add(claim)
    db_session.flush()

    relation = RelationModel(
        research_space_id=space_id,
        source_id=source_id,
        relation_type=relation_type,
        target_id=target_id,
        aggregate_confidence=0.7,
        source_count=1,
        highest_evidence_tier="LITERATURE",
        curation_status="DRAFT",
        provenance_id=None,
    )
    db_session.add(relation)
    db_session.flush()

    projection = RelationProjectionSourceModel(
        research_space_id=space_id,
        relation_id=relation.id,
        claim_id=claim.id,
        projection_origin="CLAIM_RESOLUTION",
        source_document_id=None,
        source_document_ref=None,
        agent_run_id="read-model-test",
        metadata_payload={},
    )
    db_session.add(projection)
    db_session.flush()
    return relation.id, claim.id


def test_rebuild_populates_entity_relation_summary(db_session) -> None:
    gene_type, phenotype_type, relation_type = _seed_dictionary(db_session)
    space = _seed_space(db_session)
    source = EntityModel(
        research_space_id=space.id,
        entity_type=gene_type,
        display_label="MED13",
        metadata_payload={},
    )
    target_a = EntityModel(
        research_space_id=space.id,
        entity_type=phenotype_type,
        display_label="Cardiomyopathy",
        metadata_payload={},
    )
    target_b = EntityModel(
        research_space_id=space.id,
        entity_type=phenotype_type,
        display_label="Arrhythmia",
        metadata_payload={},
    )
    db_session.add_all([source, target_a, target_b])
    db_session.flush()

    _seed_relation_bundle(
        db_session,
        space_id=space.id,
        source_id=source.id,
        target_id=target_a.id,
        relation_type=relation_type,
        target_type=phenotype_type,
    )
    _seed_relation_bundle(
        db_session,
        space_id=space.id,
        source_id=source.id,
        target_id=target_b.id,
        relation_type=relation_type,
        target_type=phenotype_type,
    )
    _seed_relation_bundle(
        db_session,
        space_id=space.id,
        source_id=target_a.id,
        target_id=source.id,
        relation_type=relation_type,
        target_type=gene_type,
    )

    projector = KernelEntityRelationSummaryProjector(db_session)

    rebuilt_rows = projector.rebuild(space_id=str(space.id))

    assert rebuilt_rows == 3
    summary = db_session.get(EntityRelationSummaryModel, source.id)
    assert summary is not None
    assert summary.outgoing_relation_count == 2
    assert summary.incoming_relation_count == 1
    assert summary.total_relation_count == 3
    assert summary.distinct_relation_type_count == 1
    assert summary.support_claim_count == 3
    assert summary.last_projection_at is not None


def test_apply_update_removes_summary_when_relations_are_deleted(db_session) -> None:
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

    relation_id, _claim_id = _seed_relation_bundle(
        db_session,
        space_id=space.id,
        source_id=source.id,
        target_id=target.id,
        relation_type=relation_type,
        target_type=phenotype_type,
    )
    projector = KernelEntityRelationSummaryProjector(db_session)
    assert projector.rebuild(space_id=str(space.id)) == 2

    db_session.execute(
        delete(RelationProjectionSourceModel).where(
            RelationProjectionSourceModel.relation_id == relation_id,
        ),
    )
    db_session.execute(delete(RelationModel).where(RelationModel.id == relation_id))
    db_session.flush()

    updated_rows = projector.apply_update(
        GraphReadModelUpdate(
            model_name="entity_relation_summary",
            trigger=GraphReadModelTrigger.PROJECTION_CHANGE,
            entity_ids=(str(source.id), str(target.id)),
            space_id=str(space.id),
        ),
    )

    assert updated_rows == 2
    assert db_session.get(EntityRelationSummaryModel, source.id) is None
    assert db_session.get(EntityRelationSummaryModel, target.id) is None
    assert db_session.scalars(select(EntityRelationSummaryModel)).all() == []
