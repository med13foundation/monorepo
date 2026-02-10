"""Mechanism serializers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.models.api import evidence as evidence_api
from src.models.api import mechanism as mechanism_api

from .utils import _require_entity_id

if TYPE_CHECKING:
    from src.domain.entities.mechanism import Mechanism

MechanismResponse = mechanism_api.MechanismResponse
ApiMechanismLifecycleState = mechanism_api.MechanismLifecycleState
ProteinDomainPayload = mechanism_api.ProteinDomainPayload
ProteinDomainCoordinate = mechanism_api.ProteinDomainCoordinate


def serialize_mechanism(mechanism: Mechanism) -> MechanismResponse:
    """Serialize a Mechanism entity."""
    mechanism_id = _require_entity_id("Mechanism", mechanism.id)
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
        for domain in mechanism.protein_domains
    ]

    phenotype_ids = list(mechanism.phenotype_ids or [])

    return MechanismResponse(
        id=mechanism_id,
        name=mechanism.name,
        description=mechanism.description,
        evidence_tier=evidence_api.EvidenceLevel(mechanism.evidence_tier.value),
        confidence_score=mechanism.confidence_score,
        source=mechanism.source,
        lifecycle_state=ApiMechanismLifecycleState(mechanism.lifecycle_state.value),
        protein_domains=protein_domains,
        phenotype_ids=phenotype_ids,
        phenotype_count=len(phenotype_ids),
        created_at=mechanism.created_at,
        updated_at=mechanism.updated_at,
    )


__all__ = ["serialize_mechanism"]
