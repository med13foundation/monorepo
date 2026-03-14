"""Tests for pack-owned entity-recognition fallback heuristics."""

from __future__ import annotations

from src.domain.agents.contexts.entity_recognition_context import (
    EntityRecognitionContext,
)
from src.graph.domain_biomedical.entity_recognition_fallback import (
    BIOMEDICAL_ENTITY_RECOGNITION_HEURISTIC_FIELD_MAP,
)
from src.infrastructure.llm.adapters._entity_recognition_adapter_fallback_helpers import (
    build_heuristic_entity_recognition_contract,
)


def test_build_heuristic_entity_recognition_contract_uses_pubmed_pack_fields() -> None:
    context = EntityRecognitionContext(
        document_id="doc-pubmed",
        source_type="pubmed",
        raw_record={
            "pmid": "12345",
            "gene_symbol": "MED13",
            "phenotype": "Cardiomyopathy",
        },
    )

    contract = build_heuristic_entity_recognition_contract(
        context,
        fallback_config=BIOMEDICAL_ENTITY_RECOGNITION_HEURISTIC_FIELD_MAP,
        agent_run_id="run-1",
        decision="fallback",
    )

    assert contract.primary_entity_type == "GENE"
    assert [entity.entity_type for entity in contract.recognized_entities] == [
        "GENE",
        "PHENOTYPE",
        "PUBLICATION",
    ]
    assert contract.recognized_entities[2].identifiers["publication_ref"] == "12345"


def test_build_heuristic_entity_recognition_contract_uses_pack_default_source() -> None:
    context = EntityRecognitionContext(
        document_id="doc-generic",
        source_type="custom_source",
        raw_record={
            "clinvar_id": "VCV0001",
            "gene_symbol": "MED13",
        },
    )

    contract = build_heuristic_entity_recognition_contract(
        context,
        fallback_config=BIOMEDICAL_ENTITY_RECOGNITION_HEURISTIC_FIELD_MAP,
        agent_run_id=None,
        decision="fallback",
    )

    assert contract.primary_entity_type == "VARIANT"
    assert [entity.entity_type for entity in contract.recognized_entities] == [
        "VARIANT",
        "GENE",
    ]
