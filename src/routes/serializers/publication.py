"""Publication serializers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.models.api import publication as publication_api

from .evidence import serialize_evidence
from .utils import _require_entity_id

if TYPE_CHECKING:
    from src.domain.entities.publication import Publication

AuthorInfo = publication_api.AuthorInfo
PublicationResponse = publication_api.PublicationResponse
ApiPublicationType = publication_api.PublicationType


def serialize_publication(publication: Publication) -> PublicationResponse:
    """Serialize a Publication entity."""
    publication_id = _require_entity_id("Publication", publication.id)
    evidence = [serialize_evidence(ev) for ev in publication.evidence]
    author_models = [
        AuthorInfo(
            name=name,
            first_name=None,
            last_name=None,
            affiliation=None,
            orcid=None,
        )
        for name in publication.authors
    ]

    return PublicationResponse(
        id=publication_id,
        pubmed_id=publication.identifier.pubmed_id,
        pmc_id=publication.identifier.pmc_id,
        doi=publication.identifier.doi,
        title=publication.title,
        authors=author_models,
        journal=publication.journal,
        publication_year=publication.publication_year,
        volume=publication.volume,
        issue=publication.issue,
        pages=publication.pages,
        publication_date=publication.publication_date,
        publication_type=ApiPublicationType(publication.publication_type),
        abstract=publication.abstract,
        keywords=list(publication.keywords),
        citation_count=publication.citation_count,
        impact_factor=publication.impact_factor,
        reviewed=publication.reviewed,
        relevance_score=publication.relevance_score,
        full_text_url=publication.full_text_url,
        open_access=publication.open_access,
        created_at=publication.created_at,
        updated_at=publication.updated_at,
        evidence_count=len(evidence),
        evidence=evidence,
    )


__all__ = ["serialize_publication"]
