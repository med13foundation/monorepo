"""Biomedical-pack payload shaping rules for extraction."""

from __future__ import annotations

from src.graph.core.extraction_payload import (
    ExtractionCompactRecordRule,
    ExtractionPayloadConfig,
)

BIOMEDICAL_EXTRACTION_PAYLOAD_CONFIG = ExtractionPayloadConfig(
    compact_record_rules={
        "pubmed": ExtractionCompactRecordRule(
            fields=(
                "pubmed_id",
                "title",
                "abstract",
                "full_text",
                "keywords",
                "journal",
                "publication_date",
                "publication_types",
                "doi",
                "source",
                "full_text_source",
                "full_text_chunk_index",
                "full_text_chunk_total",
                "full_text_chunk_start_char",
                "full_text_chunk_end_char",
            ),
            chunk_fields=(
                "pubmed_id",
                "title",
                "doi",
                "source",
                "full_text",
                "full_text_source",
                "full_text_chunk_index",
                "full_text_chunk_total",
                "full_text_chunk_start_char",
                "full_text_chunk_end_char",
            ),
            chunk_indicator_field="full_text_chunk_index",
            fallback_text_field="text",
        ),
        "clinvar": ExtractionCompactRecordRule(
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
