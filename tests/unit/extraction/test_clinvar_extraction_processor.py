"""Unit tests for the ClinVar extraction processor."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from src.domain.entities.extraction_queue_item import (
    ExtractionQueueItem,
    ExtractionStatus,
)
from src.infrastructure.extraction.clinvar_extraction_processor import (
    ClinVarExtractionProcessor,
)


def _build_queue_item(metadata: dict[str, object]) -> ExtractionQueueItem:
    now = datetime.now(UTC)
    return ExtractionQueueItem(
        id=uuid4(),
        publication_id=None,
        pubmed_id=None,
        source_type="clinvar",
        source_record_id="clinvar:clinvar_id:1001",
        source_id=uuid4(),
        ingestion_job_id=uuid4(),
        status=ExtractionStatus.PENDING,
        attempts=0,
        last_error=None,
        extraction_version=1,
        metadata=metadata,
        queued_at=now,
        started_at=None,
        completed_at=None,
        updated_at=now,
    )


def test_extract_publication_returns_deterministic_clinvar_facts() -> None:
    processor = ClinVarExtractionProcessor()
    queue_item = _build_queue_item(
        {
            "raw_record": {
                "clinvar_id": "1001",
                "gene_symbol": "MED13",
                "clinical_significance": "Pathogenic",
                "condition": "Developmental delay",
            },
        },
    )

    result = processor.extract_publication(
        queue_item=queue_item,
        publication=None,
        text_payload=None,
    )

    fact_types = {fact["fact_type"] for fact in result.facts}
    assert result.status == "completed"
    assert "variant" in fact_types
    assert "gene" in fact_types
    assert "phenotype" in fact_types
    assert result.processor_name == "clinvar_contract_v1"
    assert result.metadata["source_type"] == "clinvar"


def test_extract_publication_fails_when_raw_record_is_missing() -> None:
    processor = ClinVarExtractionProcessor()
    queue_item = _build_queue_item({})

    result = processor.extract_publication(
        queue_item=queue_item,
        publication=None,
        text_payload=None,
    )

    assert result.status == "failed"
    assert result.error_message == "missing_raw_record"
    assert result.metadata["reason"] == "missing_raw_record"
