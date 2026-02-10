from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.domain.entities.statement import StatementOfUnderstanding
from src.domain.value_objects.confidence import EvidenceLevel
from src.domain.value_objects.protein_structure import ProteinDomain
from src.domain.value_objects.statement_status import StatementStatus
from src.models.database.statement import StatementModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence


class StatementMapper:
    """Maps between SQLAlchemy StatementModel and domain Statement entities."""

    @staticmethod
    def to_domain(model: StatementModel) -> StatementOfUnderstanding:
        protein_domains = [
            ProteinDomain.model_validate(item) for item in model.protein_domains or []
        ]
        phenotype_ids = [phenotype.id for phenotype in model.phenotypes]
        return StatementOfUnderstanding(
            research_space_id=UUID(str(model.research_space_id)),
            title=model.title,
            summary=model.summary,
            evidence_tier=StatementMapper._normalize_evidence_tier(
                model.evidence_tier,
            ),
            confidence_score=model.confidence_score,
            status=StatementMapper._normalize_status(model.status),
            source=model.source,
            protein_domains=protein_domains,
            phenotype_ids=phenotype_ids,
            promoted_mechanism_id=model.promoted_mechanism_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            id=model.id,
        )

    @staticmethod
    def to_model(
        entity: StatementOfUnderstanding,
        model: StatementModel | None = None,
    ) -> StatementModel:
        target = model or StatementModel()
        target.research_space_id = str(entity.research_space_id)
        target.title = entity.title
        target.summary = entity.summary
        target.evidence_tier = StatementMapper._evidence_tier_value(
            entity.evidence_tier,
        )
        target.confidence_score = entity.confidence_score
        target.status = StatementMapper._status_value(entity.status)
        target.source = entity.source
        target.protein_domains = [
            domain.model_dump() for domain in entity.protein_domains
        ]
        target.promoted_mechanism_id = entity.promoted_mechanism_id
        if entity.created_at:
            target.created_at = entity.created_at
        if entity.updated_at:
            target.updated_at = entity.updated_at
        return target

    @staticmethod
    def to_domain_sequence(
        models: Sequence[StatementModel],
    ) -> list[StatementOfUnderstanding]:
        return [StatementMapper.to_domain(model) for model in models]

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
    def _normalize_status(value: str | None) -> StatementStatus:
        if not value:
            return StatementStatus.DRAFT
        try:
            return StatementStatus(value)
        except ValueError:
            return StatementStatus.DRAFT

    @staticmethod
    def _status_value(value: StatementStatus | str) -> str:
        if isinstance(value, StatementStatus):
            return value.value
        return str(value)


__all__ = ["StatementMapper"]
