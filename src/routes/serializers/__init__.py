"""Helper functions for serializing domain entities into typed API DTOs."""

from .common import build_activity_feed_item, build_dashboard_summary
from .evidence import serialize_evidence, serialize_evidence_brief
from .extraction import serialize_extraction_fact, serialize_publication_extraction
from .gene import serialize_gene
from .mechanism import serialize_mechanism
from .phenotype import serialize_phenotype
from .publication import serialize_publication
from .statement import serialize_statement
from .variant import serialize_variant, serialize_variant_summary

__all__ = [
    "build_activity_feed_item",
    "build_dashboard_summary",
    "serialize_evidence",
    "serialize_evidence_brief",
    "serialize_extraction_fact",
    "serialize_gene",
    "serialize_mechanism",
    "serialize_phenotype",
    "serialize_publication",
    "serialize_publication_extraction",
    "serialize_statement",
    "serialize_variant",
    "serialize_variant_summary",
]
