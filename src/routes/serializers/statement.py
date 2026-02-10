"""Statement serializers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.models.api import evidence as evidence_api
from src.models.api import mechanism as mechanism_api
from src.models.api import statement as statement_api

from .utils import _require_entity_id

if TYPE_CHECKING:
    from src.domain.entities.statement import StatementOfUnderstanding

StatementResponse = statement_api.StatementResponse
ApiStatementStatus = statement_api.StatementStatus
ProteinDomainPayload = mechanism_api.ProteinDomainPayload
ProteinDomainCoordinate = mechanism_api.ProteinDomainCoordinate


def serialize_statement(statement: StatementOfUnderstanding) -> StatementResponse:
    """Serialize a StatementOfUnderstanding entity."""
    statement_id = _require_entity_id("Statement", statement.id)
    protein_domains = [
        ProteinDomainPayload(
            name=domain.name,
            source_id=domain.source_id,
            start_residue=domain.start_residue,
            end_residue=domain.end_residue,
            domain_type=domain.domain_type,
            description=domain.description,
            coordinates=(
                [
                    ProteinDomainCoordinate(
                        x=coord.x,
                        y=coord.y,
                        z=coord.z,
                        confidence=coord.confidence,
                    )
                    for coord in domain.coordinates
                ]
                if domain.coordinates
                else None
            ),
        )
        for domain in statement.protein_domains
    ]
    phenotype_ids = list(statement.phenotype_ids or [])

    return StatementResponse(
        id=statement_id,
        title=statement.title,
        summary=statement.summary,
        evidence_tier=evidence_api.EvidenceLevel(statement.evidence_tier.value),
        confidence_score=statement.confidence_score,
        status=ApiStatementStatus(statement.status.value),
        source=statement.source,
        protein_domains=protein_domains,
        phenotype_ids=phenotype_ids,
        phenotype_count=len(phenotype_ids),
        promoted_mechanism_id=statement.promoted_mechanism_id,
        created_at=statement.created_at,
        updated_at=statement.updated_at,
    )


__all__ = ["serialize_statement"]
