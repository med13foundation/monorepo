"""Variant serializers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.models.api import common as api_common
from src.models.api import variant as variant_api

from .evidence import serialize_evidence_brief
from .utils import _require_entity_id

if TYPE_CHECKING:
    from src.domain.entities.variant import Variant, VariantSummary

GeneSummary = api_common.GeneSummary

ApiClinicalSignificance = variant_api.ClinicalSignificance
VariantResponse = variant_api.VariantResponse
VariantSummaryResponse = variant_api.VariantSummaryResponse
ApiVariantType = variant_api.VariantType


def serialize_variant_summary(summary: VariantSummary) -> VariantSummaryResponse:
    """Convert a VariantSummary into a typed DTO."""
    return VariantSummaryResponse(
        variant_id=summary.variant_id,
        clinvar_id=summary.clinvar_id,
        chromosome=summary.chromosome,
        position=summary.position,
        clinical_significance=summary.clinical_significance,
    )


def serialize_variant(variant: Variant) -> VariantResponse:
    """Serialize a Variant aggregate into VariantResponse."""
    variant_id = _require_entity_id("Variant", variant.id)
    evidence_items = (
        [serialize_evidence_brief(ev) for ev in variant.evidence]
        if getattr(variant, "evidence", None)
        else None
    )

    gene_summary = _maybe_gene_summary(variant)

    return VariantResponse(
        id=variant_id,
        variant_id=variant.variant_id,
        clinvar_id=variant.clinvar_id,
        gene_id=variant.gene_public_id or "",
        gene_symbol=variant.gene_symbol or "",
        chromosome=variant.chromosome,
        position=variant.position,
        reference_allele=variant.reference_allele,
        alternate_allele=variant.alternate_allele,
        hgvs_genomic=variant.hgvs_genomic,
        hgvs_protein=variant.hgvs_protein,
        hgvs_cdna=variant.hgvs_cdna,
        variant_type=ApiVariantType(variant.variant_type),
        clinical_significance=ApiClinicalSignificance(variant.clinical_significance),
        condition=variant.condition,
        review_status=variant.review_status,
        allele_frequency=variant.allele_frequency,
        gnomad_af=variant.gnomad_af,
        created_at=variant.created_at,
        updated_at=variant.updated_at,
        evidence_count=len(evidence_items) if evidence_items else 0,
        evidence=evidence_items,
        gene=gene_summary,
    )


def _maybe_gene_summary(variant: Variant) -> GeneSummary | None:
    """Build a gene summary if the variant includes gene metadata."""
    gene_id_value = variant.gene_public_id
    gene_symbol_value = variant.gene_symbol
    if gene_id_value is None and gene_symbol_value is None:
        return None
    return GeneSummary(
        id=getattr(variant, "gene_database_id", None),
        gene_id=gene_id_value,
        symbol=gene_symbol_value,
        name=None,
    )


__all__ = [
    "serialize_variant",
    "serialize_variant_summary",
]
