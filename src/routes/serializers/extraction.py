"""Publication extraction serializers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.models.api import publication_extraction as publication_extraction_api

if TYPE_CHECKING:
    from src.domain.entities.publication_extraction import PublicationExtraction
    from src.type_definitions.common import ExtractionFact, ExtractionFactType

ApiExtractionOutcome = publication_extraction_api.ExtractionOutcome
ExtractionFactResponse = publication_extraction_api.ExtractionFactResponse
PublicationExtractionResponse = publication_extraction_api.PublicationExtractionResponse


def serialize_extraction_fact(
    fact: ExtractionFact,
) -> ExtractionFactResponse:
    """Serialize an extraction fact mapping into a response DTO."""
    fact_type: ExtractionFactType = fact.get("fact_type", "other")
    return ExtractionFactResponse(
        fact_type=fact_type,
        value=fact.get("value", ""),
        normalized_id=(
            str(fact["normalized_id"]) if fact.get("normalized_id") else None
        ),
        source=str(fact["source"]) if fact.get("source") else None,
        attributes=fact.get("attributes"),
    )


def serialize_publication_extraction(
    extraction: PublicationExtraction,
) -> PublicationExtractionResponse:
    """Serialize a publication extraction domain entity."""
    facts = [serialize_extraction_fact(fact) for fact in (extraction.facts or [])]
    return PublicationExtractionResponse(
        id=str(extraction.id),
        publication_id=extraction.publication_id,
        pubmed_id=extraction.pubmed_id,
        source_id=str(extraction.source_id),
        ingestion_job_id=str(extraction.ingestion_job_id),
        queue_item_id=str(extraction.queue_item_id),
        status=ApiExtractionOutcome(extraction.status.value),
        extraction_version=extraction.extraction_version,
        processor_name=extraction.processor_name,
        processor_version=extraction.processor_version,
        text_source=extraction.text_source.value,
        document_reference=extraction.document_reference,
        facts=facts,
        metadata=extraction.metadata,
        extracted_at=extraction.extracted_at,
        created_at=extraction.created_at,
        updated_at=extraction.updated_at,
    )


__all__ = [
    "serialize_extraction_fact",
    "serialize_publication_extraction",
]
