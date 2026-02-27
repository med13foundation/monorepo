"""Fallback and selection helpers for entity-recognition adapter orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from src.domain.agents.contracts import (
    EntityRecognitionContract,
    EvidenceItem,
    RecognizedEntityCandidate,
    RecognizedObservationCandidate,
)
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.domain.agents.contexts.entity_recognition_context import (
        EntityRecognitionContext,
    )
    from src.type_definitions.common import JSONObject

_HEURISTIC_FIELD_MAP: dict[str, dict[str, tuple[str, ...]]] = {
    "clinvar": {
        "variant": ("clinvar_id", "variation_id", "accession", "hgvs"),
        "gene": ("gene_symbol", "gene", "hgnc_id"),
        "phenotype": ("condition", "disease_name", "phenotype"),
        "publication": ("title", "pubmed_id", "doi"),
    },
    "pubmed": {
        "variant": ("hgvs", "variant"),
        "gene": ("gene_symbol", "gene", "hgnc_id"),
        "phenotype": ("condition", "disease", "phenotype"),
        "publication": ("title", "pubmed_id", "pmid", "doi"),
    },
}


def is_heuristic_entity_recognition_contract(
    contract: EntityRecognitionContract,
) -> bool:
    rationale = contract.rationale.strip().lower()
    return rationale.startswith("heuristic ")


def select_preferred_entity_recognition_contract(
    primary_output: EntityRecognitionContract,
    retry_output: EntityRecognitionContract,
) -> EntityRecognitionContract:
    primary_is_heuristic = is_heuristic_entity_recognition_contract(primary_output)
    retry_is_heuristic = is_heuristic_entity_recognition_contract(retry_output)
    if primary_is_heuristic and not retry_is_heuristic:
        return retry_output
    if retry_is_heuristic and not primary_is_heuristic:
        return primary_output
    if _entity_signal_score(retry_output) > _entity_signal_score(primary_output):
        return retry_output
    return primary_output


def _entity_signal_score(contract: EntityRecognitionContract) -> tuple[int, float]:
    entity_count = len(contract.recognized_entities)
    observation_count = len(contract.recognized_observations)
    return (entity_count * 3 + observation_count, contract.confidence_score)


def build_heuristic_entity_recognition_contract(
    context: EntityRecognitionContext,
    *,
    agent_run_id: str | None,
    decision: Literal["generated", "fallback", "escalate"],
) -> EntityRecognitionContract:
    source_type = context.source_type.strip().lower()
    raw_record = dict(context.raw_record)
    field_candidates = [
        str(key)
        for key, value in raw_record.items()
        if isinstance(value, str | int | float | bool)
    ]

    entities: list[RecognizedEntityCandidate] = []
    variant_label = _extract_scalar(
        raw_record,
        _field_keys_for_source(source_type, "variant"),
    )
    if variant_label:
        entities.append(
            RecognizedEntityCandidate(
                entity_type="VARIANT",
                display_label=variant_label,
                identifiers={"variant_id": variant_label},
                confidence=0.8,
            ),
        )

    gene_label = _extract_scalar(
        raw_record,
        _field_keys_for_source(source_type, "gene"),
    )
    if gene_label:
        entities.append(
            RecognizedEntityCandidate(
                entity_type="GENE",
                display_label=gene_label,
                identifiers={"gene_symbol": gene_label},
                confidence=0.75,
            ),
        )

    phenotype_label = _extract_scalar(
        raw_record,
        _field_keys_for_source(source_type, "phenotype"),
    )
    if phenotype_label:
        entities.append(
            RecognizedEntityCandidate(
                entity_type="PHENOTYPE",
                display_label=phenotype_label,
                identifiers={"label": phenotype_label},
                confidence=0.65,
            ),
        )

    publication_label = _extract_scalar(
        raw_record,
        _field_keys_for_source(source_type, "publication"),
    )
    if publication_label:
        entities.append(
            RecognizedEntityCandidate(
                entity_type="PUBLICATION",
                display_label=publication_label,
                identifiers={"publication_ref": publication_label},
                confidence=0.7,
            ),
        )

    observations: list[RecognizedObservationCandidate] = []
    for field_name in field_candidates:
        value = raw_record.get(field_name)
        if value is None:
            continue
        json_value = to_json_value(value)
        observations.append(
            RecognizedObservationCandidate(
                field_name=field_name,
                value=json_value,
                confidence=0.6,
            ),
        )

    pipeline_payload = {
        str(key): to_json_value(value) for key, value in raw_record.items()
    }
    evidence = [
        EvidenceItem(
            source_type="db",
            locator=f"source_document:{context.document_id}",
            excerpt="Deterministic fallback parsed raw_record fields",
            relevance=0.7 if entities else 0.4,
        ),
    ]
    resolved_decision: Literal["generated", "fallback", "escalate"] = (
        "generated" if entities else decision
    )
    confidence = 0.78 if entities else 0.4

    return EntityRecognitionContract(
        decision=resolved_decision,
        confidence_score=confidence,
        rationale=f"Heuristic {source_type} parsing fallback executed",
        evidence=evidence,
        source_type=context.source_type,
        document_id=context.document_id,
        primary_entity_type=(
            entities[0].entity_type
            if entities
            else ("PUBLICATION" if source_type == "pubmed" else "VARIANT")
        ),
        field_candidates=field_candidates,
        recognized_entities=entities,
        recognized_observations=observations,
        pipeline_payloads=[pipeline_payload] if pipeline_payload else [],
        shadow_mode=context.shadow_mode,
        agent_run_id=agent_run_id,
    )


def _extract_scalar(raw_record: JSONObject, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = raw_record.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
        if isinstance(value, int | float):
            return str(value)
    return None


def _field_keys_for_source(source_type: str, field: str) -> tuple[str, ...]:
    source_mapping = _HEURISTIC_FIELD_MAP.get(
        source_type,
        _HEURISTIC_FIELD_MAP["clinvar"],
    )
    return source_mapping.get(field, ())
