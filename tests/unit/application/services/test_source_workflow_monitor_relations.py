"""Focused unit tests for helper-backed workflow-monitor relation queries."""

from __future__ import annotations

from unittest.mock import Mock, patch
from uuid import uuid4

from src.application.services.source_workflow_monitor_service import (
    SourceWorkflowMonitorService,
)
from src.infrastructure.repositories.graph_observability_repository import (
    SourceDocumentRelationRow,
    SpaceGraphSummaryMetrics,
)


def test_load_document_relations_uses_graph_service_helper() -> None:
    session = Mock()
    service = SourceWorkflowMonitorService(session=session, run_progress=None)
    document_id = str(uuid4())

    with patch(
        "src.application.services._source_workflow_monitor_relations.load_source_document_relation_rows",
        return_value=[
            SourceDocumentRelationRow(
                source_document_id=document_id,
                relation_id="relation-1",
                relation_type="ASSOCIATED_WITH",
                curation_status="DRAFT",
                aggregate_confidence=0.75,
                source_entity_id="entity-a",
                target_entity_id="entity-b",
                evidence_id="evidence-1",
                evidence_confidence=0.5,
                evidence_summary="Evidence summary",
                evidence_sentence="Evidence sentence",
                evidence_sentence_source="artana_generated",
                evidence_sentence_confidence="low",
                evidence_sentence_rationale="Generated rationale",
                agent_run_id="run-1",
                source_entity_label="MED13",
                target_entity_label="Cardiomyopathy",
            ),
        ],
    ) as helper:
        rows = service._load_document_relations(
            space_id=uuid4(),
            document_ids={document_id},
            document_context_by_id={
                document_id: {
                    "external_record_id": "pmid:40214304",
                    "source_type": "pubmed",
                    "metadata": {},
                },
            },
            limit=20,
        )

    helper.assert_called_once()
    assert rows[0]["relation_id"] == "relation-1"
    assert rows[0]["evidence_sentence_source"] == "artana_generated"
    assert rows[0]["paper_links"][0]["label"] == "PubMed"


def test_build_graph_summary_uses_graph_service_helper() -> None:
    session = Mock()
    service = SourceWorkflowMonitorService(session=session, run_progress=None)
    source_id = uuid4()
    source_document_ids = [uuid4(), uuid4()]

    with (
        patch.object(
            service,
            "_load_source_document_uuid_ids",
            return_value=source_document_ids,
        ) as load_source_document_ids,
        patch(
            "src.application.services._source_workflow_monitor_relations.load_space_graph_summary_metrics",
            return_value=SpaceGraphSummaryMetrics(
                node_count=12,
                edge_count=34,
                source_edge_count=5,
                top_relation_types=[("ASSOCIATED_WITH", 4), ("TREATS", 1)],
            ),
        ) as helper,
    ):
        summary = service._build_graph_summary(
            space_id=uuid4(),
            source_id=source_id,
        )

    load_source_document_ids.assert_called_once_with(source_id=source_id)
    helper.assert_called_once()
    assert summary == {
        "node_count": 12,
        "edge_count": 34,
        "source_edge_count": 5,
        "top_relation_types": [
            {"relation_type": "ASSOCIATED_WITH", "count": 4},
            {"relation_type": "TREATS", "count": 1},
        ],
    }
