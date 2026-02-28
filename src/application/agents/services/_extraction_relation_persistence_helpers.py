"""Relation persistence helpers for extraction orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.application.agents.services._extraction_relation_canonicalization_helpers import (
    _ExtractionRelationCanonicalizationHelpers,
)
from src.application.agents.services._extraction_relation_full_auto_helpers import (
    _ExtractionRelationFullAutoHelpers,
)
from src.application.agents.services._extraction_relation_policy_helpers import (
    _ExtractionRelationPolicyHelpers,
    _ResolvedRelationCandidate,
)
from src.application.agents.services._relation_endpoint_entity_resolution_helpers import (
    _RelationEndpointEntityResolutionHelpers,
)
from src.application.agents.services._relation_persistence_payload_helpers import (
    candidate_payload,
    normalize_optional_text,
    normalize_run_id,
    relation_payload,
)
from src.application.services.claim_first_metrics import (
    emit_claim_first_extraction_metrics,
)
from src.domain.value_objects.relation_types import normalize_relation_type

if TYPE_CHECKING:
    from src.application.agents.services._extraction_relation_policy_helpers import (
        RelationGovernanceMode,
    )
    from src.domain.agents.contracts.extraction import (
        ExtractedRelation,
        ExtractionContract,
    )
    from src.domain.agents.contracts.extraction_policy import ExtractionPolicyContract
    from src.domain.entities.source_document import SourceDocument
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
    from src.domain.repositories.kernel.relation_claim_repository import (
        KernelRelationClaimRepository,
    )
    from src.domain.repositories.kernel.relation_repository import (
        KernelRelationRepository,
    )
    from src.type_definitions.common import JSONObject, ResearchSpaceSettings

_LOW_CONFIDENCE_REVIEW_THRESHOLD = 0.6
_PER_CANDIDATE_LOG_THRESHOLD = 25
_PER_CANDIDATE_LOG_INTERVAL = 10
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RelationPersistenceResult:
    """Persistence + review outcome for extracted relation candidates."""

    persisted_relations_count: int = 0
    pending_review_relations_count: int = 0
    relation_claims_count: int = 0
    non_persistable_claims_count: int = 0
    forbidden_relations_count: int = 0
    undefined_relations_count: int = 0
    policy_proposals_count: int = 0
    policy_run_id: str | None = None
    rejected_relation_reasons: tuple[str, ...] = ()
    rejected_relation_details: tuple[JSONObject, ...] = ()
    funnel: JSONObject = field(default_factory=dict)
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _CandidateBuildResult:
    candidates: tuple[_ResolvedRelationCandidate, ...] = ()
    rejected_relation_reasons: tuple[str, ...] = ()
    rejected_relation_details: tuple[JSONObject, ...] = ()
    invalid_components_count: int = 0
    endpoint_resolution_failed_count: int = 0
    self_loop_count: int = 0
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _PersistCandidatesResult:
    persisted_relations_count: int = 0
    pending_review_relations_count: int = 0
    relation_claims_count: int = 0
    relation_claims_queued_for_review_count: int = 0
    non_persistable_claims_count: int = 0
    forbidden_relations_count: int = 0
    undefined_relations_count: int = 0
    rejected_relation_reasons: tuple[str, ...] = ()
    rejected_relation_details: tuple[JSONObject, ...] = ()
    persistence_failed_count: int = 0
    errors: tuple[str, ...] = ()


class _ExtractionRelationPersistenceHelpers(
    _ExtractionRelationCanonicalizationHelpers,
    _ExtractionRelationFullAutoHelpers,
    _RelationEndpointEntityResolutionHelpers,
    _ExtractionRelationPolicyHelpers,
):
    """Shared relation-persistence helpers for extraction service."""

    _relations: KernelRelationRepository | None
    _relation_claims: KernelRelationClaimRepository | None
    _entities: KernelEntityRepository | None

    async def _persist_extracted_relations(
        self,
        *,
        document: SourceDocument,
        contract: ExtractionContract,
        research_space_settings: ResearchSpaceSettings,
        publication_entity_ids: tuple[str, ...],
        model_id: str | None,
    ) -> RelationPersistenceResult:
        started_at = datetime.now(UTC)
        run_id = normalize_run_id(contract.agent_run_id)
        if document.research_space_id is None:
            return RelationPersistenceResult(
                errors=("relation_persistence_missing_research_space_id",),
            )
        research_space_id = str(document.research_space_id)
        relation_governance_mode = self._resolve_relation_governance_mode(
            research_space_settings,
        )
        if not contract.relations:
            return RelationPersistenceResult()
        if self._relations is None or self._entities is None:
            return RelationPersistenceResult(
                errors=("relation_persistence_unavailable",),
            )

        logger.info(
            "Extraction relation persistence helper started",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "research_space_id": research_space_id,
                "relation_candidates_input_count": len(contract.relations),
                "publication_entity_ids_count": len(publication_entity_ids),
                "relation_governance_mode": relation_governance_mode,
            },
        )

        publication_entity_id = (
            publication_entity_ids[0] if publication_entity_ids else None
        )
        candidate_build_started_at = datetime.now(UTC)
        candidate_build = self._build_relation_candidates(
            research_space_id=research_space_id,
            relations=contract.relations,
            publication_entity_id=publication_entity_id,
        )
        logger.info(
            "Extraction relation candidates built",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "duration_ms": int(
                    (datetime.now(UTC) - candidate_build_started_at).total_seconds()
                    * 1000,
                ),
                "candidates_count": len(candidate_build.candidates),
                "invalid_components_count": candidate_build.invalid_components_count,
                "endpoint_resolution_failed_count": (
                    candidate_build.endpoint_resolution_failed_count
                ),
                "self_loop_count": candidate_build.self_loop_count,
                "error_count": len(candidate_build.errors),
            },
        )
        unknown_patterns = self._build_unknown_relation_patterns(
            candidate_build.candidates,
        )
        policy_step_started_at = datetime.now(UTC)
        policy_step = await self._run_policy_step(
            research_space_id=research_space_id,
            document=document,
            source_type=contract.source_type,
            unknown_patterns=unknown_patterns,
            model_id=model_id,
        )
        logger.info(
            "Extraction relation policy step finished",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "duration_ms": int(
                    (datetime.now(UTC) - policy_step_started_at).total_seconds() * 1000,
                ),
                "unknown_patterns_count": len(unknown_patterns),
                "policy_contract_present": policy_step.contract is not None,
                "error_count": len(policy_step.errors),
            },
        )
        proposal_store_started_at = datetime.now(UTC)
        proposal_count, proposal_errors = self._store_policy_constraint_proposals(
            research_space_id=research_space_id,
            document=document,
            policy_contract=policy_step.contract,
            policy_run_id=normalize_run_id(
                (
                    policy_step.contract.agent_run_id
                    if policy_step.contract is not None
                    else None
                ),
            ),
            relation_governance_mode=relation_governance_mode,
        )
        logger.info(
            "Extraction relation policy proposals stored",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "duration_ms": int(
                    (datetime.now(UTC) - proposal_store_started_at).total_seconds()
                    * 1000,
                ),
                "proposal_count": proposal_count,
                "error_count": len(proposal_errors),
            },
        )
        persist_candidates_started_at = datetime.now(UTC)
        persist_result = self._persist_relation_candidates(
            document=document,
            run_id=run_id,
            candidates=candidate_build.candidates,
            policy_contract=policy_step.contract,
            relation_governance_mode=relation_governance_mode,
        )
        logger.info(
            "Extraction relation candidates persisted",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "duration_ms": int(
                    (datetime.now(UTC) - persist_candidates_started_at).total_seconds()
                    * 1000,
                ),
                "persisted_relations_count": persist_result.persisted_relations_count,
                "pending_review_relations_count": (
                    persist_result.pending_review_relations_count
                ),
                "relation_claims_count": persist_result.relation_claims_count,
                "non_persistable_claims_count": (
                    persist_result.non_persistable_claims_count
                ),
                "forbidden_relations_count": persist_result.forbidden_relations_count,
                "undefined_relations_count": persist_result.undefined_relations_count,
                "persistence_failed_count": persist_result.persistence_failed_count,
                "error_count": len(persist_result.errors),
            },
        )
        emit_claim_first_extraction_metrics(
            research_space_id=research_space_id,
            source_document_id=str(document.id),
            claims_created=persist_result.relation_claims_count,
            claims_non_persistable=persist_result.non_persistable_claims_count,
            relations_draft_created=persist_result.persisted_relations_count,
            relation_claims_queued_for_review=(
                persist_result.relation_claims_queued_for_review_count
            ),
            research_space_settings=research_space_settings,
        )
        logger.info(
            "Extraction relation persistence helper finished",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "duration_ms": int(
                    (datetime.now(UTC) - started_at).total_seconds() * 1000,
                ),
                "relation_candidates_input_count": len(contract.relations),
                "relation_claims_count": persist_result.relation_claims_count,
                "persisted_relations_count": persist_result.persisted_relations_count,
                "non_persistable_claims_count": (
                    persist_result.non_persistable_claims_count
                ),
                "total_error_count": len(
                    candidate_build.errors
                    + policy_step.errors
                    + proposal_errors
                    + persist_result.errors,
                ),
            },
        )
        return RelationPersistenceResult(
            persisted_relations_count=persist_result.persisted_relations_count,
            pending_review_relations_count=persist_result.pending_review_relations_count,
            relation_claims_count=persist_result.relation_claims_count,
            non_persistable_claims_count=persist_result.non_persistable_claims_count,
            forbidden_relations_count=persist_result.forbidden_relations_count,
            undefined_relations_count=persist_result.undefined_relations_count,
            policy_proposals_count=proposal_count,
            policy_run_id=normalize_run_id(
                (
                    policy_step.contract.agent_run_id
                    if policy_step.contract is not None
                    else None
                ),
            ),
            rejected_relation_reasons=self._merge_unique_reasons(
                candidate_build.rejected_relation_reasons,
                persist_result.rejected_relation_reasons,
            ),
            rejected_relation_details=(
                candidate_build.rejected_relation_details
                + persist_result.rejected_relation_details
            ),
            funnel={
                "relation_candidates_generated": len(contract.relations),
                "relation_candidates_after_prevalidation": len(
                    candidate_build.candidates,
                ),
                "relation_candidates_prevalidation_rejected": (
                    candidate_build.invalid_components_count
                    + candidate_build.endpoint_resolution_failed_count
                    + candidate_build.self_loop_count
                ),
                "relation_candidates_invalid_components": (
                    candidate_build.invalid_components_count
                ),
                "relation_candidates_endpoint_resolution_failed": (
                    candidate_build.endpoint_resolution_failed_count
                ),
                "relation_candidates_self_loop": candidate_build.self_loop_count,
                "relation_candidates_forbidden": (
                    persist_result.forbidden_relations_count
                ),
                "relation_candidates_undefined": (
                    persist_result.undefined_relations_count
                ),
                "relation_claims_created": persist_result.relation_claims_count,
                "relation_claims_queued_for_review": (
                    persist_result.relation_claims_queued_for_review_count
                ),
                "relation_claims_non_persistable": (
                    persist_result.non_persistable_claims_count
                ),
                "relation_candidates_persisted": (
                    persist_result.persisted_relations_count
                ),
                "relation_candidates_pending_review": (
                    persist_result.pending_review_relations_count
                ),
                "relation_candidates_persistence_failed": (
                    persist_result.persistence_failed_count
                ),
                "relation_policy_unknown_patterns": len(unknown_patterns),
                "relation_policy_proposals_created": proposal_count,
            },
            errors=(
                candidate_build.errors
                + policy_step.errors
                + proposal_errors
                + persist_result.errors
            ),
        )

    def _build_relation_candidates(
        self,
        *,
        research_space_id: str,
        relations: list[ExtractedRelation],
        publication_entity_id: str | None,
    ) -> _CandidateBuildResult:
        candidates: list[_ResolvedRelationCandidate] = []
        rejected_reasons: list[str] = []
        rejected_details: list[JSONObject] = []
        errors: list[str] = []
        invalid_components_count = 0
        endpoint_resolution_failed_count = 0
        self_loop_count = 0

        for relation in relations:
            normalized_source_type = self._normalize_component(relation.source_type)
            normalized_relation_type = normalize_relation_type(relation.relation_type)
            normalized_target_type = self._normalize_component(relation.target_type)
            payload = relation_payload(relation)

            if (
                not normalized_source_type
                or not normalized_relation_type
                or not normalized_target_type
            ):
                self._record_rejected_relation(
                    reasons=rejected_reasons,
                    details=rejected_details,
                    reason="invalid_relation_components",
                    payload=payload,
                    metadata={
                        "validation_state": "INVALID_COMPONENTS",
                        "validation_reason": (
                            "source_type, relation_type, and target_type are required"
                        ),
                    },
                )
                errors.append("relation_persistence_skipped_invalid_components")
                candidates.append(
                    _ResolvedRelationCandidate(
                        source_entity_id=None,
                        target_entity_id=None,
                        source_type=normalized_source_type or "UNKNOWN",
                        relation_type=normalized_relation_type or "UNKNOWN",
                        target_type=normalized_target_type or "UNKNOWN",
                        source_label=normalize_optional_text(relation.source_label),
                        target_label=normalize_optional_text(relation.target_label),
                        confidence=float(relation.confidence),
                        validation_state="INVALID_COMPONENTS",
                        validation_reason=(
                            "source_type, relation_type, and target_type are required"
                        ),
                        persistability="NON_PERSISTABLE",
                    ),
                )
                invalid_components_count += 1
                continue

            source_entity_id = self._resolve_relation_endpoint_entity_id(
                research_space_id=research_space_id,
                entity_type=normalized_source_type,
                label=relation.source_label,
                publication_entity_id=publication_entity_id,
                endpoint_name="source",
            )
            target_entity_id = self._resolve_relation_endpoint_entity_id(
                research_space_id=research_space_id,
                entity_type=normalized_target_type,
                label=relation.target_label,
                publication_entity_id=publication_entity_id,
                endpoint_name="target",
            )
            if source_entity_id is None or target_entity_id is None:
                self._record_rejected_relation(
                    reasons=rejected_reasons,
                    details=rejected_details,
                    reason="relation_endpoint_resolution_failed",
                    payload=payload,
                    metadata={
                        "validation_state": "ENDPOINT_UNRESOLVED",
                        "validation_reason": (
                            "source or target endpoint could not be resolved"
                        ),
                    },
                )
                errors.append(
                    (
                        "relation_persistence_skipped:"
                        f"{normalized_source_type}:{normalized_relation_type}:"
                        f"{normalized_target_type}"
                    ),
                )
                candidates.append(
                    _ResolvedRelationCandidate(
                        source_entity_id=source_entity_id,
                        target_entity_id=target_entity_id,
                        source_type=normalized_source_type,
                        relation_type=normalized_relation_type,
                        target_type=normalized_target_type,
                        source_label=normalize_optional_text(relation.source_label),
                        target_label=normalize_optional_text(relation.target_label),
                        confidence=float(relation.confidence),
                        validation_state="ENDPOINT_UNRESOLVED",
                        validation_reason=(
                            "source or target endpoint could not be resolved"
                        ),
                        persistability="NON_PERSISTABLE",
                    ),
                )
                endpoint_resolution_failed_count += 1
                continue
            if source_entity_id == target_entity_id:
                self._record_rejected_relation(
                    reasons=rejected_reasons,
                    details=rejected_details,
                    reason="relation_self_loop",
                    payload=payload,
                    metadata={
                        "validation_state": "SELF_LOOP",
                        "validation_reason": "self-loop relations are not allowed",
                    },
                )
                candidates.append(
                    _ResolvedRelationCandidate(
                        source_entity_id=source_entity_id,
                        target_entity_id=target_entity_id,
                        source_type=normalized_source_type,
                        relation_type=normalized_relation_type,
                        target_type=normalized_target_type,
                        source_label=normalize_optional_text(relation.source_label),
                        target_label=normalize_optional_text(relation.target_label),
                        confidence=float(relation.confidence),
                        validation_state="SELF_LOOP",
                        validation_reason="self-loop relations are not allowed",
                        persistability="NON_PERSISTABLE",
                    ),
                )
                self_loop_count += 1
                continue

            validation_state, validation_reason = (
                self._resolve_relation_validation_state(
                    source_type=normalized_source_type,
                    relation_type=normalized_relation_type,
                    target_type=normalized_target_type,
                )
            )
            candidates.append(
                _ResolvedRelationCandidate(
                    source_entity_id=source_entity_id,
                    target_entity_id=target_entity_id,
                    source_type=normalized_source_type,
                    relation_type=normalized_relation_type,
                    target_type=normalized_target_type,
                    source_label=normalize_optional_text(relation.source_label),
                    target_label=normalize_optional_text(relation.target_label),
                    confidence=float(relation.confidence),
                    validation_state=validation_state,
                    validation_reason=validation_reason,
                    persistability="PERSISTABLE",
                ),
            )

        return _CandidateBuildResult(
            candidates=tuple(candidates),
            rejected_relation_reasons=tuple(rejected_reasons),
            rejected_relation_details=tuple(rejected_details),
            invalid_components_count=invalid_components_count,
            endpoint_resolution_failed_count=endpoint_resolution_failed_count,
            self_loop_count=self_loop_count,
            errors=tuple(errors),
        )

    def _persist_relation_candidates(  # noqa: C901, PLR0912, PLR0915
        self,
        *,
        document: SourceDocument,
        run_id: str | None,
        candidates: tuple[_ResolvedRelationCandidate, ...],
        policy_contract: ExtractionPolicyContract | None,
        relation_governance_mode: RelationGovernanceMode,
    ) -> _PersistCandidatesResult:
        if self._relations is None:
            return _PersistCandidatesResult(
                errors=("relation_persistence_unavailable",),
            )
        started_at = datetime.now(UTC)

        persisted_count = 0
        pending_count = 0
        relation_claims_count = 0
        relation_claims_queued_for_review_count = 0
        non_persistable_claims_count = 0
        forbidden_count = 0
        undefined_count = 0
        rejected_reasons: list[str] = []
        rejected_details: list[JSONObject] = []
        errors: list[str] = []
        persistence_failed_count = 0

        constraint_lookup = self._index_constraint_proposals(policy_contract)
        mapping_lookup = self._index_mapping_proposals(policy_contract)
        research_space_id = (
            str(document.research_space_id)
            if document.research_space_id is not None
            else ""
        )
        total_candidates = len(candidates)
        logger.info(
            "Persist relation candidates started",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "research_space_id": research_space_id,
                "candidate_count": total_candidates,
                "relation_governance_mode": relation_governance_mode,
            },
        )

        for index, candidate in enumerate(candidates, start=1):
            should_log_candidate = (
                total_candidates <= _PER_CANDIDATE_LOG_THRESHOLD
                or index in {1, total_candidates}
                or index % _PER_CANDIDATE_LOG_INTERVAL == 0
            )
            if should_log_candidate:
                logger.info(
                    "Persist relation candidate started",
                    extra={
                        "document_id": str(document.id),
                        "run_id": run_id,
                        "candidate_index": index,
                        "candidate_total": total_candidates,
                        "source_type": candidate.source_type,
                        "relation_type": candidate.relation_type,
                        "target_type": candidate.target_type,
                        "validation_state": candidate.validation_state,
                        "persistability": candidate.persistability,
                        "confidence": candidate.confidence,
                    },
                )
            proposal_key = (
                candidate.source_type,
                candidate.relation_type,
                candidate.target_type,
            )
            mapping_proposal = mapping_lookup.get(proposal_key)
            effective_candidate = candidate
            canonicalization_metadata: JSONObject | None = None

            if effective_candidate.persistability == "PERSISTABLE":
                canonicalization_started_at = datetime.now(UTC)
                if should_log_candidate:
                    logger.info(
                        "Persist relation candidate canonicalization started",
                        extra={
                            "document_id": str(document.id),
                            "run_id": run_id,
                            "candidate_index": index,
                            "candidate_total": total_candidates,
                            "source_type": effective_candidate.source_type,
                            "relation_type": effective_candidate.relation_type,
                            "target_type": effective_candidate.target_type,
                        },
                    )
                (
                    effective_candidate,
                    canonicalization_metadata,
                ) = self._canonicalize_relation_candidate(
                    candidate=effective_candidate,
                    mapping_proposal=mapping_proposal,
                    document=document,
                )
                validation_state, validation_reason = (
                    self._resolve_relation_validation_state(
                        source_type=effective_candidate.source_type,
                        relation_type=effective_candidate.relation_type,
                        target_type=effective_candidate.target_type,
                    )
                )
                effective_candidate = replace(
                    effective_candidate,
                    validation_state=validation_state,
                    validation_reason=validation_reason,
                )
                if should_log_candidate:
                    logger.info(
                        "Persist relation candidate canonicalization finished",
                        extra={
                            "document_id": str(document.id),
                            "run_id": run_id,
                            "candidate_index": index,
                            "candidate_total": total_candidates,
                            "duration_ms": int(
                                (
                                    datetime.now(UTC) - canonicalization_started_at
                                ).total_seconds()
                                * 1000,
                            ),
                            "validation_state": effective_candidate.validation_state,
                            "persistability": effective_candidate.persistability,
                            "relation_type": effective_candidate.relation_type,
                        },
                    )

            if (
                effective_candidate.validation_state == "UNDEFINED"
                and relation_governance_mode == "FULL_AUTO"
            ):
                effective_candidate = self._resolve_full_auto_candidate(
                    candidate=effective_candidate,
                    mapping_proposal=mapping_proposal,
                    source_ref=f"source_document:{document.id}:full_auto_persist",
                )

            payload = candidate_payload(effective_candidate)
            if canonicalization_metadata:
                payload["canonicalization"] = canonicalization_metadata
            claim_id: str | None = None
            if self._relation_claims is not None:
                try:
                    created_claim = self._relation_claims.create(
                        research_space_id=research_space_id,
                        source_document_id=str(document.id),
                        agent_run_id=run_id,
                        source_type=document.source_type.value,
                        relation_type=effective_candidate.relation_type,
                        target_type=effective_candidate.target_type,
                        source_label=effective_candidate.source_label,
                        target_label=effective_candidate.target_label,
                        confidence=effective_candidate.confidence,
                        validation_state=effective_candidate.validation_state,
                        validation_reason=effective_candidate.validation_reason,
                        persistability=effective_candidate.persistability,
                        claim_status="OPEN",
                        linked_relation_id=None,
                        metadata=payload,
                    )
                    claim_id = str(created_claim.id)
                    relation_claims_count += 1
                except (TypeError, ValueError) as exc:
                    errors.append(
                        (
                            "relation_claim_create_failed:"
                            f"{effective_candidate.relation_type}:{exc!s}"
                        ),
                    )
                    if should_log_candidate:
                        logger.warning(
                            "Persist relation candidate claim creation failed",
                            extra={
                                "document_id": str(document.id),
                                "run_id": run_id,
                                "candidate_index": index,
                                "candidate_total": total_candidates,
                                "relation_type": effective_candidate.relation_type,
                            },
                        )

            if effective_candidate.validation_state == "FORBIDDEN":
                forbidden_count += 1
            if effective_candidate.validation_state == "UNDEFINED":
                undefined_count += 1

            if effective_candidate.persistability != "PERSISTABLE":
                non_persistable_claims_count += 1
                if claim_id is not None:
                    self._enqueue_review_item(
                        entity_type="relation_claim",
                        entity_id=claim_id,
                        research_space_id=research_space_id,
                        priority=self._review_priority_for_candidate(
                            candidate=effective_candidate,
                        ),
                    )
                    relation_claims_queued_for_review_count += 1
                if should_log_candidate:
                    logger.info(
                        "Persist relation candidate completed as non-persistable",
                        extra={
                            "document_id": str(document.id),
                            "run_id": run_id,
                            "candidate_index": index,
                            "candidate_total": total_candidates,
                            "validation_state": effective_candidate.validation_state,
                            "claim_id": claim_id,
                        },
                    )
                continue

            if (
                effective_candidate.source_entity_id is None
                or effective_candidate.target_entity_id is None
            ):
                non_persistable_claims_count += 1
                if claim_id is not None:
                    self._enqueue_review_item(
                        entity_type="relation_claim",
                        entity_id=claim_id,
                        research_space_id=research_space_id,
                        priority="high",
                    )
                    relation_claims_queued_for_review_count += 1
                errors.append("relation_persistence_missing_endpoint_entity_id")
                if should_log_candidate:
                    logger.warning(
                        "Persist relation candidate missing endpoint entity id",
                        extra={
                            "document_id": str(document.id),
                            "run_id": run_id,
                            "candidate_index": index,
                            "candidate_total": total_candidates,
                            "validation_state": effective_candidate.validation_state,
                            "claim_id": claim_id,
                        },
                    )
                continue

            try:
                created_relation = self._relations.create(
                    research_space_id=research_space_id,
                    source_id=effective_candidate.source_entity_id,
                    relation_type=effective_candidate.relation_type,
                    target_id=effective_candidate.target_entity_id,
                    confidence=effective_candidate.confidence,
                    evidence_summary=self._build_relation_evidence_summary(
                        document=document,
                        candidate=effective_candidate,
                        relation_governance_mode=relation_governance_mode,
                        constraint_proposal=constraint_lookup.get(
                            (
                                effective_candidate.source_type,
                                effective_candidate.relation_type,
                                effective_candidate.target_type,
                            ),
                        ),
                        mapping_proposal=mapping_proposal,
                    ),
                    evidence_tier="COMPUTATIONAL",
                    curation_status="DRAFT",
                    source_document_id=str(document.id),
                    agent_run_id=run_id,
                )
                persisted_count += 1
                pending_count += 1
                if claim_id is not None and self._relation_claims is not None:
                    with_context_errors = self._link_claim_to_relation(
                        claim_id=claim_id,
                        relation_id=str(created_relation.id),
                    )
                    errors.extend(with_context_errors)
            except (TypeError, ValueError) as exc:
                errors.append(
                    (
                        "relation_persistence_failed:"
                        f"{effective_candidate.relation_type}:"
                        f"{effective_candidate.source_entity_id}"
                        f"->{effective_candidate.target_entity_id}:{exc!s}"
                    ),
                )
                persistence_failed_count += 1
                if should_log_candidate:
                    logger.warning(
                        "Persist relation candidate relation write failed",
                        extra={
                            "document_id": str(document.id),
                            "run_id": run_id,
                            "candidate_index": index,
                            "candidate_total": total_candidates,
                            "relation_type": effective_candidate.relation_type,
                            "source_entity_id": effective_candidate.source_entity_id,
                            "target_entity_id": effective_candidate.target_entity_id,
                        },
                    )
                continue

            self._enqueue_review_item(
                entity_type="relation",
                entity_id=str(created_relation.id),
                research_space_id=research_space_id,
                priority=self._review_priority_for_candidate(
                    candidate=effective_candidate,
                ),
            )
            if should_log_candidate:
                logger.info(
                    "Persist relation candidate completed as persisted relation",
                    extra={
                        "document_id": str(document.id),
                        "run_id": run_id,
                        "candidate_index": index,
                        "candidate_total": total_candidates,
                        "relation_id": str(created_relation.id),
                        "claim_id": claim_id,
                        "validation_state": effective_candidate.validation_state,
                        "relation_type": effective_candidate.relation_type,
                    },
                )

        logger.info(
            "Persist relation candidates finished",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "duration_ms": int(
                    (datetime.now(UTC) - started_at).total_seconds() * 1000,
                ),
                "candidate_count": total_candidates,
                "persisted_relations_count": persisted_count,
                "pending_review_relations_count": pending_count,
                "relation_claims_count": relation_claims_count,
                "relation_claims_queued_for_review_count": (
                    relation_claims_queued_for_review_count
                ),
                "non_persistable_claims_count": non_persistable_claims_count,
                "forbidden_relations_count": forbidden_count,
                "undefined_relations_count": undefined_count,
                "persistence_failed_count": persistence_failed_count,
                "error_count": len(errors),
            },
        )
        return _PersistCandidatesResult(
            persisted_relations_count=persisted_count,
            pending_review_relations_count=pending_count,
            relation_claims_count=relation_claims_count,
            relation_claims_queued_for_review_count=(
                relation_claims_queued_for_review_count
            ),
            non_persistable_claims_count=non_persistable_claims_count,
            forbidden_relations_count=forbidden_count,
            undefined_relations_count=undefined_count,
            rejected_relation_reasons=tuple(rejected_reasons),
            rejected_relation_details=tuple(rejected_details),
            persistence_failed_count=persistence_failed_count,
            errors=tuple(errors),
        )

    def _link_claim_to_relation(
        self,
        *,
        claim_id: str,
        relation_id: str,
    ) -> list[str]:
        if self._relation_claims is None:
            return []
        try:
            self._relation_claims.link_relation(
                claim_id,
                linked_relation_id=relation_id,
            )
        except (TypeError, ValueError) as exc:
            return [f"relation_claim_link_failed:{claim_id}:{relation_id}:{exc!s}"]
        return []

    @staticmethod
    def _review_priority_for_candidate(
        *,
        candidate: _ResolvedRelationCandidate,
    ) -> str:
        if candidate.validation_state in {"FORBIDDEN", "SELF_LOOP"}:
            return "high"
        if candidate.validation_state == "UNDEFINED":
            return "medium"
        if candidate.confidence < _LOW_CONFIDENCE_REVIEW_THRESHOLD:
            return "medium"
        return "low"


__all__ = ["RelationPersistenceResult", "_ExtractionRelationPersistenceHelpers"]
