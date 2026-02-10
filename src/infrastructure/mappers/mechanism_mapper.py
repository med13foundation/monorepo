from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.domain.entities.mechanism import Mechanism
from src.domain.value_objects.confidence import EvidenceLevel
from src.domain.value_objects.mechanism_lifecycle import MechanismLifecycleState
from src.domain.value_objects.protein_structure import ProteinDomain
from src.models.database.mechanism import MechanismModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence


class MechanismMapper:
    """Maps between SQLAlchemy MechanismModel and domain Mechanism entities."""

    @staticmethod
    def to_domain(model: MechanismModel) -> Mechanism:
        protein_domains = [
            ProteinDomain.model_validate(item) for item in model.protein_domains or []
        ]
        phenotype_ids = [phenotype.id for phenotype in model.phenotypes]
        return Mechanism(
            research_space_id=UUID(str(model.research_space_id)),
            name=model.name,
            description=model.description,
            evidence_tier=MechanismMapper._normalize_evidence_tier(
                model.evidence_tier,
            ),
            confidence_score=model.confidence_score,
            source=model.source,
            lifecycle_state=MechanismMapper._normalize_lifecycle_state(
                model.lifecycle_state,
            ),
            protein_domains=protein_domains,
            phenotype_ids=phenotype_ids,
            created_at=model.created_at,
            updated_at=model.updated_at,
            id=model.id,
        )

    @staticmethod
    def to_model(
        entity: Mechanism,
        model: MechanismModel | None = None,
    ) -> MechanismModel:
        target = model or MechanismModel()
        target.research_space_id = str(entity.research_space_id)
        target.name = entity.name
        target.description = entity.description
        target.evidence_tier = MechanismMapper._evidence_tier_value(
            entity.evidence_tier,
        )
        target.confidence_score = entity.confidence_score
        target.source = entity.source
        target.lifecycle_state = MechanismMapper._lifecycle_state_value(
            entity.lifecycle_state,
        )
        target.protein_domains = [
            domain.model_dump() for domain in entity.protein_domains
        ]
        if entity.created_at:
            target.created_at = entity.created_at
        if entity.updated_at:
            target.updated_at = entity.updated_at
        return target

    @staticmethod
    def to_domain_sequence(models: Sequence[MechanismModel]) -> list[Mechanism]:
        return [MechanismMapper.to_domain(model) for model in models]

    @staticmethod
    def _normalize_evidence_tier(value: str) -> EvidenceLevel:
        try:
            return EvidenceLevel(value)
        except ValueError:
            return EvidenceLevel.SUPPORTING

    @staticmethod
    def _evidence_tier_value(value: EvidenceLevel | str) -> str:
        if isinstance(value, EvidenceLevel):
            return value.value
        return str(value)

    @staticmethod
    def _normalize_lifecycle_state(value: str | None) -> MechanismLifecycleState:
        if not value:
            return MechanismLifecycleState.DRAFT
        try:
            return MechanismLifecycleState(value)
        except ValueError:
            return MechanismLifecycleState.DRAFT

    @staticmethod
    def _lifecycle_state_value(value: MechanismLifecycleState | str) -> str:
        if isinstance(value, MechanismLifecycleState):
            return value.value
        return str(value)


__all__ = ["MechanismMapper"]
