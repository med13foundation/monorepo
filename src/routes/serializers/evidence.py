"""Evidence serializers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.models.api import common as api_common
from src.models.api import evidence as evidence_api

from .utils import _require_entity_id

if TYPE_CHECKING:
    from src.domain.entities.evidence import Evidence
    from src.domain.entities.variant import EvidenceSummary

PublicationSummary = api_common.PublicationSummary
VariantLinkSummary = api_common.VariantLinkSummary
PhenotypeSummary = api_common.PhenotypeSummary

ApiEvidenceLevel = evidence_api.EvidenceLevel
EvidenceResponse = evidence_api.EvidenceResponse
EvidenceSummaryResponse = evidence_api.EvidenceSummaryResponse
ApiEvidenceType = evidence_api.EvidenceType


def serialize_evidence_brief(evidence: EvidenceSummary) -> EvidenceSummaryResponse:
    """Serialize the lightweight EvidenceSummary helper."""
    return EvidenceSummaryResponse(
        id=evidence.evidence_id,
        evidence_level=evidence.evidence_level,
        evidence_type=evidence.evidence_type,
        description=evidence.description,
        reviewed=evidence.reviewed,
    )


def serialize_evidence(evidence: Evidence) -> EvidenceResponse:
    """Serialize a full Evidence entity."""
    evidence_id = _require_entity_id("Evidence", evidence.id)
    variant_summary = _build_variant_summary_for_evidence(evidence)
    phenotype_summary = _build_phenotype_summary_for_evidence(evidence)
    publication_summary = _build_publication_summary_for_evidence(evidence)
    return EvidenceResponse(
        id=evidence_id,
        variant_id=str(evidence.variant_id),
        phenotype_id=str(evidence.phenotype_id),
        publication_id=(
            str(evidence.publication_id) if evidence.publication_id else None
        ),
        description=evidence.description,
        summary=evidence.summary,
        evidence_level=ApiEvidenceLevel(evidence.evidence_level.value),
        evidence_type=ApiEvidenceType(evidence.evidence_type),
        confidence_score=evidence.confidence.score,
        quality_score=evidence.quality_score,
        sample_size=evidence.sample_size,
        study_type=evidence.study_type,
        statistical_significance=evidence.statistical_significance,
        reviewed=evidence.reviewed,
        review_date=evidence.review_date,
        reviewer_notes=evidence.reviewer_notes,
        created_at=evidence.created_at,
        updated_at=evidence.updated_at,
        variant=variant_summary,
        phenotype=phenotype_summary,
        publication=publication_summary,
    )


def _build_variant_summary_for_evidence(
    evidence: Evidence,
) -> VariantLinkSummary | None:
    """Construct a lightweight variant summary for evidence payloads."""
    variant_id_value: str | None = None
    clinvar_id_value: str | None = None

    if evidence.variant_summary is not None:
        variant_id_value = evidence.variant_summary.variant_id
        clinvar_id_value = evidence.variant_summary.clinvar_id
    elif evidence.variant_identifier is not None:
        variant_id_value = evidence.variant_identifier.variant_id
        clinvar_id_value = evidence.variant_identifier.clinvar_id

    if variant_id_value is None and clinvar_id_value is None:
        return None

    return VariantLinkSummary(
        id=evidence.variant_id,
        variant_id=variant_id_value,
        clinvar_id=clinvar_id_value,
        gene_symbol=None,
    )


def _build_phenotype_summary_for_evidence(
    evidence: Evidence,
) -> PhenotypeSummary | None:
    """Construct a phenotype summary for evidence payloads."""
    identifier = evidence.phenotype_identifier
    return PhenotypeSummary(
        id=evidence.phenotype_id,
        hpo_id=identifier.hpo_id if identifier else None,
        name=identifier.hpo_term if identifier else None,
    )


def _build_publication_summary_for_evidence(
    evidence: Evidence,
) -> PublicationSummary | None:
    """Construct a publication summary for evidence payloads."""
    identifier = evidence.publication_identifier
    if identifier is None and evidence.publication_id is None:
        return None
    return PublicationSummary(
        id=evidence.publication_id,
        title=None,
        pubmed_id=identifier.pubmed_id if identifier else None,
        doi=identifier.doi if identifier else None,
    )


__all__ = [
    "serialize_evidence",
    "serialize_evidence_brief",
]
