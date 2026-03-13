"""Unit tests for Artana observability pipeline-resolution helpers."""

from __future__ import annotations

from unittest.mock import Mock, patch

from src.application.services._artana_observability_pipeline_resolution import (
    load_relation_evidence_run_ids,
)


def test_load_relation_evidence_run_ids_uses_graph_service_helper_and_deduplicates() -> (
    None
):
    session = Mock()

    with patch(
        "src.application.services._artana_observability_pipeline_resolution.load_relation_evidence_agent_run_ids_for_document_ids",
        return_value=["run-1", "run-2", "run-1", "", None],
    ) as helper:
        result = load_relation_evidence_run_ids(
            session,
            pipeline_document_ids=["doc-1", "doc-2"],
        )

    helper.assert_called_once_with(
        session,
        document_ids=["doc-1", "doc-2"],
    )
    assert result == ["run-1", "run-2"]


def test_load_relation_evidence_run_ids_short_circuits_empty_document_ids() -> None:
    session = Mock()

    with patch(
        "src.application.services._artana_observability_pipeline_resolution.load_relation_evidence_agent_run_ids_for_document_ids",
        return_value=[],
    ) as helper:
        result = load_relation_evidence_run_ids(
            session,
            pipeline_document_ids=[],
        )

    helper.assert_called_once_with(
        session,
        document_ids=[],
    )
    assert result == []
