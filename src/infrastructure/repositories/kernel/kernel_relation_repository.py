"""
SQLAlchemy implementation of KernelRelationRepository.

Handles graph-edge CRUD, curation lifecycle, and neighborhood traversal
against the canonical ``relations`` + ``relation_evidence`` tables.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy.engine import CursorResult

from src.domain.entities.kernel.relations import KernelRelation
from src.domain.repositories.kernel.relation_repository import KernelRelationRepository
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel
from src.models.database.research_space import ResearchSpaceModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_DEFAULT_EVIDENCE_TIER = "COMPUTATIONAL"
_EVIDENCE_TIER_RANK: dict[str, int] = {
    "EXPERT_CURATED": 6,
    "CLINICAL": 5,
    "EXPERIMENTAL": 4,
    "LITERATURE": 3,
    "STRUCTURED_DATA": 2,
    "COMPUTATIONAL": 1,
}
_PROMOTABLE_CURATION_STATUSES = {"DRAFT", "UNDER_REVIEW"}
_DEFAULT_MIN_EVIDENCE_TIER = "LITERATURE"
_SPACE_POLICY_SETTINGS_KEY = "relation_auto_promotion"
_SPACE_POLICY_CUSTOM_PREFIX = "relation_autopromote_"


def _read_bool_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _read_int_env(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return max(parsed, minimum)


def _read_float_env(
    name: str,
    default: float,
    *,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = float(raw)
    except ValueError:
        return default
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def _parse_bool_setting(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _parse_int_setting(value: object, *, default: int, minimum: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return max(value, minimum)
    if isinstance(value, float):
        return max(int(value), minimum)
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return default
        return max(parsed, minimum)
    return default


def _parse_float_setting(
    value: object,
    *,
    default: float,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, float | int):
        parsed = float(value)
    elif isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return default
    else:
        return default
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def _normalize_tier_setting(value: object, *, default: str) -> str:
    if not isinstance(value, str):
        return default
    normalized = value.strip().upper()
    if not normalized:
        return default
    return normalized


@dataclass(frozen=True)
class AutoPromotionPolicy:
    """Policy used to auto-promote canonical relations after evidence updates."""

    enabled: bool = True
    min_distinct_sources: int = 3
    min_aggregate_confidence: float = 0.95
    require_distinct_documents: bool = True
    require_distinct_runs: bool = True
    block_if_conflicting_evidence: bool = True
    min_evidence_tier: str = _DEFAULT_MIN_EVIDENCE_TIER
    computational_min_distinct_sources: int = 5
    computational_min_aggregate_confidence: float = 0.99
    conflicting_confidence_threshold: float = 0.5

    @classmethod
    def from_environment(cls) -> AutoPromotionPolicy:
        """Build relation auto-promotion policy from environment variables."""
        normalized_tier = (
            os.getenv(
                "MED13_RELATION_AUTOPROMOTE_MIN_EVIDENCE_TIER",
                _DEFAULT_MIN_EVIDENCE_TIER,
            )
            .strip()
            .upper()
        )
        if not normalized_tier:
            normalized_tier = _DEFAULT_MIN_EVIDENCE_TIER
        return cls(
            enabled=_read_bool_env(
                "MED13_RELATION_AUTOPROMOTE_ENABLED",
                default=True,
            ),
            min_distinct_sources=_read_int_env(
                "MED13_RELATION_AUTOPROMOTE_MIN_DISTINCT_SOURCES",
                3,
                minimum=1,
            ),
            min_aggregate_confidence=_read_float_env(
                "MED13_RELATION_AUTOPROMOTE_MIN_AGGREGATE_CONFIDENCE",
                0.95,
            ),
            require_distinct_documents=_read_bool_env(
                "MED13_RELATION_AUTOPROMOTE_REQUIRE_DISTINCT_DOCUMENTS",
                default=True,
            ),
            require_distinct_runs=_read_bool_env(
                "MED13_RELATION_AUTOPROMOTE_REQUIRE_DISTINCT_RUNS",
                default=True,
            ),
            block_if_conflicting_evidence=_read_bool_env(
                "MED13_RELATION_AUTOPROMOTE_BLOCK_CONFLICTING_EVIDENCE",
                default=True,
            ),
            min_evidence_tier=normalized_tier,
            computational_min_distinct_sources=_read_int_env(
                "MED13_RELATION_AUTOPROMOTE_COMPUTATIONAL_MIN_DISTINCT_SOURCES",
                5,
                minimum=1,
            ),
            computational_min_aggregate_confidence=_read_float_env(
                "MED13_RELATION_AUTOPROMOTE_COMPUTATIONAL_MIN_AGGREGATE_CONFIDENCE",
                0.99,
            ),
            conflicting_confidence_threshold=_read_float_env(
                "MED13_RELATION_AUTOPROMOTE_CONFLICTING_CONFIDENCE_THRESHOLD",
                0.5,
            ),
        )


@dataclass(frozen=True)
class AutoPromotionDecision:
    """Outcome details for one relation auto-promotion evaluation."""

    outcome: Literal["promoted", "kept"]
    reason: str
    previous_status: str
    current_status: str
    all_computational: bool
    required_sources: int
    required_confidence: float
    distinct_source_count: int
    distinct_document_count: int
    distinct_run_count: int
    aggregate_confidence: float
    highest_evidence_tier: str | None


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _try_as_uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return UUID(normalized)
    except ValueError:
        return None


def _clamp_confidence(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _normalize_evidence_tier(value: str | None) -> str:
    if value is None:
        return _DEFAULT_EVIDENCE_TIER
    normalized = value.strip().upper()
    if not normalized:
        return _DEFAULT_EVIDENCE_TIER
    return normalized


def _tier_rank(value: str | None) -> int:
    if value is None:
        return 0
    return _EVIDENCE_TIER_RANK.get(value.strip().upper(), 0)


class SqlAlchemyKernelRelationRepository(KernelRelationRepository):
    """SQLAlchemy implementation of the kernel relation repository."""

    def __init__(
        self,
        session: Session,
        *,
        auto_promotion_policy: AutoPromotionPolicy | None = None,
    ) -> None:
        self._session = session
        self._auto_promotion_policy = (
            auto_promotion_policy or AutoPromotionPolicy.from_environment()
        )

    # ── Write ─────────────────────────────────────────────────────────

    def create(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_id: str,
        relation_type: str,
        target_id: str,
        confidence: float = 0.5,
        evidence_summary: str | None = None,
        evidence_tier: str | None = None,
        curation_status: str = "DRAFT",
        provenance_id: str | None = None,
        source_document_id: str | None = None,
        agent_run_id: str | None = None,
    ) -> KernelRelation:
        canonical_stmt = select(RelationModel).where(
            RelationModel.research_space_id == _as_uuid(research_space_id),
            RelationModel.source_id == _as_uuid(source_id),
            RelationModel.relation_type == relation_type,
            RelationModel.target_id == _as_uuid(target_id),
        )
        relation = self._session.scalars(canonical_stmt).first()

        if relation is None:
            relation = RelationModel(
                id=uuid4(),
                research_space_id=_as_uuid(research_space_id),
                source_id=_as_uuid(source_id),
                relation_type=relation_type,
                target_id=_as_uuid(target_id),
                aggregate_confidence=0.0,
                source_count=0,
                highest_evidence_tier=None,
                curation_status=curation_status,
                provenance_id=(
                    _as_uuid(provenance_id) if provenance_id is not None else None
                ),
            )
            self._session.add(relation)
            self._session.flush()
        normalized_confidence = _clamp_confidence(confidence)
        normalized_tier = _normalize_evidence_tier(evidence_tier)
        provenance_uuid = _as_uuid(provenance_id) if provenance_id is not None else None
        source_document_uuid = _try_as_uuid(source_document_id)
        agent_run_uuid = _try_as_uuid(agent_run_id)

        if provenance_uuid is not None and relation.provenance_id is None:
            relation.provenance_id = provenance_uuid

        duplicate_stmt = select(RelationEvidenceModel.id).where(
            RelationEvidenceModel.relation_id == relation.id,
            RelationEvidenceModel.confidence == normalized_confidence,
            RelationEvidenceModel.evidence_tier == normalized_tier,
        )
        if evidence_summary is None:
            duplicate_stmt = duplicate_stmt.where(
                RelationEvidenceModel.evidence_summary.is_(None),
            )
        else:
            duplicate_stmt = duplicate_stmt.where(
                RelationEvidenceModel.evidence_summary == evidence_summary,
            )
        if provenance_uuid is None:
            duplicate_stmt = duplicate_stmt.where(
                RelationEvidenceModel.provenance_id.is_(None),
            )
        else:
            duplicate_stmt = duplicate_stmt.where(
                RelationEvidenceModel.provenance_id == provenance_uuid,
            )
        duplicate_evidence_id = self._session.scalar(duplicate_stmt.limit(1))

        if duplicate_evidence_id is None:
            evidence = RelationEvidenceModel(
                id=uuid4(),
                relation_id=relation.id,
                confidence=normalized_confidence,
                evidence_summary=evidence_summary,
                evidence_tier=normalized_tier,
                provenance_id=provenance_uuid,
                source_document_id=source_document_uuid,
                agent_run_id=agent_run_uuid,
            )
            self._session.add(evidence)
            self._session.flush()

        self._recompute_relation_aggregate(relation.id)
        auto_promotion_decision = self._apply_auto_promotion(relation.id)
        self._log_auto_promotion_decision(
            relation=relation,
            decision=auto_promotion_decision,
        )
        self._session.flush()
        return KernelRelation.model_validate(relation)

    @staticmethod
    def _log_auto_promotion_decision(
        *,
        relation: RelationModel,
        decision: AutoPromotionDecision,
    ) -> None:
        logger.info(
            "Relation auto-promotion evaluated",
            extra={
                "event": "relation_auto_promotion",
                "relation_id": str(relation.id),
                "research_space_id": str(relation.research_space_id),
                "source_id": str(relation.source_id),
                "target_id": str(relation.target_id),
                "relation_type": relation.relation_type,
                "auto_promotion_outcome": decision.outcome,
                "auto_promotion_reason": decision.reason,
                "auto_promotion_previous_status": decision.previous_status,
                "auto_promotion_current_status": decision.current_status,
                "auto_promotion_all_computational": decision.all_computational,
                "auto_promotion_required_sources": decision.required_sources,
                "auto_promotion_required_confidence": decision.required_confidence,
                "auto_promotion_distinct_source_count": (
                    decision.distinct_source_count
                ),
                "auto_promotion_distinct_document_count": (
                    decision.distinct_document_count
                ),
                "auto_promotion_distinct_run_count": decision.distinct_run_count,
                "aggregate_confidence": decision.aggregate_confidence,
                "highest_evidence_tier": decision.highest_evidence_tier,
            },
        )

    def _resolve_auto_promotion_policy(
        self,
        *,
        research_space_id: UUID,
    ) -> AutoPromotionPolicy:
        default_policy = self._auto_promotion_policy
        settings_payload = self._extract_space_policy_settings(
            research_space_id=research_space_id,
        )
        if not settings_payload:
            return default_policy

        return AutoPromotionPolicy(
            enabled=_parse_bool_setting(
                settings_payload.get("enabled"),
                default=default_policy.enabled,
            ),
            min_distinct_sources=_parse_int_setting(
                settings_payload.get("min_distinct_sources"),
                default=default_policy.min_distinct_sources,
                minimum=1,
            ),
            min_aggregate_confidence=_parse_float_setting(
                settings_payload.get("min_aggregate_confidence"),
                default=default_policy.min_aggregate_confidence,
            ),
            require_distinct_documents=_parse_bool_setting(
                settings_payload.get("require_distinct_documents"),
                default=default_policy.require_distinct_documents,
            ),
            require_distinct_runs=_parse_bool_setting(
                settings_payload.get("require_distinct_runs"),
                default=default_policy.require_distinct_runs,
            ),
            block_if_conflicting_evidence=_parse_bool_setting(
                settings_payload.get("block_if_conflicting_evidence"),
                default=default_policy.block_if_conflicting_evidence,
            ),
            min_evidence_tier=_normalize_tier_setting(
                settings_payload.get("min_evidence_tier"),
                default=default_policy.min_evidence_tier,
            ),
            computational_min_distinct_sources=_parse_int_setting(
                settings_payload.get("computational_min_distinct_sources"),
                default=default_policy.computational_min_distinct_sources,
                minimum=1,
            ),
            computational_min_aggregate_confidence=_parse_float_setting(
                settings_payload.get("computational_min_aggregate_confidence"),
                default=default_policy.computational_min_aggregate_confidence,
            ),
            conflicting_confidence_threshold=_parse_float_setting(
                settings_payload.get("conflicting_confidence_threshold"),
                default=default_policy.conflicting_confidence_threshold,
            ),
        )

    def _extract_space_policy_settings(
        self,
        *,
        research_space_id: UUID,
    ) -> dict[str, object]:
        model = self._session.get(ResearchSpaceModel, research_space_id)
        if model is None or not isinstance(model.settings, dict):
            return {}

        settings_payload: dict[str, object] = {}
        raw_policy = model.settings.get(_SPACE_POLICY_SETTINGS_KEY)
        if isinstance(raw_policy, dict):
            for key, value in raw_policy.items():
                settings_payload[str(key)] = value

        custom_settings = model.settings.get("custom")
        if isinstance(custom_settings, dict):
            for key, value in custom_settings.items():
                if not isinstance(key, str):
                    continue
                if not key.startswith(_SPACE_POLICY_CUSTOM_PREFIX):
                    continue
                normalized_key = key.removeprefix(_SPACE_POLICY_CUSTOM_PREFIX)
                if normalized_key:
                    settings_payload[normalized_key] = value

        return settings_payload

    def _apply_auto_promotion(  # noqa: C901, PLR0911, PLR0912
        self,
        relation_id: UUID,
    ) -> AutoPromotionDecision:
        """Auto-promote relation status when policy thresholds are satisfied."""
        relation_model = self._session.get(RelationModel, relation_id)
        if relation_model is None:
            return AutoPromotionDecision(
                outcome="kept",
                reason="relation_not_found",
                previous_status="UNKNOWN",
                current_status="UNKNOWN",
                all_computational=False,
                required_sources=0,
                required_confidence=0.0,
                distinct_source_count=0,
                distinct_document_count=0,
                distinct_run_count=0,
                aggregate_confidence=0.0,
                highest_evidence_tier=None,
            )

        policy = self._resolve_auto_promotion_policy(
            research_space_id=relation_model.research_space_id,
        )
        if not policy.enabled:
            normalized_status = relation_model.curation_status.strip().upper()
            return AutoPromotionDecision(
                outcome="kept",
                reason="policy_disabled",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=False,
                required_sources=0,
                required_confidence=0.0,
                distinct_source_count=0,
                distinct_document_count=0,
                distinct_run_count=0,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        normalized_status = relation_model.curation_status.strip().upper()
        if normalized_status not in _PROMOTABLE_CURATION_STATUSES:
            return AutoPromotionDecision(
                outcome="kept",
                reason="status_not_promotable",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=False,
                required_sources=0,
                required_confidence=0.0,
                distinct_source_count=0,
                distinct_document_count=0,
                distinct_run_count=0,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        evidences = self._list_relation_evidences(relation_id)
        if not evidences:
            return AutoPromotionDecision(
                outcome="kept",
                reason="no_evidence",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=False,
                required_sources=0,
                required_confidence=0.0,
                distinct_source_count=0,
                distinct_document_count=0,
                distinct_run_count=0,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        all_computational = self._all_evidence_is_computational(evidences)
        required_sources = policy.min_distinct_sources
        required_confidence = policy.min_aggregate_confidence

        if all_computational:
            required_sources = max(
                required_sources,
                policy.computational_min_distinct_sources,
            )
            required_confidence = max(
                required_confidence,
                policy.computational_min_aggregate_confidence,
            )

        distinct_source_count = self._count_distinct_sources(evidences)
        distinct_document_count = self._count_distinct_documents(evidences)
        distinct_run_count = self._count_distinct_runs(evidences)

        if not all_computational and _tier_rank(
            relation_model.highest_evidence_tier,
        ) < _tier_rank(policy.min_evidence_tier):
            return AutoPromotionDecision(
                outcome="kept",
                reason="tier_below_threshold",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=all_computational,
                required_sources=required_sources,
                required_confidence=required_confidence,
                distinct_source_count=distinct_source_count,
                distinct_document_count=distinct_document_count,
                distinct_run_count=distinct_run_count,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        if policy.block_if_conflicting_evidence and self._has_conflicting_evidence(
            evidences,
            policy,
        ):
            return AutoPromotionDecision(
                outcome="kept",
                reason="conflicting_evidence_detected",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=all_computational,
                required_sources=required_sources,
                required_confidence=required_confidence,
                distinct_source_count=distinct_source_count,
                distinct_document_count=distinct_document_count,
                distinct_run_count=distinct_run_count,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        if distinct_source_count < required_sources:
            return AutoPromotionDecision(
                outcome="kept",
                reason="insufficient_distinct_sources",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=all_computational,
                required_sources=required_sources,
                required_confidence=required_confidence,
                distinct_source_count=distinct_source_count,
                distinct_document_count=distinct_document_count,
                distinct_run_count=distinct_run_count,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        if (
            policy.require_distinct_documents
            and 0 < distinct_document_count < required_sources
        ):
            return AutoPromotionDecision(
                outcome="kept",
                reason="insufficient_distinct_documents",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=all_computational,
                required_sources=required_sources,
                required_confidence=required_confidence,
                distinct_source_count=distinct_source_count,
                distinct_document_count=distinct_document_count,
                distinct_run_count=distinct_run_count,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        if policy.require_distinct_runs and 0 < distinct_run_count < required_sources:
            return AutoPromotionDecision(
                outcome="kept",
                reason="insufficient_distinct_runs",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=all_computational,
                required_sources=required_sources,
                required_confidence=required_confidence,
                distinct_source_count=distinct_source_count,
                distinct_document_count=distinct_document_count,
                distinct_run_count=distinct_run_count,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        if relation_model.aggregate_confidence < required_confidence:
            return AutoPromotionDecision(
                outcome="kept",
                reason="insufficient_aggregate_confidence",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=all_computational,
                required_sources=required_sources,
                required_confidence=required_confidence,
                distinct_source_count=distinct_source_count,
                distinct_document_count=distinct_document_count,
                distinct_run_count=distinct_run_count,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        relation_model.curation_status = "APPROVED"
        relation_model.reviewed_at = datetime.now(UTC)
        return AutoPromotionDecision(
            outcome="promoted",
            reason="thresholds_met",
            previous_status=normalized_status,
            current_status=relation_model.curation_status,
            all_computational=all_computational,
            required_sources=required_sources,
            required_confidence=required_confidence,
            distinct_source_count=distinct_source_count,
            distinct_document_count=distinct_document_count,
            distinct_run_count=distinct_run_count,
            aggregate_confidence=float(relation_model.aggregate_confidence),
            highest_evidence_tier=relation_model.highest_evidence_tier,
        )

    def _list_relation_evidences(
        self,
        relation_id: UUID,
    ) -> list[RelationEvidenceModel]:
        stmt = select(RelationEvidenceModel).where(
            RelationEvidenceModel.relation_id == relation_id,
        )
        return list(self._session.scalars(stmt).all())

    @staticmethod
    def _count_distinct_sources(evidences: list[RelationEvidenceModel]) -> int:
        distinct_sources: set[str] = set()
        for evidence in evidences:
            if evidence.provenance_id is not None:
                distinct_sources.add(f"provenance:{evidence.provenance_id}")
            elif evidence.source_document_id is not None:
                distinct_sources.add(f"document:{evidence.source_document_id}")
            elif evidence.agent_run_id is not None:
                distinct_sources.add(f"run:{evidence.agent_run_id}")
            else:
                distinct_sources.add(f"evidence:{evidence.id}")
        return len(distinct_sources)

    @staticmethod
    def _count_distinct_documents(evidences: list[RelationEvidenceModel]) -> int:
        distinct_documents = {
            evidence.source_document_id
            for evidence in evidences
            if evidence.source_document_id is not None
        }
        return len(distinct_documents)

    @staticmethod
    def _count_distinct_runs(evidences: list[RelationEvidenceModel]) -> int:
        distinct_runs = {
            evidence.agent_run_id
            for evidence in evidences
            if evidence.agent_run_id is not None
        }
        return len(distinct_runs)

    @staticmethod
    def _all_evidence_is_computational(evidences: list[RelationEvidenceModel]) -> bool:
        if not evidences:
            return False
        return all(
            _normalize_evidence_tier(evidence.evidence_tier) == _DEFAULT_EVIDENCE_TIER
            for evidence in evidences
        )

    @staticmethod
    def _has_conflicting_evidence(
        evidences: list[RelationEvidenceModel],
        policy: AutoPromotionPolicy,
    ) -> bool:
        return any(
            float(evidence.confidence) < policy.conflicting_confidence_threshold
            for evidence in evidences
        )

    # ── Read ──────────────────────────────────────────────────────────

    def get_by_id(self, relation_id: str) -> KernelRelation | None:
        model = self._session.get(RelationModel, _as_uuid(relation_id))
        return KernelRelation.model_validate(model) if model is not None else None

    def find_by_source(
        self,
        source_id: str,
        *,
        relation_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        stmt = select(RelationModel).where(
            RelationModel.source_id == _as_uuid(source_id),
        )
        if relation_type is not None:
            stmt = stmt.where(RelationModel.relation_type == relation_type)
        stmt = stmt.order_by(RelationModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelRelation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_by_target(
        self,
        target_id: str,
        *,
        relation_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        stmt = select(RelationModel).where(
            RelationModel.target_id == _as_uuid(target_id),
        )
        if relation_type is not None:
            stmt = stmt.where(RelationModel.relation_type == relation_type)
        stmt = stmt.order_by(RelationModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelRelation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_neighborhood(
        self,
        entity_id: str,
        *,
        depth: int = 1,
        relation_types: list[str] | None = None,
    ) -> list[KernelRelation]:
        """
        Multi-hop neighborhood traversal.

        For depth=1, returns all relations where the entity is source or target.
        For depth>1, iteratively expands the frontier.
        """
        visited_ids: set[UUID] = set()
        frontier: set[UUID] = {_as_uuid(entity_id)}
        all_relations: list[RelationModel] = []

        for _hop in range(depth):
            if not frontier:
                break

            stmt = select(RelationModel).where(
                or_(
                    RelationModel.source_id.in_(frontier),
                    RelationModel.target_id.in_(frontier),
                ),
            )
            if relation_types:
                stmt = stmt.where(RelationModel.relation_type.in_(relation_types))

            hop_relations = list(self._session.scalars(stmt).all())
            all_relations.extend(hop_relations)

            visited_ids |= frontier
            next_frontier: set[UUID] = set()
            for rel in hop_relations:
                src_id = _as_uuid(rel.source_id)
                tgt_id = _as_uuid(rel.target_id)
                if src_id not in visited_ids:
                    next_frontier.add(src_id)
                if tgt_id not in visited_ids:
                    next_frontier.add(tgt_id)
            frontier = next_frontier

        # Deduplicate (a relation may appear in multiple hops)
        seen: set[str] = set()
        unique: list[RelationModel] = []
        for rel in all_relations:
            rel_id = str(rel.id)
            if rel_id not in seen:
                seen.add(rel_id)
                unique.append(rel)
        return [KernelRelation.model_validate(model) for model in unique]

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        stmt = select(RelationModel).where(
            RelationModel.research_space_id == _as_uuid(research_space_id),
        )
        if relation_type is not None:
            stmt = stmt.where(RelationModel.relation_type == relation_type)
        if curation_status is not None:
            stmt = stmt.where(RelationModel.curation_status == curation_status)
        stmt = stmt.order_by(RelationModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelRelation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def search_by_text(
        self,
        research_space_id: str,
        query: str,
        *,
        limit: int = 20,
    ) -> list[KernelRelation]:
        stmt = (
            select(RelationModel)
            .outerjoin(
                RelationEvidenceModel,
                RelationEvidenceModel.relation_id == RelationModel.id,
            )
            .where(
                RelationModel.research_space_id == _as_uuid(research_space_id),
                or_(
                    RelationModel.relation_type.ilike(f"%{query}%"),
                    RelationModel.curation_status.ilike(f"%{query}%"),
                    RelationEvidenceModel.evidence_summary.ilike(f"%{query}%"),
                ),
            )
            .order_by(RelationModel.updated_at.desc())
            .limit(limit)
        )
        models = list(self._session.scalars(stmt).all())
        seen: set[UUID] = set()
        unique_models: list[RelationModel] = []
        for model in models:
            if model.id in seen:
                continue
            seen.add(model.id)
            unique_models.append(model)
        return [KernelRelation.model_validate(model) for model in unique_models]

    # ── Curation lifecycle ────────────────────────────────────────────

    def update_curation(
        self,
        relation_id: str,
        *,
        curation_status: str,
        reviewed_by: str,
        reviewed_at: datetime | None = None,
    ) -> KernelRelation:
        relation_model = self._session.get(RelationModel, _as_uuid(relation_id))
        if relation_model is None:
            msg = f"Relation {relation_id} not found"
            raise ValueError(msg)
        relation_model.curation_status = curation_status
        relation_model.reviewed_by = _as_uuid(reviewed_by)
        relation_model.reviewed_at = reviewed_at or datetime.now(UTC)
        self._session.flush()
        return KernelRelation.model_validate(relation_model)

    # ── Delete ────────────────────────────────────────────────────────

    def delete(self, relation_id: str) -> bool:
        relation_model = self._session.get(RelationModel, _as_uuid(relation_id))
        if relation_model is None:
            return False
        self._session.delete(relation_model)
        self._session.flush()
        return True

    def delete_by_provenance(self, provenance_id: str) -> int:
        target_provenance_id = _as_uuid(provenance_id)
        relation_ids = list(
            set(
                self._session.scalars(
                    select(RelationEvidenceModel.relation_id).where(
                        RelationEvidenceModel.provenance_id == target_provenance_id,
                    ),
                ).all(),
            ),
        )
        if not relation_ids:
            return 0

        self._session.execute(
            sa_delete(RelationEvidenceModel).where(
                RelationEvidenceModel.provenance_id == target_provenance_id,
            ),
        )

        for relation_id in relation_ids:
            relation_model = self._session.get(RelationModel, relation_id)
            if relation_model is None:
                continue
            self._recompute_relation_aggregate(relation_id)

        delete_result = self._session.execute(
            sa_delete(RelationModel).where(
                RelationModel.id.in_(relation_ids),
                ~RelationModel.evidences.any(),
            ),
        )
        count = (
            int(delete_result.rowcount or 0)
            if isinstance(delete_result, CursorResult)
            else 0
        )
        self._session.flush()
        logger.info(
            "Rolled back %d relations for provenance %s",
            count,
            provenance_id,
        )
        return count

    # ── Aggregate helpers ─────────────────────────────────────────────

    def _recompute_relation_aggregate(self, relation_id: UUID) -> None:
        relation_model = self._session.get(RelationModel, relation_id)
        if relation_model is None:
            return

        evidences = list(
            self._session.scalars(
                select(RelationEvidenceModel).where(
                    RelationEvidenceModel.relation_id == relation_id,
                ),
            ).all(),
        )
        if not evidences:
            relation_model.aggregate_confidence = 0.0
            relation_model.source_count = 0
            relation_model.highest_evidence_tier = None
            relation_model.updated_at = datetime.now(UTC)
            return

        product = 1.0
        highest_tier: str | None = None
        highest_rank = -1

        for evidence in evidences:
            confidence = _clamp_confidence(float(evidence.confidence))
            product *= 1.0 - confidence

            tier = _normalize_evidence_tier(evidence.evidence_tier)
            rank = _tier_rank(tier)
            if rank > highest_rank:
                highest_rank = rank
                highest_tier = tier

        relation_model.aggregate_confidence = _clamp_confidence(1.0 - product)
        relation_model.source_count = len(evidences)
        relation_model.highest_evidence_tier = highest_tier
        relation_model.updated_at = datetime.now(UTC)

    def count_by_research_space(self, research_space_id: str) -> int:
        """Count total relations in a research space."""
        result = self._session.execute(
            select(func.count()).where(
                RelationModel.research_space_id == _as_uuid(research_space_id),
            ),
        )
        return result.scalar_one()


__all__ = ["SqlAlchemyKernelRelationRepository"]
