"""Application service for graph-driven hypothesis generation."""

from __future__ import annotations

from collections.abc import Iterable  # noqa: TC003
from dataclasses import dataclass
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

from src.application.services.claim_first_metrics import increment_metric
from src.domain.agents.contexts.graph_connection_context import GraphConnectionContext
from src.domain.value_objects.relation_types import normalize_relation_type

if TYPE_CHECKING:
    from src.application.services.kernel.kernel_claim_participant_service import (
        KernelClaimParticipantService,
    )
    from src.application.services.kernel.kernel_reasoning_path_service import (
        KernelReasoningPathService,
    )
    from src.application.services.kernel.kernel_relation_claim_service import (
        KernelRelationClaimService,
    )
    from src.domain.agents.contracts.graph_connection import ProposedRelation
    from src.domain.agents.ports.graph_connection_port import GraphConnectionPort
    from src.domain.entities.kernel.relation_claims import KernelRelationClaim
    from src.domain.ports import DictionaryPort
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
    from src.domain.repositories.kernel.relation_repository import (
        KernelRelationRepository,
    )
    from src.type_definitions.common import JSONObject


_SCORE_THRESHOLD = 0.45
_GRAPH_ORIGIN = "graph_agent"
_PATH_ORIGIN = "reasoning_path"
_DEFAULT_SEED_LIMIT = 40
_SEED_CLAIM_CONFIDENCE_THRESHOLD = 0.7


@dataclass(frozen=True)
class HypothesisGenerationServiceDependencies:
    """Dependencies required for hypothesis generation orchestration."""

    graph_connection_agent: GraphConnectionPort
    relation_claim_service: KernelRelationClaimService
    claim_participant_service: KernelClaimParticipantService
    entity_repository: KernelEntityRepository
    relation_repository: KernelRelationRepository
    dictionary_service: DictionaryPort
    reasoning_path_service: KernelReasoningPathService | None = None


@dataclass(frozen=True)
class HypothesisGenerationResult:
    """Outcome of one hypothesis-generation run."""

    run_id: str
    requested_seed_count: int
    used_seed_count: int
    candidates_seen: int
    created_count: int
    deduped_count: int
    errors: tuple[str, ...]
    hypotheses: tuple[KernelRelationClaim, ...]


@dataclass(frozen=True)
class _RawCandidate:
    seed_entity_id: str
    source_entity_id: str
    target_entity_id: str
    source_type: str
    target_type: str
    relation_type: str
    source_label: str | None
    target_label: str | None
    relation_confidence: float
    evidence_density: float
    novelty: float
    relation_allowed: bool
    self_loop: bool
    supporting_provenance_ids: tuple[str, ...]
    supporting_document_count: int
    evidence_summary: str
    reasoning: str
    graph_agent_run_id: str | None


@dataclass(frozen=True)
class _ScoredCandidate:
    raw: _RawCandidate
    relation_diversity: float
    score: float


@dataclass(frozen=True)
class _PathCandidate:
    reasoning_path_id: str
    start_entity_id: str
    end_entity_id: str
    source_type: str
    target_type: str
    relation_type: str
    source_label: str | None
    target_label: str | None
    confidence: float
    path_length: int
    supporting_claim_ids: tuple[str, ...]


