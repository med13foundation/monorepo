"""Graph-fallback helper functions for pipeline orchestration."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.domain.agents.contracts.graph_connection import ProposedRelation


def extract_graph_fallback_relations_from_extraction_summary(  # noqa: C901, PLR0912
    extraction_summary: object,
    *,
    max_relations_per_seed: int = 8,
) -> dict[str, tuple[ProposedRelation, ...]]:
    """Build graph fallback relation payloads from extraction summary metadata."""
    from src.domain.agents.contracts.graph_connection import ProposedRelation

    raw_payloads = getattr(
        extraction_summary,
        "derived_graph_fallback_relation_payloads",
        (),
    )
    if not isinstance(raw_payloads, list | tuple):
        return {}

    relations_by_seed: dict[str, list[ProposedRelation]] = {}
    seen_keys: set[tuple[str, str, str, str]] = set()
    for raw_payload in raw_payloads:
        if not isinstance(raw_payload, dict):
            continue
        seed_value = raw_payload.get("seed_entity_id")
        source_value = raw_payload.get("source_id")
        relation_value = raw_payload.get("relation_type")
        target_value = raw_payload.get("target_id")
        if (
            not isinstance(seed_value, str)
            or not isinstance(source_value, str)
            or not isinstance(relation_value, str)
            or not isinstance(target_value, str)
        ):
            continue

        normalized_seed = seed_value.strip()
        normalized_source = source_value.strip()
        normalized_relation = relation_value.strip().upper()[:64]
        normalized_target = target_value.strip()
        if (
            not normalized_seed
            or not normalized_source
            or not normalized_relation
            or not normalized_target
            or normalized_source == normalized_target
        ):
            continue
        try:
            UUID(normalized_seed)
            UUID(normalized_source)
            UUID(normalized_target)
        except ValueError:
            continue

        relation_key = (
            normalized_seed,
            normalized_source,
            normalized_relation,
            normalized_target,
        )
        if relation_key in seen_keys:
            continue
        seen_keys.add(relation_key)

        confidence_value = raw_payload.get("confidence")
        if isinstance(confidence_value, bool):
            normalized_confidence = 0.35
        elif isinstance(confidence_value, float | int):
            normalized_confidence = max(
                0.05,
                min(float(confidence_value), 0.49),
            )
        else:
            normalized_confidence = 0.35

        evidence_summary_value = raw_payload.get("evidence_summary")
        if isinstance(evidence_summary_value, str) and evidence_summary_value.strip():
            evidence_summary = evidence_summary_value.strip()[:2000]
        else:
            evidence_summary = (
                "Promoted from extraction-stage relation candidate as graph "
                "fallback; review required."
            )
        reason_value = raw_payload.get("reason")
        reason = (
            reason_value.strip()
            if isinstance(reason_value, str) and reason_value.strip()
            else "rejected_relation_candidate"
        )
        validation_state_value = raw_payload.get("validation_state")
        validation_state = (
            validation_state_value.strip().upper()
            if isinstance(validation_state_value, str)
            and validation_state_value.strip()
            else "UNDEFINED"
        )

        seed_relations = relations_by_seed.setdefault(normalized_seed, [])
        if len(seed_relations) >= max_relations_per_seed:
            continue
        seed_relations.append(
            ProposedRelation(
                source_id=normalized_source,
                relation_type=normalized_relation,
                target_id=normalized_target,
                confidence=normalized_confidence,
                evidence_summary=evidence_summary,
                evidence_tier="COMPUTATIONAL",
                supporting_provenance_ids=[],
                supporting_document_count=0,
                reasoning=(
                    "Fail-open graph fallback using extraction-stage relation "
                    f"candidate ({validation_state}:{reason})."
                ),
            ),
        )

    return {
        seed_entity_id: tuple(seed_relations)
        for seed_entity_id, seed_relations in relations_by_seed.items()
    }


def resolve_graph_seed_limit(
    *,
    env_name: str,
    default: int,
) -> int:
    """Resolve max graph seeds per run from environment with safe fallback."""
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default
    normalized = raw_value.strip()
    if not normalized:
        return default
    if normalized.isdigit():
        parsed = int(normalized)
        return max(parsed, 1)
    return default


def resolve_latest_ingestion_job_id(
    *,
    ingestion_service: object,
    source_id: UUID,
) -> UUID | None:
    """Lookup latest ingestion job id when repository supports source queries."""
    repository_getter = getattr(ingestion_service, "get_job_repository", None)
    if not callable(repository_getter):
        return None
    try:
        recent_jobs = repository_getter().find_by_source(source_id, limit=1)
    except AttributeError:
        return None
    if not recent_jobs:
        return None
    import uuid

    latest_job_id = getattr(recent_jobs[0], "id", None)
    if isinstance(latest_job_id, uuid.UUID):
        return latest_job_id
    return None


__all__ = [
    "extract_graph_fallback_relations_from_extraction_summary",
    "resolve_graph_seed_limit",
    "resolve_latest_ingestion_job_id",
]
