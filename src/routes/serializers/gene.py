"""Gene serializers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from src.models.api import gene as gene_api

from .utils import _require_entity_id
from .variant import serialize_variant_summary

if TYPE_CHECKING:
    from src.domain.entities.gene import Gene
    from src.domain.entities.variant import VariantSummary

GenePhenotypeSummary = gene_api.GenePhenotypeSummary
GeneResponse = gene_api.GeneResponse
ApiGeneType = gene_api.GeneType


def serialize_gene(
    gene: Gene,
    *,
    include_variants: bool = False,
    variants: Iterable[VariantSummary] | None = None,
    include_phenotypes: bool = False,
    phenotypes: Iterable[Mapping[str, object] | GenePhenotypeSummary] | None = None,
) -> GeneResponse:
    """Serialize a Gene aggregate with optional relationships."""
    gene_id = _require_entity_id("Gene", gene.id)

    if include_variants:
        variant_iterable = variants if variants is not None else gene.variants
        variant_summaries = [
            serialize_variant_summary(summary) for summary in variant_iterable
        ]
        variant_count = len(variant_summaries)
    else:
        variant_summaries = None
        variant_count = len(gene.variants) if gene.variants else 0

    phenotype_summaries: list[GenePhenotypeSummary] | None = None
    phenotype_count = 0
    if include_phenotypes:
        raw_phenotypes = phenotypes if phenotypes is not None else []
        phenotype_summaries = [
            _coerce_gene_phenotype(value) for value in raw_phenotypes
        ]
        phenotype_count = len(phenotype_summaries)

    return GeneResponse(
        id=gene_id,
        gene_id=gene.gene_id,
        symbol=gene.symbol,
        name=gene.name,
        description=gene.description,
        gene_type=ApiGeneType(gene.gene_type),
        chromosome=gene.chromosome,
        start_position=gene.start_position,
        end_position=gene.end_position,
        ensembl_id=gene.ensembl_id,
        ncbi_gene_id=gene.ncbi_gene_id,
        uniprot_id=gene.uniprot_id,
        created_at=gene.created_at,
        updated_at=gene.updated_at,
        variant_count=variant_count,
        phenotype_count=phenotype_count,
        variants=variant_summaries,
        phenotypes=phenotype_summaries,
    )


def _coerce_gene_phenotype(
    value: GenePhenotypeSummary | Mapping[str, object],
) -> GenePhenotypeSummary:
    if isinstance(value, GenePhenotypeSummary):
        return value
    return GenePhenotypeSummary.model_validate(value)


__all__ = ["serialize_gene"]