class HypothesisGenerationService:
    """Generate hypothesis relation claims from graph-agent exploration."""

    def __init__(
        self,
        dependencies: HypothesisGenerationServiceDependencies,
    ) -> None:
        self._graph_agent = dependencies.graph_connection_agent
        self._claims = dependencies.relation_claim_service
        self._participants = dependencies.claim_participant_service
        self._entities = dependencies.entity_repository
        self._relations = dependencies.relation_repository
        self._dictionary = dependencies.dictionary_service
        self._reasoning_paths = dependencies.reasoning_path_service

    async def generate_hypotheses(  # noqa: PLR0912, PLR0913, PLR0915, C901
        self,
        *,
        research_space_id: str,
        seed_entity_ids: list[str] | None,
        source_type: str,
        relation_types: list[str] | None,
        max_depth: int,
        max_hypotheses: int,
        model_id: str | None,
    ) -> HypothesisGenerationResult:
        """Run graph-agent exploration and persist top scored hypothesis claims."""
        run_id = str(uuid4())
        requested_seeds = _normalize_seed_entity_ids(seed_entity_ids)
        requested_seed_count = len(requested_seeds)

        resolved_seed_ids = self._resolve_seed_entity_ids(
            research_space_id=research_space_id,
            requested_seed_entity_ids=requested_seeds,
            max_hypotheses=max_hypotheses,
        )

        if not resolved_seed_ids:
            return HypothesisGenerationResult(
                run_id=run_id,
                requested_seed_count=requested_seed_count,
                used_seed_count=0,
                candidates_seen=0,
                created_count=0,
                deduped_count=0,
                errors=("no_seed_entities_resolved",),
                hypotheses=(),
            )

        normalized_relation_types = _normalize_relation_types(relation_types)
        active_fingerprints = self._load_active_hypothesis_fingerprints(
            research_space_id,
        )

        raw_candidates: list[_RawCandidate] = []
        path_candidates: list[_PathCandidate] = []
        errors: list[str] = []

        if self._reasoning_paths is not None:
            path_candidates, path_errors = self._load_reasoning_path_candidates(
                research_space_id=research_space_id,
                seed_entity_ids=resolved_seed_ids,
                max_hypotheses=max_hypotheses,
            )
            errors.extend(path_errors)

        for seed_entity_id in resolved_seed_ids:
            try:
                context = GraphConnectionContext(
                    seed_entity_id=seed_entity_id,
                    source_type=source_type,
                    research_space_id=research_space_id,
                    relation_types=normalized_relation_types,
                    max_depth=max_depth,
                    shadow_mode=True,
                )
                contract = await self._graph_agent.discover(
                    context,
                    model_id=model_id,
                )
            except Exception as exc:  # noqa: BLE001 - do not fail whole run on one seed
                errors.append(
                    f"seed_discovery_failed:{seed_entity_id}:{type(exc).__name__}",
                )
                continue

            seed_candidates, seed_errors = self._normalize_candidates_for_seed(
                research_space_id=research_space_id,
                seed_entity_id=seed_entity_id,
                candidates=contract.proposed_relations,
                graph_agent_run_id=_normalize_optional_text(contract.agent_run_id),
            )
            raw_candidates.extend(seed_candidates)
            errors.extend(seed_errors)

        scored_candidates = self._score_candidates(raw_candidates)
        scored_candidates.sort(
            key=lambda item: (
                -item.score,
                -item.raw.relation_confidence,
                item.raw.relation_type,
            ),
        )
        eligible_candidates = [
            candidate
            for candidate in scored_candidates
            if candidate.score >= _SCORE_THRESHOLD
        ]

        created: list[KernelRelationClaim] = []
        deduped_count = 0
        emitted_fingerprints: set[str] = set()
        for path_candidate in path_candidates:
            if len(created) >= max_hypotheses:
                break

            fingerprint = _build_fingerprint(
                source_entity_id=path_candidate.start_entity_id,
                relation_type=path_candidate.relation_type,
                target_entity_id=path_candidate.end_entity_id,
                origin=f"{_PATH_ORIGIN}:{path_candidate.reasoning_path_id}",
            )
            if (
                fingerprint in active_fingerprints
                or fingerprint in emitted_fingerprints
            ):
                deduped_count += 1
                continue

            claim = self._create_claim_from_path_candidate(
                candidate=path_candidate,
                research_space_id=research_space_id,
                run_id=run_id,
                fingerprint=fingerprint,
            )
            created.append(claim)
            emitted_fingerprints.add(fingerprint)
            active_fingerprints.add(fingerprint)

        for scored_candidate in eligible_candidates:
            if len(created) >= max_hypotheses:
                break

            fingerprint = _build_fingerprint(
                source_entity_id=scored_candidate.raw.source_entity_id,
                relation_type=scored_candidate.raw.relation_type,
                target_entity_id=scored_candidate.raw.target_entity_id,
                origin=_GRAPH_ORIGIN,
            )
            if (
                fingerprint in active_fingerprints
                or fingerprint in emitted_fingerprints
            ):
                deduped_count += 1
                continue

            claim = self._create_claim_from_candidate(
                candidate=scored_candidate,
                research_space_id=research_space_id,
                run_id=run_id,
                fingerprint=fingerprint,
                seed_entity_id=scored_candidate.raw.seed_entity_id,
            )
            created.append(claim)
            emitted_fingerprints.add(fingerprint)
            active_fingerprints.add(fingerprint)

        if not created:
            if not raw_candidates:
                errors.append("no_candidates_discovered")
            elif not eligible_candidates:
                errors.append("all_candidates_below_threshold")
            elif deduped_count >= len(eligible_candidates):
                errors.append("all_candidates_deduped")
            else:
                errors.append("no_candidates_selected")

        if created:
            increment_metric(
                "hypotheses_auto_generated_total",
                delta=len(created),
                tags={"research_space_id": research_space_id},
            )
        if deduped_count > 0:
            increment_metric(
                "hypotheses_deduped_total",
                delta=deduped_count,
                tags={"research_space_id": research_space_id},
            )
        if errors:
            increment_metric(
                "hypotheses_generation_failed_total",
                delta=len(errors),
                tags={"research_space_id": research_space_id},
            )

        return HypothesisGenerationResult(
            run_id=run_id,
            requested_seed_count=requested_seed_count,
            used_seed_count=len(resolved_seed_ids),
            candidates_seen=len(raw_candidates),
            created_count=len(created),
            deduped_count=deduped_count,
            errors=tuple(errors),
            hypotheses=tuple(created),
        )

    def _resolve_seed_entity_ids(  # noqa: C901, PLR0912
        self,
        *,
        research_space_id: str,
        requested_seed_entity_ids: list[str],
        max_hypotheses: int,
    ) -> list[str]:
        max_seed_count = max(1, min(_DEFAULT_SEED_LIMIT, max_hypotheses * 2))
        if requested_seed_entity_ids:
            return requested_seed_entity_ids[:max_seed_count]

        resolved: list[str] = []
        seen: set[str] = set()

        unresolved_claims = self._claims.list_by_research_space(
            research_space_id,
            limit=300,
        )
        prioritized_claims = [
            claim
            for claim in unresolved_claims
            if claim.claim_status in {"OPEN", "NEEDS_MAPPING"}
            and float(claim.confidence) >= _SEED_CLAIM_CONFIDENCE_THRESHOLD
        ]
        prioritized_claims.sort(
            key=lambda claim: (
                -float(claim.confidence),
                -_datetime_to_epoch_seconds(claim.created_at),
            ),
        )
        for claim in prioritized_claims:
            metadata_payload = claim.metadata_payload
            source_entity_id = _normalize_optional_text(
                metadata_payload.get("source_entity_id"),
            )
            target_entity_id = _normalize_optional_text(
                metadata_payload.get("target_entity_id"),
            )
            for candidate_seed in (source_entity_id, target_entity_id):
                if candidate_seed is None or candidate_seed in seen:
                    continue
                seen.add(candidate_seed)
                resolved.append(candidate_seed)
                if len(resolved) >= max_seed_count:
                    return resolved

        relation_rows = self._relations.find_by_research_space(
            research_space_id,
            limit=600,
        )
        degree_counts: dict[str, int] = {}
        for relation in relation_rows:
            source_id = str(relation.source_id)
            target_id = str(relation.target_id)
            degree_counts[source_id] = degree_counts.get(source_id, 0) + 1
            degree_counts[target_id] = degree_counts.get(target_id, 0) + 1
        ranked_entity_ids = sorted(
            degree_counts,
            key=lambda entity_id: (-degree_counts[entity_id], entity_id),
        )
        for entity_id in ranked_entity_ids:
            if entity_id in seen:
                continue
            seen.add(entity_id)
            resolved.append(entity_id)
            if len(resolved) >= max_seed_count:
                return resolved

        fallback_entities = self._entities.find_by_research_space(
            research_space_id,
            limit=max_seed_count,
        )
        for entity in fallback_entities:
            entity_id = str(entity.id)
            if entity_id in seen:
                continue
            seen.add(entity_id)
            resolved.append(entity_id)
            if len(resolved) >= max_seed_count:
                break

        return resolved

    def _load_active_hypothesis_fingerprints(
        self,
        research_space_id: str,
    ) -> set[str]:
        claims = self._claims.list_by_research_space(
            research_space_id,
            polarity="HYPOTHESIS",
        )
        active_fingerprints: set[str] = set()
        for claim in claims:
            if claim.claim_status == "REJECTED":
                continue
            metadata_payload = claim.metadata_payload
            fingerprint = _normalize_optional_text(metadata_payload.get("fingerprint"))
            if fingerprint is None:
                continue
            active_fingerprints.add(fingerprint)
        return active_fingerprints

    def _normalize_candidates_for_seed(
        self,
        *,
        research_space_id: str,
        seed_entity_id: str,
        candidates: list[ProposedRelation],
        graph_agent_run_id: str | None,
    ) -> tuple[list[_RawCandidate], list[str]]:
        normalized_candidates: list[_RawCandidate] = []
        errors: list[str] = []

        for candidate in candidates:
            normalized_relation_type = normalize_relation_type(candidate.relation_type)
            if not normalized_relation_type:
                errors.append("candidate_missing_relation_type")
                continue

            source_entity = self._entities.get_by_id(candidate.source_id)
            target_entity = self._entities.get_by_id(candidate.target_id)
            if source_entity is None or target_entity is None:
                errors.append(
                    "candidate_endpoint_unresolved:"
                    f"{candidate.source_id}->{candidate.target_id}:{normalized_relation_type}",
                )
                continue

            source_entity_type = source_entity.entity_type.strip().upper()
            target_entity_type = target_entity.entity_type.strip().upper()
            self_loop = str(source_entity.id) == str(target_entity.id)

            relation_allowed = False
            if not self_loop:
                try:
                    relation_allowed = self._dictionary.is_relation_allowed(
                        source_entity_type,
                        normalized_relation_type,
                        target_entity_type,
                    )
                except ValueError:
                    relation_allowed = False

            novelty = self._resolve_novelty(
                research_space_id=research_space_id,
                source_entity_id=str(source_entity.id),
                relation_type=normalized_relation_type,
                target_entity_id=str(target_entity.id),
            )
            evidence_density = _resolve_evidence_density(
                supporting_provenance_ids=candidate.supporting_provenance_ids,
                supporting_document_count=candidate.supporting_document_count,
            )

            normalized_candidates.append(
                _RawCandidate(
                    seed_entity_id=seed_entity_id,
                    source_entity_id=str(source_entity.id),
                    target_entity_id=str(target_entity.id),
                    source_type=source_entity_type,
                    target_type=target_entity_type,
                    relation_type=normalized_relation_type,
                    source_label=_normalize_optional_text(source_entity.display_label),
                    target_label=_normalize_optional_text(target_entity.display_label),
                    relation_confidence=max(0.0, min(1.0, float(candidate.confidence))),
                    evidence_density=evidence_density,
                    novelty=novelty,
                    relation_allowed=relation_allowed,
                    self_loop=self_loop,
                    supporting_provenance_ids=_normalize_string_iterable(
                        candidate.supporting_provenance_ids,
                    ),
                    supporting_document_count=max(
                        0,
                        int(candidate.supporting_document_count),
                    ),
                    evidence_summary=candidate.evidence_summary,
                    reasoning=candidate.reasoning,
                    graph_agent_run_id=graph_agent_run_id,
                ),
            )

        return normalized_candidates, errors

    def _score_candidates(
        self,
        candidates: list[_RawCandidate],
    ) -> list[_ScoredCandidate]:
        relation_type_counts: dict[str, int] = {}
        for candidate in candidates:
            relation_type_counts[candidate.relation_type] = (
                relation_type_counts.get(candidate.relation_type, 0) + 1
            )

        scored: list[_ScoredCandidate] = []
        for candidate in candidates:
            relation_count = max(
                1,
                relation_type_counts.get(candidate.relation_type, 1),
            )
            relation_diversity = max(0.2, 1.0 / float(relation_count))
            score = (
                (0.50 * candidate.relation_confidence)
                + (0.20 * candidate.evidence_density)
                + (0.20 * candidate.novelty)
                + (0.10 * relation_diversity)
            )
            scored.append(
                _ScoredCandidate(
                    raw=candidate,
                    relation_diversity=max(0.0, min(1.0, relation_diversity)),
                    score=max(0.0, min(1.0, score)),
                ),
            )
        return scored

    def _load_reasoning_path_candidates(
        self,
        *,
        research_space_id: str,
        seed_entity_ids: list[str],
        max_hypotheses: int,
    ) -> tuple[list[_PathCandidate], list[str]]:
        if self._reasoning_paths is None:
            return [], []
        candidates: list[_PathCandidate] = []
        errors: list[str] = []
        seen_path_ids: set[str] = set()
        for seed_entity_id in seed_entity_ids:
            path_list = self._reasoning_paths.list_paths(
                research_space_id=research_space_id,
                start_entity_id=seed_entity_id,
                status="ACTIVE",
                path_kind="MECHANISM",
                limit=max(5, max_hypotheses * 3),
                offset=0,
            )
            for path in path_list.paths:
                path_id = str(path.id)
                if path_id in seen_path_ids:
                    continue
                seen_path_ids.add(path_id)
                path_detail = self._reasoning_paths.get_path(
                    path_id,
                    research_space_id,
                )
                if path_detail is None:
                    errors.append(f"path_missing:{path_id}")
                    continue
                start_entity = self._entities.get_by_id(str(path.start_entity_id))
                end_entity = self._entities.get_by_id(str(path.end_entity_id))
                if start_entity is None or end_entity is None:
                    errors.append(f"path_endpoint_unresolved:{path_id}")
                    continue
                metadata_payload = path.metadata_payload
                terminal_relation_type = _normalize_metadata_relation_type(
                    metadata_payload.get("terminal_relation_type"),
                )
                if not terminal_relation_type:
                    terminal_relation_type = "ASSOCIATED_WITH"
                supporting_claim_ids = _normalize_metadata_string_tuple(
                    metadata_payload.get("supporting_claim_ids"),
                )
                if not supporting_claim_ids:
                    supporting_claim_ids = tuple(
                        str(claim.id) for claim in path_detail.claims
                    )
                candidates.append(
                    _PathCandidate(
                        reasoning_path_id=path_id,
                        start_entity_id=str(path.start_entity_id),
                        end_entity_id=str(path.end_entity_id),
                        source_type=start_entity.entity_type.strip().upper(),
                        target_type=end_entity.entity_type.strip().upper(),
                        relation_type=terminal_relation_type,
                        source_label=_normalize_optional_text(
                            start_entity.display_label,
                        ),
                        target_label=_normalize_optional_text(end_entity.display_label),
                        confidence=max(0.0, min(1.0, float(path.confidence))),
                        path_length=int(path.path_length),
                        supporting_claim_ids=supporting_claim_ids,
                    ),
                )
        candidates.sort(
            key=lambda item: (
                -item.confidence,
                item.path_length,
                item.reasoning_path_id,
            ),
        )
        return candidates, errors

    def _create_claim_from_candidate(
        self,
        *,
        candidate: _ScoredCandidate,
        research_space_id: str,
        run_id: str,
        fingerprint: str,
        seed_entity_id: str,
    ) -> KernelRelationClaim:
        validation_state, validation_reason, persistability = _resolve_validation_state(
            relation_allowed=candidate.raw.relation_allowed,
            self_loop=candidate.raw.self_loop,
        )

        source_label = candidate.raw.source_label or candidate.raw.source_entity_id
        target_label = candidate.raw.target_label or candidate.raw.target_entity_id
        claim_text = (
            f"{source_label} {candidate.raw.relation_type.lower().replace('_', ' ')} "
            f"{target_label}"
        )

        metadata: JSONObject = {
            "origin": _GRAPH_ORIGIN,
            "run_id": run_id,
            "seed_entity_id": seed_entity_id,
            "candidate_score": round(candidate.score, 6),
            "relation_confidence": round(candidate.raw.relation_confidence, 6),
            "evidence_density": round(candidate.raw.evidence_density, 6),
            "novelty": round(candidate.raw.novelty, 6),
            "relation_diversity": round(candidate.relation_diversity, 6),
            "supporting_provenance_ids": list(candidate.raw.supporting_provenance_ids),
            "supporting_document_count": candidate.raw.supporting_document_count,
            "fingerprint": fingerprint,
            "source_entity_id": candidate.raw.source_entity_id,
            "target_entity_id": candidate.raw.target_entity_id,
            "evidence_summary": candidate.raw.evidence_summary,
            "reasoning": candidate.raw.reasoning,
            "graph_agent_run_id": candidate.raw.graph_agent_run_id,
        }

        claim = self._claims.create_hypothesis_claim(
            research_space_id=research_space_id,
            source_document_id=None,
            agent_run_id=run_id,
            source_type=candidate.raw.source_type,
            relation_type=candidate.raw.relation_type,
            target_type=candidate.raw.target_type,
            source_label=candidate.raw.source_label,
            target_label=candidate.raw.target_label,
            confidence=candidate.score,
            validation_state=validation_state,
            validation_reason=validation_reason,
            persistability=persistability,
            claim_text=claim_text,
            metadata=metadata,
            claim_status="OPEN",
        )
        self._participants.create_participant(
            claim_id=str(claim.id),
            research_space_id=research_space_id,
            role="SUBJECT",
            label=candidate.raw.source_label,
            entity_id=candidate.raw.source_entity_id,
            position=0,
            qualifiers=None,
        )
        self._participants.create_participant(
            claim_id=str(claim.id),
            research_space_id=research_space_id,
            role="OBJECT",
            label=candidate.raw.target_label,
            entity_id=candidate.raw.target_entity_id,
            position=1,
            qualifiers=None,
        )
        return claim

    def _create_claim_from_path_candidate(
        self,
        *,
        candidate: _PathCandidate,
        research_space_id: str,
        run_id: str,
        fingerprint: str,
    ) -> KernelRelationClaim:
        source_label = candidate.source_label or candidate.start_entity_id
        target_label = candidate.target_label or candidate.end_entity_id
        claim_text = (
            f"{source_label} {candidate.relation_type.lower().replace('_', ' ')} "
            f"{target_label}"
        )
        metadata: JSONObject = {
            "origin": _PATH_ORIGIN,
            "run_id": run_id,
            "reasoning_path_id": candidate.reasoning_path_id,
            "fingerprint": fingerprint,
            "start_entity_id": candidate.start_entity_id,
            "end_entity_id": candidate.end_entity_id,
            "supporting_claim_ids": list(candidate.supporting_claim_ids),
            "path_confidence": round(candidate.confidence, 6),
            "path_length": candidate.path_length,
        }
        claim = self._claims.create_hypothesis_claim(
            research_space_id=research_space_id,
            source_document_id=None,
            agent_run_id=run_id,
            source_type=candidate.source_type,
            relation_type=candidate.relation_type,
            target_type=candidate.target_type,
            source_label=candidate.source_label,
            target_label=candidate.target_label,
            confidence=candidate.confidence,
            validation_state="ALLOWED",
            validation_reason="derived_from_reasoning_path",
            persistability="NON_PERSISTABLE",
            claim_text=claim_text,
            metadata=metadata,
            claim_status="OPEN",
        )
        self._participants.create_participant(
            claim_id=str(claim.id),
            research_space_id=research_space_id,
            role="SUBJECT",
            label=candidate.source_label,
            entity_id=candidate.start_entity_id,
            position=0,
            qualifiers=None,
        )
        self._participants.create_participant(
            claim_id=str(claim.id),
            research_space_id=research_space_id,
            role="OBJECT",
            label=candidate.target_label,
            entity_id=candidate.end_entity_id,
            position=1,
            qualifiers=None,
        )
        return claim

    def _resolve_novelty(
        self,
        *,
        research_space_id: str,
        source_entity_id: str,
        relation_type: str,
        target_entity_id: str,
    ) -> float:
        existing_relations = self._relations.find_by_source(
            source_entity_id,
            relation_type=relation_type,
            limit=200,
        )
        for relation in existing_relations:
            if str(relation.research_space_id) != research_space_id:
                continue
            if str(relation.target_id) != target_entity_id:
                continue
            return 0.3
        return 1.0


