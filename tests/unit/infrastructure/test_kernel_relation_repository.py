"""Unit tests for the SQLAlchemy kernel relation repository adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from src.domain.entities.kernel.relations import RelationEvidenceWrite
from src.domain.entities.user import UserRole, UserStatus
from src.infrastructure.repositories.kernel.kernel_relation_repository import (
    SqlAlchemyKernelRelationRepository,
)
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.provenance import ProvenanceModel
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel
from src.models.database.kernel.spaces import GraphSpaceModel, GraphSpaceStatusEnum
from src.models.database.research_space import ResearchSpaceModel, SpaceStatusEnum
from src.models.database.user import UserModel
from tests.graph_seed_helpers import ensure_relation_constraint, ensure_relation_types

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _as_optional_uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    return UUID(value)


def _create_relation(  # noqa: PLR0913
    repository: SqlAlchemyKernelRelationRepository,
    *,
    research_space_id: str,
    source_id: str,
    relation_type: str,
    target_id: str,
    confidence: float = 0.5,
    evidence_summary: str | None = None,
    evidence_sentence: str | None = None,
    evidence_sentence_source: str | None = None,
    evidence_sentence_confidence: str | None = None,
    evidence_sentence_rationale: str | None = None,
    evidence_tier: str | None = "COMPUTATIONAL",
    curation_status: str = "DRAFT",
    provenance_id: str | None = None,
    source_document_id: str | None = None,
    agent_run_id: str | None = None,
):
    relation = repository.upsert_relation(
        research_space_id=research_space_id,
        source_id=source_id,
        relation_type=relation_type,
        target_id=target_id,
        curation_status=curation_status,
        provenance_id=provenance_id,
    )
    existing = repository.list_evidence_for_relation(
        research_space_id=research_space_id,
        relation_id=str(relation.id),
        claim_backed_only=False,
    )
    new_evidence = RelationEvidenceWrite(
        confidence=max(0.0, min(confidence, 1.0)),
        evidence_summary=evidence_summary,
        evidence_sentence=evidence_sentence,
        evidence_sentence_source=evidence_sentence_source,
        evidence_sentence_confidence=evidence_sentence_confidence,
        evidence_sentence_rationale=evidence_sentence_rationale,
        evidence_tier=evidence_tier or "COMPUTATIONAL",
        provenance_id=_as_optional_uuid(provenance_id),
        source_document_id=_as_optional_uuid(source_document_id),
        agent_run_id=agent_run_id,
    )
    evidence_rows = [
        RelationEvidenceWrite(
            confidence=float(row.confidence),
            evidence_summary=row.evidence_summary,
            evidence_sentence=row.evidence_sentence,
            evidence_sentence_source=row.evidence_sentence_source,
            evidence_sentence_confidence=row.evidence_sentence_confidence,
            evidence_sentence_rationale=row.evidence_sentence_rationale,
            evidence_tier=row.evidence_tier,
            provenance_id=row.provenance_id,
            source_document_id=row.source_document_id,
            agent_run_id=row.agent_run_id,
        )
        for row in existing
    ]
    existing_keys = {
        (
            float(row.confidence),
            row.evidence_summary,
            row.evidence_sentence,
            row.evidence_sentence_source,
            row.evidence_sentence_confidence,
            row.evidence_sentence_rationale,
            row.evidence_tier,
            str(row.provenance_id) if row.provenance_id is not None else None,
            str(row.source_document_id) if row.source_document_id is not None else None,
            row.agent_run_id,
        )
        for row in existing
    }
    new_key = (
        float(new_evidence.confidence),
        new_evidence.evidence_summary,
        new_evidence.evidence_sentence,
        new_evidence.evidence_sentence_source,
        new_evidence.evidence_sentence_confidence,
        new_evidence.evidence_sentence_rationale,
        new_evidence.evidence_tier,
        (
            str(new_evidence.provenance_id)
            if new_evidence.provenance_id is not None
            else None
        ),
        (
            str(new_evidence.source_document_id)
            if new_evidence.source_document_id is not None
            else None
        ),
        new_evidence.agent_run_id,
    )
    if new_key not in existing_keys:
        evidence_rows.append(new_evidence)
    return repository.replace_derived_evidence_cache(
        str(relation.id),
        evidences=evidence_rows,
    )


SqlAlchemyKernelRelationRepository.create = _create_relation  # type: ignore[attr-defined]


def _seed_space_and_entities(
    db_session: Session,
    *,
    settings: dict[str, object] | None = None,
) -> tuple[UUID, UUID, UUID]:
    ensure_relation_constraint(
        db_session,
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
    )
    ensure_relation_constraint(
        db_session,
        source_type="GENE",
        relation_type="SUPPORTS",
        target_type="PHENOTYPE",
    )
    ensure_relation_types(db_session, "SUPPORTS", "CAUSES")
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
    db_session.add(
        GraphSpaceModel(
            id=research_space_id,
            slug=f"graph-space-{str(research_space_id).replace('-', '')[:8]}",
            name="Graph Test Space",
            description="Graph registry entry for relation repository tests",
            owner_id=owner_id,
            status=GraphSpaceStatusEnum.ACTIVE,
            settings=settings or {},
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


def _seed_provenance_ids(
    db_session: Session,
    *,
    research_space_id: UUID,
    count: int,
) -> list[UUID]:
    provenance_ids: list[UUID] = []
    for idx in range(count):
        provenance_id = uuid4()
        db_session.add(
            ProvenanceModel(
                id=provenance_id,
                research_space_id=research_space_id,
                source_type="AI_EXTRACTION",
                source_ref=f"test://source/{idx}",
                raw_input={"seed_index": idx},
            ),
        )
        provenance_ids.append(provenance_id)
    db_session.flush()
    return provenance_ids


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

    relation_rows = db_session.scalars(
        select(RelationModel).where(
            RelationModel.research_space_id == research_space_id,
        ),
    ).all()
    assert len(relation_rows) == 1
    evidence_rows = db_session.scalars(
        select(RelationEvidenceModel).where(
            RelationEvidenceModel.relation_id == first.id,
        ),
    ).all()
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

    source_document_id = str(uuid4())
    first = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.91,
        evidence_summary="Same supporting statement",
        evidence_sentence="MED13 is associated with disease in cohort A.",
        evidence_tier="LITERATURE",
        source_document_id=source_document_id,
    )
    second = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.91,
        evidence_summary="Same supporting statement",
        evidence_sentence="MED13 is associated with disease in cohort A.",
        evidence_tier="LITERATURE",
        source_document_id=source_document_id,
    )

    assert first.id == second.id
    assert second.source_count == 1
    evidence_rows = db_session.scalars(
        select(RelationEvidenceModel).where(
            RelationEvidenceModel.relation_id == second.id,
        ),
    ).all()
    assert len(evidence_rows) == 1


def test_create_dedupe_does_not_collapse_distinct_source_documents(
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
        evidence_sentence="MED13 is associated with disease in cohort A.",
        evidence_tier="LITERATURE",
        source_document_id=str(uuid4()),
    )
    second = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.91,
        evidence_summary="Same supporting statement",
        evidence_sentence="MED13 is associated with disease in cohort A.",
        evidence_tier="LITERATURE",
        source_document_id=str(uuid4()),
    )

    assert first.id == second.id
    assert second.source_count == 2
    evidence_rows = db_session.scalars(
        select(RelationEvidenceModel).where(
            RelationEvidenceModel.relation_id == second.id,
        ),
    ).all()
    assert len(evidence_rows) == 2


def test_create_dedupe_includes_evidence_sentence(
    db_session: Session,
) -> None:
    research_space_id, source_entity_id, target_entity_id = _seed_space_and_entities(
        db_session,
    )
    repository = SqlAlchemyKernelRelationRepository(db_session)
    source_document_id = str(uuid4())

    first = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.75,
        evidence_summary="Shared summary",
        evidence_sentence="Sentence A: MED13 is associated with disease.",
        evidence_tier="LITERATURE",
        source_document_id=source_document_id,
    )
    second = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.75,
        evidence_summary="Shared summary",
        evidence_sentence="Sentence A: MED13 is associated with disease.",
        evidence_tier="LITERATURE",
        source_document_id=source_document_id,
    )
    third = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.75,
        evidence_summary="Shared summary",
        evidence_sentence="Sentence B: MED13 variants are implicated in disease.",
        evidence_tier="LITERATURE",
        source_document_id=source_document_id,
    )

    assert first.id == second.id == third.id
    assert third.source_count == 2
    evidence_rows = db_session.scalars(
        select(RelationEvidenceModel).where(
            RelationEvidenceModel.relation_id == third.id,
        ),
    ).all()
    assert len(evidence_rows) == 2


def test_create_dedupe_includes_evidence_sentence_provenance_fields(
    db_session: Session,
) -> None:
    research_space_id, source_entity_id, target_entity_id = _seed_space_and_entities(
        db_session,
    )
    repository = SqlAlchemyKernelRelationRepository(db_session)
    source_document_id = str(uuid4())

    first = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.64,
        evidence_summary="Shared summary",
        evidence_sentence="Generated sentence for optional relation.",
        evidence_sentence_source="artana_generated",
        evidence_sentence_confidence="low",
        evidence_sentence_rationale="No direct cooccurrence span found in source text.",
        evidence_tier="COMPUTATIONAL",
        source_document_id=source_document_id,
    )
    second = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.64,
        evidence_summary="Shared summary",
        evidence_sentence="Generated sentence for optional relation.",
        evidence_sentence_source="artana_generated",
        evidence_sentence_confidence="low",
        evidence_sentence_rationale="No direct cooccurrence span found in source text.",
        evidence_tier="COMPUTATIONAL",
        source_document_id=source_document_id,
    )
    third = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.64,
        evidence_summary="Shared summary",
        evidence_sentence="Generated sentence for optional relation.",
        evidence_sentence_source="artana_generated",
        evidence_sentence_confidence="medium",
        evidence_sentence_rationale=(
            "Generated from relation context and abstract fallback for reviewer aid."
        ),
        evidence_tier="COMPUTATIONAL",
        source_document_id=source_document_id,
    )

    assert first.id == second.id == third.id
    assert third.source_count == 2
    evidence_rows = db_session.scalars(
        select(RelationEvidenceModel).where(
            RelationEvidenceModel.relation_id == third.id,
        ),
    ).all()
    assert len(evidence_rows) == 2


def test_create_persists_non_uuid_agent_run_id(db_session: Session) -> None:
    research_space_id, source_entity_id, target_entity_id = _seed_space_and_entities(
        db_session,
    )
    repository = SqlAlchemyKernelRelationRepository(db_session)

    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.91,
        evidence_tier="LITERATURE",
        agent_run_id="graph:connection:sha256:aa11bb22",
    )

    evidence_rows = db_session.scalars(
        select(RelationEvidenceModel).where(
            RelationEvidenceModel.relation_id == relation.id,
        ),
    ).all()
    assert len(evidence_rows) == 1
    assert evidence_rows[0].agent_run_id == "graph:connection:sha256:aa11bb22"


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
    provenance_ids = _seed_provenance_ids(
        db_session,
        research_space_id=research_space_id,
        count=5,
    )
    repository = SqlAlchemyKernelRelationRepository(db_session)

    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=1.0,
        evidence_tier="COMPUTATIONAL",
        provenance_id=str(provenance_ids[0]),
    )
    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=1.0,
        evidence_tier="COMPUTATIONAL",
        provenance_id=str(provenance_ids[1]),
    )
    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=1.0,
        evidence_tier="COMPUTATIONAL",
        provenance_id=str(provenance_ids[2]),
    )
    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=1.0,
        evidence_tier="COMPUTATIONAL",
        provenance_id=str(provenance_ids[3]),
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
        provenance_id=str(provenance_ids[4]),
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
    provenance_ids = _seed_provenance_ids(
        db_session,
        research_space_id=research_space_id,
        count=3,
    )
    repository = SqlAlchemyKernelRelationRepository(db_session)

    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.99,
        evidence_tier="LITERATURE",
        provenance_id=str(provenance_ids[0]),
    )
    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.99,
        evidence_tier="LITERATURE",
        provenance_id=str(provenance_ids[1]),
    )
    relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.99,
        evidence_tier="LITERATURE",
        provenance_id=str(provenance_ids[2]),
    )

    assert relation.source_count == 3
    assert relation.curation_status == "DRAFT"


def test_find_by_research_space_filters_by_node_ids(
    db_session: Session,
) -> None:
    research_space_id, source_entity_id, target_entity_id = _seed_space_and_entities(
        db_session,
    )
    other_source_id = uuid4()
    other_target_id = uuid4()
    db_session.add_all(
        [
            EntityModel(
                id=other_source_id,
                research_space_id=research_space_id,
                entity_type="GENE",
                display_label="CNOT1",
                metadata_payload={},
            ),
            EntityModel(
                id=other_target_id,
                research_space_id=research_space_id,
                entity_type="PHENOTYPE",
                display_label="Seizures",
                metadata_payload={},
            ),
        ],
    )
    db_session.flush()

    repository = SqlAlchemyKernelRelationRepository(db_session)
    expected_relation = repository.create(
        research_space_id=str(research_space_id),
        source_id=str(source_entity_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(target_entity_id),
        confidence=0.95,
        evidence_tier="LITERATURE",
    )
    repository.create(
        research_space_id=str(research_space_id),
        source_id=str(other_source_id),
        relation_type="ASSOCIATED_WITH",
        target_id=str(other_target_id),
        confidence=0.93,
        evidence_tier="LITERATURE",
    )

    by_source = repository.find_by_research_space(
        str(research_space_id),
        node_ids=[str(source_entity_id)],
        claim_backed_only=False,
    )
    by_target = repository.find_by_research_space(
        str(research_space_id),
        node_ids=[str(target_entity_id)],
        claim_backed_only=False,
    )

    assert [str(relation.id) for relation in by_source] == [str(expected_relation.id)]
    assert [str(relation.id) for relation in by_target] == [str(expected_relation.id)]
