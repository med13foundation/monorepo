"""Regression tests for graph fallback guardrail behavior."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.application.agents.services._graph_connection_fallback_helpers import (
    normalize_external_fallback_relations,
    resolve_relations_for_persistence,
)
from src.application.agents.services.entity_recognition_service import (
    EntityRecognitionService,
)
from src.application.services._pipeline_orchestration_graph_fallback_helpers import (
    extract_graph_fallback_relations_from_extraction_summary,
)
from src.domain.agents.contracts.graph_connection import (
    ProposedRelation,
    RejectedCandidate,
)


@dataclass(frozen=True)
class _StubExtractionSummary:
    derived_graph_fallback_relation_payloads: tuple[dict[str, object], ...]


def _rejected_detail(*, reason: str) -> dict[str, object]:
    return {
        "reason": reason,
        "payload": {
            "source_entity_id": str(uuid4()),
            "target_entity_id": str(uuid4()),
            "relation_type": "ASSOCIATED_WITH",
            "confidence": 0.8,
            "validation_state": "ALLOWED",
        },
    }


def _raw_fallback_payload(
    *,
    seed_entity_id: str,
    reason: str,
) -> dict[str, object]:
    return {
        "seed_entity_id": seed_entity_id,
        "source_id": str(uuid4()),
        "relation_type": "ASSOCIATED_WITH",
        "target_id": str(uuid4()),
        "confidence": 0.48,
        "reason": reason,
        "validation_state": "ALLOWED",
    }


def test_entity_recognition_fallback_payloads_skip_blocked_reasons() -> None:
    seed_entity_id = str(uuid4())
    payloads = EntityRecognitionService._build_graph_fallback_relation_payloads(
        seed_entity_ids=(seed_entity_id,),
        rejected_relation_details=(
            _rejected_detail(reason="relation_evidence_span_missing"),
            _rejected_detail(reason="relation_endpoint_shape_rejected"),
            _rejected_detail(reason="relation_candidate_low_support"),
        ),
    )

    assert payloads
    assert all(
        payload["reason"] == "relation_candidate_low_support" for payload in payloads
    )


def test_pipeline_graph_fallback_extractor_skips_blocked_reasons() -> None:
    seed_entity_id = str(uuid4())
    summary = _StubExtractionSummary(
        derived_graph_fallback_relation_payloads=(
            _raw_fallback_payload(
                seed_entity_id=seed_entity_id,
                reason="relation_evidence_span_missing",
            ),
            _raw_fallback_payload(
                seed_entity_id=seed_entity_id,
                reason="relation_candidate_low_support",
            ),
        ),
    )

    fallback_relations = extract_graph_fallback_relations_from_extraction_summary(
        summary,
    )

    assert seed_entity_id in fallback_relations
    assert len(fallback_relations[seed_entity_id]) == 1
    assert (
        "relation_candidate_low_support"
        in fallback_relations[seed_entity_id][0].reasoning
    )


def test_graph_connection_rejected_candidate_promotion_skips_blocked_reasons() -> None:
    blocked_candidate = RejectedCandidate(
        source_id=str(uuid4()),
        relation_type="ASSOCIATED_WITH",
        target_id=str(uuid4()),
        reason="relation_evidence_span_missing",
        confidence=0.44,
    )
    allowed_candidate = RejectedCandidate(
        source_id=str(uuid4()),
        relation_type="ASSOCIATED_WITH",
        target_id=str(uuid4()),
        reason="insufficient_supporting_documents",
        confidence=0.43,
    )

    promoted_relations, promoted_count, extraction_fallback_count = (
        resolve_relations_for_persistence(
            contract_proposed_relations=(),
            contract_rejected_candidates=(blocked_candidate, allowed_candidate),
        )
    )

    assert len(promoted_relations) == 1
    assert promoted_count == 1
    assert extraction_fallback_count == 0
    assert "insufficient_supporting_documents" in promoted_relations[0].evidence_summary


def test_graph_connection_external_fallback_normalizer_skips_blocked_payloads() -> None:
    blocked_relation = ProposedRelation(
        source_id=str(uuid4()),
        relation_type="ASSOCIATED_WITH",
        target_id=str(uuid4()),
        confidence=0.45,
        evidence_summary=(
            "Promoted from extraction relation candidate "
            "(ALLOWED:relation_evidence_span_missing)"
        ),
        evidence_tier="COMPUTATIONAL",
        supporting_provenance_ids=[],
        supporting_document_count=0,
        reasoning=(
            "Fail-open graph fallback using extraction-stage relation candidate "
            "(ALLOWED:relation_evidence_span_missing)."
        ),
    )
    allowed_relation = ProposedRelation(
        source_id=str(uuid4()),
        relation_type="ASSOCIATED_WITH",
        target_id=str(uuid4()),
        confidence=0.45,
        evidence_summary="Promoted relation candidate for review.",
        evidence_tier="COMPUTATIONAL",
        supporting_provenance_ids=[],
        supporting_document_count=0,
        reasoning="Fallback relation candidate.",
    )

    normalized_relations = normalize_external_fallback_relations(
        (blocked_relation, allowed_relation),
    )

    assert len(normalized_relations) == 1
    assert normalized_relations[0].source_id == allowed_relation.source_id
