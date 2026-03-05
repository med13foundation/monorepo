"""Unit tests for deterministic relation evidence-span helper behavior."""

from __future__ import annotations

from src.application.agents.services._relation_evidence_span_helpers import (
    resolve_relation_evidence_span,
)


def test_relation_evidence_span_uses_valid_candidate_excerpt() -> None:
    result = resolve_relation_evidence_span(
        source_label="MED13",
        target_label="Cardiomyopathy",
        candidate_excerpt="MED13 variants were associated with cardiomyopathy in patients.",
        candidate_locator="abstract:1",
        raw_record={},
    )

    assert result.failure_reason is None
    assert result.span_text is not None
    assert result.metadata["span_source"] == "candidate_excerpt"


def test_relation_evidence_span_derives_from_raw_record_text() -> None:
    result = resolve_relation_evidence_span(
        source_label="CNOT1",
        target_label="DYRK1A",
        candidate_excerpt=None,
        candidate_locator=None,
        raw_record={
            "abstract": (
                "Background only. CNOT1 impairment was linked to DYRK1A signaling "
                "reduction in neuronal tissue."
            ),
        },
    )

    assert result.failure_reason is None
    assert result.span_text is not None
    assert "CNOT1" in result.span_text
    assert result.metadata["span_source"] == "derived"
    assert result.metadata["span_text_field"] == "abstract"


def test_relation_evidence_span_fails_without_text_or_excerpt() -> None:
    result = resolve_relation_evidence_span(
        source_label="MED13",
        target_label="Cardiomyopathy",
        candidate_excerpt=None,
        candidate_locator=None,
        raw_record={},
    )

    assert result.span_text is None
    assert result.failure_reason == "document_text_unavailable"