def _normalize_seed_entity_ids(seed_entity_ids: list[str] | None) -> list[str]:
    if seed_entity_ids is None:
        return []
    normalized_ids: list[str] = []
    seen: set[str] = set()
    for value in seed_entity_ids:
        normalized = _normalize_optional_text(value)
        if normalized is None:
            continue
        try:
            canonical = str(UUID(normalized))
        except ValueError:
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        normalized_ids.append(canonical)
    return normalized_ids


def _normalize_relation_types(
    relation_types: list[str] | None,
) -> list[str] | None:
    if relation_types is None:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for value in relation_types:
        relation_type = normalize_relation_type(value)
        if not relation_type or relation_type in seen:
            continue
        seen.add(relation_type)
        normalized.append(relation_type)
    return normalized or None


def _normalize_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_metadata_relation_type(value: object) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    return normalize_relation_type(normalized)


def _normalize_metadata_string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(_normalize_string_iterable(value))


def _resolve_evidence_density(
    *,
    supporting_provenance_ids: Iterable[str],
    supporting_document_count: int,
) -> float:
    provenance_count = len(
        [value for value in supporting_provenance_ids if value.strip()],
    )
    strongest_signal = max(provenance_count, 0, supporting_document_count)
    return max(0.0, min(1.0, strongest_signal / 5.0))


