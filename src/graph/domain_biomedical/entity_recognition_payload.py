"""Biomedical-pack payload shaping rules for entity recognition."""

from __future__ import annotations

from src.graph.core.entity_recognition_payload import (
    EntityRecognitionCompactRecordRule,
    EntityRecognitionPayloadConfig,
)

BIOMEDICAL_ENTITY_RECOGNITION_PAYLOAD_CONFIG = EntityRecognitionPayloadConfig(
    compact_record_rules={
        "pubmed": EntityRecognitionCompactRecordRule(
            fields=(
                "pubmed_id",
                "title",
                "doi",
                "source",
                "full_text_source",
                "full_text_chunk_index",
                "full_text_chunk_total",
                "full_text_chunk_start_char",
                "full_text_chunk_end_char",
                "publication_date",
                "publication_types",
                "journal",
                "keywords",
            ),
            preferred_text_fields=("full_text", "abstract"),
        ),
        "clinvar": EntityRecognitionCompactRecordRule(
            fields=(
                "variation_id",
                "gene_symbol",
                "variant_name",
                "clinical_significance",
                "condition_name",
                "review_status",
                "submission_count",
                "source",
            ),
        ),
    },
)
