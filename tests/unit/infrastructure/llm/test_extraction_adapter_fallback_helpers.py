"""Tests for pack-owned extraction fallback defaults."""

from __future__ import annotations

from src.domain.agents.contexts.extraction_context import ExtractionContext
from src.domain.agents.contracts.entity_recognition import RecognizedEntityCandidate
from src.graph.domain_biomedical.extraction_fallback import (
    BIOMEDICAL_EXTRACTION_HEURISTIC_CONFIG,
)
from src.infrastructure.llm.adapters._extraction_adapter_fallback_helpers import (
    build_heuristic_extraction_contract,
)


def test_build_heuristic_extraction_contract_uses_pack_relation_defaults() -> None:
    context = ExtractionContext(
        document_id="doc-1",
        source_type="pubmed",
        raw_record={"title": "Variant linked to phenotype"},
        recognized_entities=[
            RecognizedEntityCandidate(
                entity_type="VARIANT",
                display_label="c.1A>G",
                identifiers={},
                confidence=0.8,
            ),
            RecognizedEntityCandidate(
                entity_type="PHENOTYPE",
                display_label="Cardiomyopathy",
                identifiers={},
                confidence=0.7,
            ),
        ],
    )

    contract = build_heuristic_extraction_contract(
        context,
        fallback_config=BIOMEDICAL_EXTRACTION_HEURISTIC_CONFIG,
        dictionary_service=None,
        agent_run_id="run-1",
        decision="fallback",
    )

    assert len(contract.relations) == 1
    relation = contract.relations[0]
    assert relation.source_type == "VARIANT"
    assert relation.relation_type == "ASSOCIATED_WITH"
    assert relation.target_type == "PHENOTYPE"
    assert relation.polarity == "UNCERTAIN"
    assert relation.claim_text == "Variant linked to phenotype"


def test_build_heuristic_extraction_contract_uses_pack_claim_text_field_order() -> None:
    context = ExtractionContext(
        document_id="doc-2",
        source_type="clinvar",
        raw_record={
            "title": "Short title",
            "abstract": "Preferred abstract text",
        },
        recognized_entities=[
            RecognizedEntityCandidate(
                entity_type="VARIANT",
                display_label="c.2A>G",
                identifiers={},
                confidence=0.8,
            ),
            RecognizedEntityCandidate(
                entity_type="PHENOTYPE",
                display_label="Arrhythmia",
                identifiers={},
                confidence=0.7,
            ),
        ],
    )

    contract = build_heuristic_extraction_contract(
        context,
        fallback_config=BIOMEDICAL_EXTRACTION_HEURISTIC_CONFIG,
        dictionary_service=None,
        agent_run_id=None,
        decision="fallback",
    )

    assert contract.relations[0].claim_text == "Preferred abstract text"
