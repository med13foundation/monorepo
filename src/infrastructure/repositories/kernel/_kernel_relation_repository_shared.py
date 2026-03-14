"""Shared utility types for kernel relation repositories."""

from __future__ import annotations

from uuid import UUID

from src.graph.core.relation_autopromotion_policy import (
    DEFAULT_RELATION_AUTOPROMOTION_EVIDENCE_TIER,
)

_EVIDENCE_TIER_RANK: dict[str, int] = {
    "EXPERT_CURATED": 6,
    "CLINICAL": 5,
    "EXPERIMENTAL": 4,
    "LITERATURE": 3,
    "STRUCTURED_DATA": 2,
    "COMPUTATIONAL": 1,
}


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
        return DEFAULT_RELATION_AUTOPROMOTION_EVIDENCE_TIER
    normalized = value.strip().upper()
    if not normalized:
        return DEFAULT_RELATION_AUTOPROMOTION_EVIDENCE_TIER
    return normalized


def _tier_rank(value: str | None) -> int:
    if value is None:
        return 0
    return _EVIDENCE_TIER_RANK.get(value.strip().upper(), 0)


__all__ = [
    "_as_uuid",
    "_clamp_confidence",
    "_normalize_evidence_tier",
    "_try_as_uuid",
]