def _build_fingerprint(
    *,
    source_entity_id: str,
    relation_type: str,
    target_entity_id: str,
    origin: str,
) -> str:
    return f"{source_entity_id}|{relation_type}|{target_entity_id}|{origin}"


def _resolve_validation_state(
    *,
    relation_allowed: bool,
    self_loop: bool,
) -> tuple[
    Literal["ALLOWED", "FORBIDDEN", "SELF_LOOP"],
    str,
    Literal["PERSISTABLE", "NON_PERSISTABLE"],
]:
    if self_loop:
        return (
            "SELF_LOOP",
            "source_target_self_loop",
            "NON_PERSISTABLE",
        )
    if not relation_allowed:
        return (
            "FORBIDDEN",
            "triple_not_allowed_by_dictionary",
            "NON_PERSISTABLE",
        )
    return (
        "ALLOWED",
        "allowed_by_dictionary_constraint",
        "PERSISTABLE",
    )


def _datetime_to_epoch_seconds(value: datetime) -> float:
    return value.timestamp()


def _normalize_string_iterable(values: Iterable[str]) -> tuple[str, ...]:
    normalized_values: list[str] = []
    for value in values:
        normalized = _normalize_optional_text(value)
        if normalized is None:
            continue
        normalized_values.append(normalized)
    return tuple(normalized_values)


__all__ = [
    "HypothesisGenerationResult",
    "HypothesisGenerationService",
    "HypothesisGenerationServiceDependencies",
]
