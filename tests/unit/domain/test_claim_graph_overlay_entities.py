"""Unit tests for claim overlay domain entity validation rules."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from src.domain.entities.kernel.claim_participants import KernelClaimParticipant
from src.domain.entities.kernel.claim_relations import KernelClaimRelation


def _build_participant(
    *,
    label: str | None = "MED13",
    entity_id: UUID | None = None,
    role: str = "SUBJECT",
) -> KernelClaimParticipant:
    return KernelClaimParticipant(
        id=uuid4(),
        claim_id=uuid4(),
        research_space_id=uuid4(),
        label=label,
        entity_id=entity_id,
        role=role,  # type: ignore[arg-type]
        position=0,
        qualifiers={},
        created_at=datetime.now(UTC),
    )


def _build_claim_relation(
    *,
    source_claim_id: UUID | None = None,
    target_claim_id: UUID | None = None,
    relation_type: str = "SUPPORTS",
    confidence: float = 0.7,
    review_status: str = "PROPOSED",
) -> KernelClaimRelation:
    source_id = source_claim_id or uuid4()
    target_id = target_claim_id or uuid4()
    return KernelClaimRelation(
        id=uuid4(),
        research_space_id=uuid4(),
        source_claim_id=source_id,
        target_claim_id=target_id,
        relation_type=relation_type,  # type: ignore[arg-type]
        confidence=confidence,
        review_status=review_status,  # type: ignore[arg-type]
        metadata_payload={},
        created_at=datetime.now(UTC),
    )


def test_claim_participant_happy_path_with_label_only() -> None:
    participant = _build_participant(label="MED13", entity_id=None, role="SUBJECT")
    assert participant.label == "MED13"
    assert participant.entity_id is None


def test_claim_participant_happy_path_with_entity_only() -> None:
    entity_id = uuid4()
    participant = _build_participant(label=None, entity_id=entity_id, role="OBJECT")
    assert participant.label is None
    assert participant.entity_id == entity_id


def test_claim_participant_requires_label_or_entity_anchor() -> None:
    with pytest.raises(ValueError):
        _build_participant(label=None, entity_id=None)


def test_claim_participant_rejects_whitespace_only_label_without_entity() -> None:
    with pytest.raises(ValueError):
        _build_participant(label="   ", entity_id=None)


def test_claim_participant_rejects_invalid_role_literal() -> None:
    with pytest.raises(ValidationError):
        _build_participant(role="INVALID_ROLE")


def test_claim_participant_entity_model_is_frozen() -> None:
    participant = _build_participant(label="MED13")
    with pytest.raises(ValidationError):
        participant.label = "UPDATED"  # type: ignore[misc]


def test_claim_relation_happy_path() -> None:
    relation = _build_claim_relation(
        relation_type="SUPPORTS",
        confidence=0.7,
        review_status="PROPOSED",
    )
    assert relation.source_claim_id != relation.target_claim_id
    assert relation.confidence == 0.7


def test_claim_relation_disallows_self_loop() -> None:
    claim_id = uuid4()
    with pytest.raises(ValueError):
        _build_claim_relation(source_claim_id=claim_id, target_claim_id=claim_id)


def test_claim_relation_rejects_invalid_relation_type_literal() -> None:
    with pytest.raises(ValidationError):
        _build_claim_relation(relation_type="INVALID_RELATION")


def test_claim_relation_rejects_invalid_review_status_literal() -> None:
    with pytest.raises(ValidationError):
        _build_claim_relation(review_status="INVALID_STATUS")


def test_claim_relation_confidence_boundaries() -> None:
    _build_claim_relation(confidence=0.0)
    _build_claim_relation(confidence=1.0)
    with pytest.raises(ValidationError):
        _build_claim_relation(confidence=-0.01)
    with pytest.raises(ValidationError):
        _build_claim_relation(confidence=1.01)


def test_claim_relation_entity_model_is_frozen() -> None:
    relation = _build_claim_relation()
    with pytest.raises(ValidationError):
        relation.review_status = "ACCEPTED"  # type: ignore[misc]
