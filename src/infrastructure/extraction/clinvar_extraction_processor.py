"""ClinVar-specific extraction processor for queued ClinVar records."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from src.application.services.ports.extraction_processor_port import (
    ExtractionProcessorPort,
    ExtractionProcessorResult,
    ExtractionTextPayload,
)

if TYPE_CHECKING:
    from src.domain.entities.extraction_queue_item import ExtractionQueueItem
    from src.domain.entities.publication import Publication
    from src.type_definitions.common import (
        ExtractionFact,
        ExtractionFactType,
        ExtractionTextSource,
        JSONObject,
    )


class ClinVarExtractionProcessor(ExtractionProcessorPort):
    """Extract deterministic variant/gene/phenotype facts from ClinVar payloads."""

    def extract_publication(
        self,
        *,
        queue_item: ExtractionQueueItem,
        publication: Publication | None,
        text_payload: ExtractionTextPayload | None = None,
    ) -> ExtractionProcessorResult:
        text_source = _resolve_text_source(text_payload)
        document_reference = _resolve_document_reference(text_payload)
        publication_id = publication.id if publication is not None else None

        raw_record = _extract_raw_record(queue_item)
        if raw_record is None:
            failure_metadata: JSONObject = {
                "reason": "missing_raw_record",
                "queue_item_id": str(queue_item.id),
                "source_record_id": queue_item.source_record_id,
            }
            if publication_id is not None:
                failure_metadata["publication_id"] = publication_id
            return ExtractionProcessorResult(
                status="failed",
                facts=[],
                metadata=failure_metadata,
                processor_name="clinvar_contract_v1",
                text_source=text_source,
                document_reference=document_reference,
                error_message="missing_raw_record",
            )

        facts, clinvar_id = _extract_facts(raw_record)
        success_metadata: JSONObject = {
            "queue_item_id": str(queue_item.id),
            "source_type": queue_item.source_type,
            "source_record_id": queue_item.source_record_id,
            "fact_count": len(facts),
        }
        if publication_id is not None:
            success_metadata["publication_id"] = publication_id
        if clinvar_id:
            success_metadata["clinvar_id"] = clinvar_id

        status: ExtractionProcessorResultStatus = "completed" if facts else "skipped"
        if status == "skipped":
            success_metadata["reason"] = "no_extractable_fields"

        return ExtractionProcessorResult(
            status=status,
            facts=facts,
            metadata=success_metadata,
            processor_name="clinvar_contract_v1",
            processor_version="1.0",
            text_source=text_source,
            document_reference=document_reference,
        )


def _extract_raw_record(queue_item: ExtractionQueueItem) -> JSONObject | None:
    raw_record_value = queue_item.metadata.get("raw_record")
    if isinstance(raw_record_value, dict):
        return raw_record_value
    return None


ExtractionProcessorResultStatus = Literal["completed", "failed", "skipped"]


def _resolve_text_source(
    payload: ExtractionTextPayload | None,
) -> ExtractionTextSource:
    if payload is None:
        return "full_text"
    return payload.text_source


def _resolve_document_reference(payload: ExtractionTextPayload | None) -> str | None:
    if payload is None:
        return None
    return payload.document_reference


def _extract_facts(raw_record: JSONObject) -> tuple[list[ExtractionFact], str | None]:
    accumulator = _FactAccumulator()

    clinvar_id = _first_scalar(raw_record, ("clinvar_id", "variation_id", "accession"))
    gene_symbol = _first_scalar(raw_record, ("gene_symbol", "gene"))
    clinical_significance = _first_scalar(
        raw_record,
        ("clinical_significance", "significance", "review_status"),
    )
    condition = _first_scalar(
        raw_record,
        ("condition", "disease_name", "phenotype", "trait"),
    )

    if clinvar_id:
        accumulator.add_fact(
            "variant",
            clinvar_id,
            normalized_id=clinvar_id,
            source="clinvar",
        )
    if gene_symbol:
        accumulator.add_fact(
            "gene",
            gene_symbol,
            normalized_id=gene_symbol.upper(),
            source="clinvar",
        )
    if condition:
        accumulator.add_fact(
            "phenotype",
            condition,
            source="clinvar",
        )
    if clinical_significance:
        accumulator.add_fact(
            "other",
            clinical_significance,
            source="clinvar",
            attributes={"dimension": "clinical_significance"},
        )

    return accumulator.facts, clinvar_id


def _first_scalar(payload: JSONObject, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
        if isinstance(value, int):
            return str(value)
    return None


class _FactAccumulator:
    def __init__(self) -> None:
        self.facts: list[ExtractionFact] = []
        self._seen: set[tuple[ExtractionFactType, str, str | None]] = set()

    def add_fact(
        self,
        fact_type: ExtractionFactType,
        value: str,
        *,
        normalized_id: str | None = None,
        source: str | None = None,
        attributes: JSONObject | None = None,
    ) -> None:
        normalized_value = value.strip()
        if not normalized_value:
            return
        key = (fact_type, normalized_value, normalized_id)
        if key in self._seen:
            return
        self._seen.add(key)
        fact: ExtractionFact = {
            "fact_type": fact_type,
            "value": normalized_value,
        }
        if normalized_id:
            fact["normalized_id"] = normalized_id
        if source:
            fact["source"] = source
        if attributes:
            fact["attributes"] = attributes
        self.facts.append(fact)


__all__ = ["ClinVarExtractionProcessor"]
