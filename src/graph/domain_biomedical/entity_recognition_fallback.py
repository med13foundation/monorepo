"""Biomedical-pack entity-recognition fallback heuristics."""

from __future__ import annotations

from src.graph.core.entity_recognition_fallback import (
    EntityRecognitionHeuristicFieldMap,
)

BIOMEDICAL_ENTITY_RECOGNITION_HEURISTIC_FIELD_MAP = EntityRecognitionHeuristicFieldMap(
    source_type_fields={
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
    },
    default_source_type="clinvar",
    primary_entity_types={
        "clinvar": "VARIANT",
        "pubmed": "PUBLICATION",
    },
)
