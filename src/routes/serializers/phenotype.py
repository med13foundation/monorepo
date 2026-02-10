"""Phenotype serializers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.models.api import common as api_common
from src.models.api import phenotype as phenotype_api

from .utils import _require_entity_id

if TYPE_CHECKING:
    from src.domain.entities.phenotype import Phenotype

PhenotypeSummary = api_common.PhenotypeSummary

ApiPhenotypeCategory = phenotype_api.PhenotypeCategory
PhenotypeResponse = phenotype_api.PhenotypeResponse


def serialize_phenotype(phenotype: Phenotype) -> PhenotypeResponse:
    """Serialize a Phenotype entity."""
    phenotype_id = _require_entity_id("Phenotype", phenotype.id)
    parent_summary = (
        PhenotypeSummary(
            id=None,
            hpo_id=phenotype.parent_hpo_id,
            name=None,
        )
        if phenotype.parent_hpo_id
        else None
    )
    return PhenotypeResponse(
        id=phenotype_id,
        hpo_id=phenotype.identifier.hpo_id,
        hpo_term=phenotype.identifier.hpo_term,
        name=phenotype.name,
        definition=phenotype.definition,
        synonyms=list(phenotype.synonyms),
        category=ApiPhenotypeCategory(phenotype.category),
        parent_hpo_id=phenotype.parent_hpo_id,
        is_root_term=phenotype.is_root_term,
        frequency_in_med13=phenotype.frequency_in_med13,
        severity_score=phenotype.severity_score,
        created_at=phenotype.created_at,
        updated_at=phenotype.updated_at,
        evidence_count=getattr(phenotype, "evidence_count", 0),
        variant_count=getattr(phenotype, "variant_count", 0),
        parent_phenotype=parent_summary,
        child_phenotypes=None,
        evidence=None,
    )


__all__ = ["serialize_phenotype"]
