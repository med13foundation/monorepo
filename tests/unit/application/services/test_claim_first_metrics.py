"""Unit tests for claim-first metrics helpers."""

from __future__ import annotations

import logging

from src.application.services.claim_first_metrics import (
    emit_claim_first_extraction_metrics,
    emit_graph_filter_preset_usage,
    get_metric_counters_snapshot,
    infer_graph_trust_preset,
    reset_metric_counters_for_tests,
)


def setup_function() -> None:
    reset_metric_counters_for_tests()


def test_infer_graph_trust_preset() -> None:
    assert infer_graph_trust_preset(None) == "ALL"
    assert infer_graph_trust_preset([]) == "ALL"
    assert infer_graph_trust_preset(["APPROVED"]) == "APPROVED_ONLY"
    assert infer_graph_trust_preset(["DRAFT", "UNDER_REVIEW"]) == "PENDING_REVIEW"
    assert infer_graph_trust_preset(["REJECTED", "RETRACTED"]) == "REJECTED"
    assert infer_graph_trust_preset(["DRAFT"]) == "CUSTOM"


def test_emit_claim_first_extraction_metrics_updates_counters() -> None:
    emit_claim_first_extraction_metrics(
        research_space_id="space-1",
        source_document_id="doc-1",
        claims_created=5,
        claims_non_persistable=2,
        relations_draft_created=3,
        relation_claims_queued_for_review=2,
        research_space_settings=None,
    )
    snapshot = get_metric_counters_snapshot()
    assert snapshot["claims_created_total"] == 5
    assert snapshot["claims_non_persistable_total"] == 2
    assert snapshot["relations_draft_created_total"] == 3
    assert snapshot["curation_queue_relation_claim_total"] == 2


def test_emit_graph_filter_preset_usage_updates_counter() -> None:
    emit_graph_filter_preset_usage(endpoint="subgraph", curation_statuses=None)
    emit_graph_filter_preset_usage(
        endpoint="graph_search",
        curation_statuses=["APPROVED"],
    )
    snapshot = get_metric_counters_snapshot()
    assert snapshot["graph_filter_preset_usage"] == 2


def test_non_persistable_ratio_alert_is_emitted(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="med13.alerts.claim_first"):
        emit_claim_first_extraction_metrics(
            research_space_id="space-1",
            source_document_id="doc-2",
            claims_created=10,
            claims_non_persistable=8,
            relations_draft_created=1,
            relation_claims_queued_for_review=1,
            research_space_settings={
                "claim_non_persistable_baseline_ratio": 0.2,
                "claim_non_persistable_alert_ratio": 0.3,
            },
        )

    assert any(
        "claim_non_persistable_ratio_spike" in record.message
        for record in caplog.records
    )
