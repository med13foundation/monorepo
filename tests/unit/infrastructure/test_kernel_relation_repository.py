"""Unit tests for the SQLAlchemy kernel relation repository adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from src.domain.entities.user import UserRole, UserStatus
from src.infrastructure.repositories.kernel.kernel_relation_repository import (
    SqlAlchemyKernelRelationRepository,
)
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel
from src.models.database.research_space import ResearchSpaceModel, SpaceStatusEnum
from src.models.database.user import UserModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _seed_space_and_entities(
    db_session: Session,
    *,
    settings: dict[str, object] | None = None,
) -> tuple[UUID, UUID, UUID]:
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
            settings=settings or {},
            tags=[],
        ),
    )

    source_entity_id = uuid4()
    target_entity_id = uuid4()
    db_session.add_all(
        [
            EntityModel(
                id=source_entity_id,
                research_space_id=research_space_id,
                entity_type="GENE",
                display_label="MED13",
                metadata_payload={},
            ),
            EntityModel(
                id=target_entity_id,
                research_space_id=research_space_id,
                entity_type="PHENOTYPE",
                display_label="Neurodevelopmental disorder",
                metadata_payload={},
            ),
        ],
    )
    db_session.flush()

    return research_space_id, source_entity_id, target_entity_id


def test_create_deduplicates_canonical_relation_and_aggregates_evidence(
    db_session: Session,
) -> None:
    research_space_id, source_entity_id, target_entity_id = _seed_space_and_entities(
        db_session,
    )
    repository = SqlAlchemyKernelRelationRepository(db_session)

    first = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.2,
        evidence_tier="LITERATURE",
    )
    second = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.5,
        evidence_tier="EXPERIMENTAL",
    )

    assert first.id == second.id
    assert second.source_count == 2
    assert second.aggregate_confidence == pytest.approx(0.6)
    assert second.highest_evidence_tier == "EXPERIMENTAL"

    relation_rows = db_session.scalars(select(RelationModel)).all()
    assert len(relation_rows) == 1
    evidence_rows = db_session.scalars(select(RelationEvidenceModel)).all()
    assert len(evidence_rows) == 2
    assert all(row.relation_id == relation_rows[0].id for row in evidence_rows)


def test_create_clamps_confidence_and_defaults_evidence_tier(
    db_session: Session,
) -> None:
    research_space_id, source_entity_id, target_entity_id = _seed_space_and_entities(
        db_session,
    )
    repository = SqlAlchemyKernelRelationRepository(db_session)

    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="SUPPORTS",
        target_id=str(target_entity_id),
        confidence=2.4,
        evidence_tier="",
    )
    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="SUPPORTS",
        target_id=str(target_entity_id),
        confidence=-1.0,
        evidence_tier=None,
    )

    assert relation.source_count == 2
    assert relation.aggregate_confidence == pytest.approx(1.0)
    assert relation.highest_evidence_tier == "COMPUTATIONAL"

    evidence_rows = db_session.scalars(
        select(RelationEvidenceModel).where(
            RelationEvidenceModel.relation_id == relation.id,
        ),
    ).all()
    confidences = sorted(float(row.confidence) for row in evidence_rows)
    tiers = {row.evidence_tier for row in evidence_rows}

    assert confidences == [0.0, 1.0]
    assert tiers == {"COMPUTATIONAL"}


def test_create_skips_duplicate_evidence_rows(
    db_session: Session,
) -> None:
    research_space_id, source_entity_id, target_entity_id = _seed_space_and_entities(
        db_session,
    )
    repository = SqlAlchemyKernelRelationRepository(db_session)

    first = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.91,
        evidence_summary="Same supporting statement",
        evidence_tier="LITERATURE",
    )
    second = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.91,
        evidence_summary="Same supporting statement",
        evidence_tier="LITERATURE",
    )

    assert first.id == second.id
    assert second.source_count == 1
    evidence_rows = db_session.scalars(
        select(RelationEvidenceModel).where(
            RelationEvidenceModel.relation_id == second.id,
        ),
    ).all()
    assert len(evidence_rows) == 1


def test_create_auto_promotes_when_default_thresholds_are_met(
    db_session: Session,
) -> None:
    research_space_id, source_entity_id, target_entity_id = _seed_space_and_entities(
        db_session,
    )
    repository = SqlAlchemyKernelRelationRepository(db_session)

    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.96,
        evidence_tier="LITERATURE",
    )
    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.97,
        evidence_tier="LITERATURE",
    )
    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.98,
        evidence_tier="LITERATURE",
    )

    assert relation.source_count == 3
    assert relation.aggregate_confidence >= 0.95
    assert relation.curation_status == "APPROVED"


def test_create_applies_stricter_threshold_for_computational_only_evidence(
    db_session: Session,
) -> None:
    research_space_id, source_entity_id, target_entity_id = _seed_space_and_entities(
        db_session,
    )
    repository = SqlAlchemyKernelRelationRepository(db_session)

    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=1.0,
        evidence_tier="COMPUTATIONAL",
        provenance_id=str(uuid4()),
    )
    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=1.0,
        evidence_tier="COMPUTATIONAL",
        provenance_id=str(uuid4()),
    )
    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=1.0,
        evidence_tier="COMPUTATIONAL",
        provenance_id=str(uuid4()),
    )
    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=1.0,
        evidence_tier="COMPUTATIONAL",
        provenance_id=str(uuid4()),
    )

    assert relation.source_count == 4
    assert relation.curation_status == "DRAFT"

    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=1.0,
        evidence_tier="COMPUTATIONAL",
        provenance_id=str(uuid4()),
    )

    assert relation.source_count == 5
    assert relation.curation_status == "APPROVED"


def test_create_logs_non_promotion_decision_reason(
    db_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    research_space_id, source_entity_id, target_entity_id = _seed_space_and_entities(
        db_session,
    )
    repository = SqlAlchemyKernelRelationRepository(db_session)

    with caplog.at_level("INFO"):
        repository.create(
            research_space_id=str(research_space_id),
            source_id=str(source_entity_id),
            relation_type="ASSOCIATED_WITH",
            target_id=str(target_entity_id),
            confidence=0.91,
            evidence_tier="LITERATURE",
            provenance_id=str(uuid4()),
        )

    decision_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "relation_auto_promotion"
    ]
    assert decision_records
    decision = decision_records[-1]
    assert getattr(decision, "auto_promotion_outcome", None) == "kept"
    assert getattr(decision, "auto_promotion_reason", None) in {
        "insufficient_distinct_sources",
        "insufficient_aggregate_confidence",
    }


def test_create_logs_promotion_decision_reason(
    db_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    research_space_id, source_entity_id, target_entity_id = _seed_space_and_entities(
        db_session,
    )
    repository = SqlAlchemyKernelRelationRepository(db_session)

    with caplog.at_level("INFO"):
        repository.create(
            research_space_id=str(research_space_id),
            source_id=str(source_entity_id),
            relation_type="ASSOCIATED_WITH",
            target_id=str(target_entity_id),
            confidence=0.96,
            evidence_tier="LITERATURE",
            provenance_id=str(uuid4()),
        )
        repository.create(
            research_space_id=str(research_space_id),
            source_id=str(source_entity_id),
            relation_type="ASSOCIATED_WITH",
            target_id=str(target_entity_id),
            confidence=0.97,
            evidence_tier="LITERATURE",
            provenance_id=str(uuid4()),
        )
        repository.create(
            research_space_id=str(research_space_id),
            source_id=str(source_entity_id),
            relation_type="ASSOCIATED_WITH",
            target_id=str(target_entity_id),
            confidence=0.98,
            evidence_tier="LITERATURE",
            provenance_id=str(uuid4()),
        )

    decision_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "relation_auto_promotion"
    ]
    assert decision_records
    decision = decision_records[-1]
    assert getattr(decision, "auto_promotion_outcome", None) == "promoted"
    assert getattr(decision, "auto_promotion_reason", None) == "thresholds_met"


def test_create_uses_research_space_policy_override_for_auto_promotion(
    db_session: Session,
) -> None:
    research_space_id, source_entity_id, target_entity_id = _seed_space_and_entities(
        db_session,
        settings={
            "relation_auto_promotion": {
                "min_distinct_sources": 1,
                "min_aggregate_confidence": 0.8,
                "require_distinct_documents": False,
                "require_distinct_runs": False,
                "block_if_conflicting_evidence": False,
            },
        },
    )
    repository = SqlAlchemyKernelRelationRepository(db_session)

    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.85,
        evidence_tier="LITERATURE",
        provenance_id=str(uuid4()),
    )

    assert relation.source_count == 1
    assert relation.curation_status == "APPROVED"


def test_create_space_policy_override_can_block_default_auto_promotion(
    db_session: Session,
) -> None:
    research_space_id, source_entity_id, target_entity_id = _seed_space_and_entities(
        db_session,
        settings={
            "custom": {
                "relation_autopromote_min_distinct_sources": 10,
                "relation_autopromote_require_distinct_documents": False,
                "relation_autopromote_require_distinct_runs": False,
            },
        },
    )
    repository = SqlAlchemyKernelRelationRepository(db_session)

    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.99,
        evidence_tier="LITERATURE",
        provenance_id=str(uuid4()),
    )
    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.99,
        evidence_tier="LITERATURE",
        provenance_id=str(uuid4()),
    )
    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.99,
        evidence_tier="LITERATURE",
        provenance_id=str(uuid4()),
    )

    assert relation.source_count == 3
    assert relation.curation_status == "DRAFT"
