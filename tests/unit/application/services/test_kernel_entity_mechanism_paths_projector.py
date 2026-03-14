"""Unit tests for the entity-mechanism-paths projector."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from src.application.services.kernel.kernel_entity_mechanism_paths_projector import (
    KernelEntityMechanismPathsProjector,
)
from src.application.services.kernel.kernel_reasoning_path_service import (
    KernelReasoningPathService,
)
from src.domain.entities.user import UserRole, UserStatus
from src.graph.core.read_model import (
    GraphReadModelTrigger,
    GraphReadModelUpdate,
    NullGraphReadModelUpdateDispatcher,
)
from src.infrastructure.repositories.kernel.kernel_reasoning_path_repository import (
    SqlAlchemyKernelReasoningPathRepository,
)
from src.models.database.kernel.claim_relations import ClaimRelationModel
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.read_models import EntityMechanismPathModel
from src.models.database.kernel.reasoning_paths import (
    ReasoningPathModel,
    ReasoningPathStepModel,
)
from src.models.database.kernel.relation_claims import RelationClaimModel
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel

pytestmark = pytest.mark.graph


@dataclass(frozen=True)
class _SeededPath:
    space_id: str
    seed_entity_id: str
    end_entity_id: str
    relation_id: str
    path_id: str


def _seed_space(db_session) -> ResearchSpaceModel:
    user = UserModel(
        email=f"mechanism-paths-{uuid4().hex}@example.com",
        username=f"mechanism-paths-{uuid4().hex[:8]}",
        full_name="Mechanism Paths Tester",
        hashed_password="hashed",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.flush()

    space = ResearchSpaceModel(
        slug=f"mechanism-paths-{uuid4().hex[:12]}",
        name="Mechanism Paths Space",
        description="Unit test space for mechanism path indexing",
        owner_id=user.id,
        status="active",
    )
    db_session.add(space)
    db_session.flush()
    return space


def _now() -> datetime:
    return datetime.now(UTC)


def _seed_reasoning_path_fixture(db_session) -> _SeededPath:
    space = _seed_space(db_session)
    seed_entity = EntityModel(
        research_space_id=space.id,
        entity_type="GENE",
        display_label="MED13",
        metadata_payload={},
    )
    end_entity = EntityModel(
        research_space_id=space.id,
        entity_type="PHENOTYPE",
        display_label="Speech delay",
        metadata_payload={},
    )
    db_session.add_all([seed_entity, end_entity])
    db_session.flush()

    root_claim = RelationClaimModel(
        research_space_id=space.id,
        source_document_id=None,
        source_document_ref=None,
        agent_run_id="mechanism-index-root",
        source_type="GENE",
        relation_type="CAUSES",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Mediator dysfunction",
        confidence=0.82,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        polarity="SUPPORT",
        claim_text="MED13 causes a mediator defect.",
        claim_section="results",
        linked_relation_id=None,
        metadata_payload={},
    )
    final_claim = RelationClaimModel(
        research_space_id=space.id,
        source_document_id=None,
        source_document_ref=None,
        agent_run_id="mechanism-index-final",
        source_type="PHENOTYPE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="Mediator dysfunction",
        target_label="Speech delay",
        confidence=0.79,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        polarity="SUPPORT",
        claim_text="Mediator dysfunction is associated with speech delay.",
        claim_section="results",
        linked_relation_id=None,
        metadata_payload={},
    )
    db_session.add_all([root_claim, final_claim])
    db_session.flush()

    claim_relation = ClaimRelationModel(
        research_space_id=space.id,
        source_claim_id=root_claim.id,
        target_claim_id=final_claim.id,
        relation_type="CAUSES",
        agent_run_id="mechanism-index-edge",
        source_document_id=None,
        source_document_ref=None,
        confidence=0.77,
        review_status="ACCEPTED",
        evidence_summary="Mechanism edge",
        metadata_payload={},
    )
    db_session.add(claim_relation)
    db_session.flush()

    path = ReasoningPathModel(
        research_space_id=space.id,
        path_kind="MECHANISM",
        status="ACTIVE",
        start_entity_id=seed_entity.id,
        end_entity_id=end_entity.id,
        root_claim_id=root_claim.id,
        path_length=1,
        confidence=0.77,
        path_signature_hash=f"mechanism-{uuid4().hex}",
        generated_by="test",
        generated_at=_now(),
        metadata_payload={
            "terminal_relation_type": "ASSOCIATED_WITH",
            "supporting_claim_ids": [str(root_claim.id), str(final_claim.id)],
        },
        created_at=_now(),
        updated_at=_now(),
    )
    db_session.add(path)
    db_session.flush()

    step = ReasoningPathStepModel(
        path_id=path.id,
        step_index=0,
        source_claim_id=root_claim.id,
        target_claim_id=final_claim.id,
        claim_relation_id=claim_relation.id,
        canonical_relation_id=None,
        metadata_payload={},
        created_at=_now(),
        updated_at=_now(),
    )
    db_session.add(step)
    db_session.flush()
    return _SeededPath(
        space_id=str(space.id),
        seed_entity_id=str(seed_entity.id),
        end_entity_id=str(end_entity.id),
        relation_id=str(claim_relation.id),
        path_id=str(path.id),
    )


def test_rebuild_populates_entity_mechanism_paths(db_session) -> None:
    seeded = _seed_reasoning_path_fixture(db_session)
    projector = KernelEntityMechanismPathsProjector(db_session)

    rebuilt_rows = projector.rebuild(space_id=seeded.space_id)

    assert rebuilt_rows == 1
    row = db_session.scalar(
        select(EntityMechanismPathModel).where(
            EntityMechanismPathModel.path_id == UUID(seeded.path_id),
        ),
    )
    assert row is not None
    assert str(row.seed_entity_id) == seeded.seed_entity_id
    assert str(row.end_entity_id) == seeded.end_entity_id
    assert row.relation_type == "ASSOCIATED_WITH"
    assert row.supporting_claim_ids


def test_apply_update_removes_stale_mechanism_rows(db_session) -> None:
    seeded = _seed_reasoning_path_fixture(db_session)
    projector = KernelEntityMechanismPathsProjector(db_session)
    projector.rebuild(space_id=seeded.space_id)

    path = db_session.get(ReasoningPathModel, UUID(seeded.path_id))
    assert path is not None
    path.status = "STALE"
    db_session.flush()

    refreshed = projector.apply_update(
        GraphReadModelUpdate(
            model_name="entity_mechanism_paths",
            trigger=GraphReadModelTrigger.PROJECTION_CHANGE,
            relation_ids=(seeded.relation_id,),
            space_id=seeded.space_id,
        ),
    )

    assert refreshed == 1
    assert (
        db_session.scalar(
            select(EntityMechanismPathModel).where(
                EntityMechanismPathModel.path_id == UUID(seeded.path_id),
            ),
        )
        is None
    )


def test_reasoning_path_service_lists_mechanism_candidates_from_index(
    db_session,
) -> None:
    seeded = _seed_reasoning_path_fixture(db_session)
    KernelEntityMechanismPathsProjector(db_session).rebuild(space_id=seeded.space_id)

    service = KernelReasoningPathService(
        reasoning_path_repo=SqlAlchemyKernelReasoningPathRepository(db_session),
        relation_claim_service=SimpleNamespace(),
        claim_participant_service=SimpleNamespace(),
        claim_evidence_service=SimpleNamespace(),
        claim_relation_service=SimpleNamespace(),
        relation_service=SimpleNamespace(),
        read_model_update_dispatcher=NullGraphReadModelUpdateDispatcher(),
        session=db_session,
    )

    candidates = service.list_mechanism_candidates(
        research_space_id=seeded.space_id,
        start_entity_id=seeded.seed_entity_id,
        limit=5,
        offset=0,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.reasoning_path_id == seeded.path_id
    assert candidate.start_entity_id == seeded.seed_entity_id
    assert candidate.end_entity_id == seeded.end_entity_id
    assert candidate.source_type == "GENE"
    assert candidate.target_type == "PHENOTYPE"
    assert candidate.relation_type == "ASSOCIATED_WITH"
    assert candidate.source_label == "MED13"
    assert candidate.target_label == "Speech delay"
