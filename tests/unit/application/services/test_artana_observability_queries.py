"""Focused unit tests for helper-backed Artana observability queries."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from src.application.services._artana_observability_queries import (
    _load_linked_provenance,
    _load_linked_relation_evidence,
)
from src.infrastructure.repositories.graph_observability_repository import (
    LinkedProvenanceRow,
    LinkedRelationEvidenceRow,
)


def test_load_linked_relation_evidence_uses_graph_service_helper() -> None:
    session = Mock()
    space_id = str(uuid4())
    created_at = datetime(2026, 3, 12, 12, 0, tzinfo=UTC)
    updated_at = datetime(2026, 3, 12, 12, 5, tzinfo=UTC)

    with patch(
        "src.application.services._artana_observability_queries.load_linked_relation_evidence_rows",
        return_value=[
            LinkedRelationEvidenceRow(
                evidence_id="evidence-1",
                relation_id="relation-1",
                research_space_id=space_id,
                source_document_id="document-1",
                relation_type="ASSOCIATED_WITH",
                curation_status="RESOLVED",
                source_entity_id="entity-a",
                target_entity_id="entity-b",
                evidence_tier="LITERATURE",
                created_at=created_at,
                relation_updated_at=updated_at,
            ),
        ],
    ) as helper:
        payload = _load_linked_relation_evidence(
            session,
            run_id="run-1",
            research_space_id=space_id,
        )

    helper.assert_called_once_with(
        session,
        run_id="run-1",
        research_space_id=UUID(space_id),
    )
    assert payload == [
        {
            "record_type": "relation_evidence",
            "record_id": "evidence-1",
            "research_space_id": space_id,
            "source_id": None,
            "document_id": "document-1",
            "source_type": None,
            "status": "RESOLVED",
            "label": "ASSOCIATED_WITH",
            "created_at": created_at.isoformat(),
            "updated_at": updated_at.isoformat(),
            "metadata": {
                "relation_id": "relation-1",
                "relation_type": "ASSOCIATED_WITH",
                "source_entity_id": "entity-a",
                "target_entity_id": "entity-b",
                "evidence_tier": "LITERATURE",
            },
        },
    ]


def test_load_linked_provenance_uses_graph_service_helper() -> None:
    session = Mock()
    space_id = str(uuid4())
    created_at = datetime(2026, 3, 12, 13, 0, tzinfo=UTC)

    with patch(
        "src.application.services._artana_observability_queries.load_linked_provenance_rows",
        return_value=[
            LinkedProvenanceRow(
                provenance_id="prov-1",
                research_space_id=space_id,
                source_type="pubmed",
                mapping_method="llm",
                source_ref="PMID:12345",
                created_at=created_at,
                mapping_confidence=0.9,
                agent_model="gpt-5.4",
            ),
        ],
    ) as helper:
        payload = _load_linked_provenance(
            session,
            run_id="run-2",
            research_space_id=space_id,
        )

    helper.assert_called_once_with(
        session,
        run_id="run-2",
        research_space_id=UUID(space_id),
    )
    assert payload == [
        {
            "record_type": "provenance",
            "record_id": "prov-1",
            "research_space_id": space_id,
            "source_id": None,
            "document_id": None,
            "source_type": "pubmed",
            "status": "llm",
            "label": "PMID:12345",
            "created_at": created_at.isoformat(),
            "updated_at": created_at.isoformat(),
            "metadata": {
                "mapping_confidence": 0.9,
                "agent_model": "gpt-5.4",
                "source_ref": "PMID:12345",
            },
        },
    ]
