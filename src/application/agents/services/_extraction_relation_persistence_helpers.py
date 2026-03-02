from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from src.application.agents.services._extraction_relation_auto_resolve_helpers import (
    _FULL_AUTO_CONFIDENCE_THRESHOLD,
    _ExtractionRelationAutoResolveHelpers,
)
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
    from collections.abc import Callable

    from src.application.agents.services._extraction_relation_policy_helpers import (
        RelationGovernanceMode,
    )
    from src.domain.agents.contracts.extraction import (
        ExtractedRelation,
        ExtractionContract,
    )
    from src.domain.agents.contracts.extraction_policy import (
        ExtractionPolicyContract,
        RelationConstraintProposal,
        RelationTypeMappingProposal,
    )
    from src.domain.entities.source_document import SourceDocument
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
    from src.domain.repositories.kernel.relation_claim_repository import (
        KernelRelationClaimRepository,
    )
    from src.domain.repositories.kernel.relation_repository import (
        KernelRelationRepository,
    )
    from src.type_definitions.common import JSONObject, ResearchSpaceSettings

_PER_CANDIDATE_LOG_THRESHOLD = 25
_PER_CANDIDATE_LOG_INTERVAL = 10
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RelationPersistenceResult:
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
    full_auto_retry_skipped_count: int = 0
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _RelationWriteOutcome:
    persisted_relations_count: int = 0
    pending_review_relations_count: int = 0
    relation_claims_count_delta: int = 0
    relation_claims_queued_for_review_count: int = 0
    persistence_failed_count: int = 0
    errors: tuple[str, ...] = ()


class _ExtractionRelationPersistenceHelpers(
    _ExtractionRelationAutoResolveHelpers,
    _ExtractionRelationCanonicalizationHelpers,
    _ExtractionRelationFullAutoHelpers,
    _RelationEndpointEntityResolutionHelpers,
    _ExtractionRelationPolicyHelpers,
):
    _relations: KernelRelationRepository | None
    _relation_claims: KernelRelationClaimRepository | None
    _entities: KernelEntityRepository | None
    _rollback_on_error: Callable[[], None] | None

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
                "full_auto_retry_skipped_count": (
                    persist_result.full_auto_retry_skipped_count
                ),
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
                "full_auto_retry_skipped_count": (
                    persist_result.full_auto_retry_skipped_count
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
                "relation_candidates_full_auto_retry_skipped": (
                    persist_result.full_auto_retry_skipped_count
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

    def _persist_candidate_relation(  # noqa: C901, PLR0912, PLR0913
        self,
        *,
        document: SourceDocument,
        run_id: str | None,
        research_space_id: str,
        relation_governance_mode: RelationGovernanceMode,
        effective_candidate: _ResolvedRelationCandidate,
        mapping_proposal: RelationTypeMappingProposal | None,
        constraint_lookup: dict[tuple[str, str, str], RelationConstraintProposal],
        claim_id: str | None,
        payload: JSONObject,
        candidate_signature: tuple[str, str, str, str, str],
        full_auto_retry_index: dict[tuple[str, str, str, str, str], str],
        dictionary_fingerprint: str,
        index: int,
        total_candidates: int,
        should_log_candidate: bool,
    ) -> _RelationWriteOutcome:
        errors: list[str] = []
        relation_claims_count_delta = 0
        relation_claims_queued_for_review_count = 0
        if self._relations is None:
            return _RelationWriteOutcome(
                persistence_failed_count=1,
                errors=("relation_persistence_unavailable",),
            )
        source_entity_id = effective_candidate.source_entity_id
        target_entity_id = effective_candidate.target_entity_id
        if source_entity_id is None or target_entity_id is None:
            return _RelationWriteOutcome(
                persistence_failed_count=1,
                errors=("relation_persistence_missing_endpoint_entity_id",),
            )
        try:
            created_relation = self._relations.create(
                research_space_id=research_space_id,
                source_id=source_entity_id,
                relation_type=effective_candidate.relation_type,
                target_id=target_entity_id,
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
            if claim_id is not None and self._relation_claims is not None:
                with_context_errors = self._link_claim_to_relation(
                    claim_id=claim_id,
                    relation_id=str(created_relation.id),
                )
                errors.extend(with_context_errors)
                if relation_governance_mode == "FULL_AUTO":
                    status_errors = self._set_claim_system_status(
                        claim_id=claim_id,
                        claim_status="RESOLVED",
                    )
                    errors.extend(status_errors)
                    if candidate_signature in full_auto_retry_index:
                        full_auto_retry_index.pop(candidate_signature)
        except (TypeError, ValueError, SQLAlchemyError) as exc:
            self._rollback_after_persistence_error(
                context="relation_create",
            )
            error_code = self._map_relation_write_error_code(exc)
            errors.append(
                (
                    "relation_persistence_failed:"
                    f"{error_code}:{effective_candidate.relation_type}:"
                    f"{source_entity_id}"
                    f"->{target_entity_id}"
                ),
            )
            if claim_id is not None and self._relation_claims is not None:
                relation_claims_count_delta -= 1
                try:
                    recreated_claim = self._relation_claims.create(
                        research_space_id=research_space_id,
                        source_document_id=str(document.id),
                        agent_run_id=run_id,
                        source_type=effective_candidate.source_type,
                        relation_type=effective_candidate.relation_type,
                        target_type=effective_candidate.target_type,
                        source_label=effective_candidate.source_label,
                        target_label=effective_candidate.target_label,
                        confidence=effective_candidate.confidence,
                        validation_state=effective_candidate.validation_state,
                        validation_reason=effective_candidate.validation_reason,
                        persistability=effective_candidate.persistability,
                        claim_status=(
                            "NEEDS_MAPPING"
                            if relation_governance_mode == "FULL_AUTO"
                            else "OPEN"
                        ),
                        linked_relation_id=None,
                        metadata=payload,
                    )
                    claim_id = str(recreated_claim.id)
                    relation_claims_count_delta += 1
                    if relation_governance_mode == "FULL_AUTO":
                        full_auto_retry_index[candidate_signature] = (
                            dictionary_fingerprint
                        )
                    self._enqueue_review_item(
                        entity_type="relation_claim",
                        entity_id=claim_id,
                        research_space_id=research_space_id,
                        priority="high",
                    )
                    relation_claims_queued_for_review_count += 1
                    if should_log_candidate:
                        logger.info(
                            "Persist relation candidate claim restored after relation rollback",
                            extra={
                                "document_id": str(document.id),
                                "run_id": run_id,
                                "candidate_index": index,
                                "candidate_total": total_candidates,
                                "claim_id": claim_id,
                                "relation_type": effective_candidate.relation_type,
                                "error_code": error_code,
                            },
                        )
                except (TypeError, ValueError, SQLAlchemyError) as claim_exc:
                    self._rollback_after_persistence_error(
                        context="relation_claim_recreate",
                    )
                    claim_error_code = self._map_relation_write_error_code(
                        claim_exc,
                    )
                    errors.append(
                        (
                            "relation_claim_recreate_failed:"
                            f"{claim_error_code}:{effective_candidate.relation_type}"
                        ),
                    )
                    if should_log_candidate:
                        logger.warning(
                            "Persist relation candidate claim recreate failed after rollback",
                            extra={
                                "document_id": str(document.id),
                                "run_id": run_id,
                                "candidate_index": index,
                                "candidate_total": total_candidates,
                                "relation_type": effective_candidate.relation_type,
                                "error_code": claim_error_code,
                                "error": str(claim_exc),
                            },
                        )
            if should_log_candidate:
                logger.warning(
                    "Persist relation candidate relation write failed",
                    extra={
                        "document_id": str(document.id),
                        "run_id": run_id,
                        "candidate_index": index,
                        "candidate_total": total_candidates,
                        "relation_type": effective_candidate.relation_type,
                        "source_entity_id": source_entity_id,
                        "target_entity_id": target_entity_id,
                        "error_code": error_code,
                        "error": str(exc),
                    },
                )
            return _RelationWriteOutcome(
                relation_claims_count_delta=relation_claims_count_delta,
                relation_claims_queued_for_review_count=(
                    relation_claims_queued_for_review_count
                ),
                persistence_failed_count=1,
                errors=tuple(errors),
            )

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

        return _RelationWriteOutcome(
            persisted_relations_count=1,
            pending_review_relations_count=1,
            relation_claims_count_delta=relation_claims_count_delta,
            relation_claims_queued_for_review_count=(
                relation_claims_queued_for_review_count
            ),
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
        relation_type_settings: ResearchSpaceSettings = {
            "dictionary_agent_creation_policy": "ACTIVE",
        }
        relation_source_ref = f"source_document:{document.id}:relation_persist"
        policy_run_id = normalize_run_id(
            policy_contract.agent_run_id if policy_contract is not None else None,
        )
        dictionary_fingerprint = self._resolve_dictionary_fingerprint()
        full_auto_retry_index = self._load_full_auto_retry_index(
            research_space_id=research_space_id,
            source_document_id=str(document.id),
            relation_governance_mode=relation_governance_mode,
        )
        full_auto_retry_skipped_count = 0

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

            candidate_signature = self._candidate_signature(effective_candidate)
            if relation_governance_mode == "FULL_AUTO":
                existing_retry_key = full_auto_retry_index.get(candidate_signature)
                if existing_retry_key == dictionary_fingerprint:
                    full_auto_retry_skipped_count += 1
                    if should_log_candidate:
                        logger.info(
                            "Persist relation candidate skipped: unchanged dictionary fingerprint",
                            extra={
                                "document_id": str(document.id),
                                "run_id": run_id,
                                "candidate_index": index,
                                "candidate_total": total_candidates,
                                "relation_type": effective_candidate.relation_type,
                                "dictionary_fingerprint": dictionary_fingerprint,
                            },
                        )
                    continue

            payload = candidate_payload(effective_candidate)
            if canonicalization_metadata:
                payload["canonicalization"] = canonicalization_metadata
            if relation_governance_mode == "FULL_AUTO":
                payload["auto_resolve_mode"] = "FULL_AUTO"
                payload["auto_resolve_policy_run_id"] = policy_run_id
                payload["auto_resolve_dictionary_fingerprint"] = dictionary_fingerprint
                payload["auto_resolve_confidence_threshold"] = (
                    _FULL_AUTO_CONFIDENCE_THRESHOLD
                )
                payload["auto_resolve_confidence_passed"] = (
                    effective_candidate.confidence >= _FULL_AUTO_CONFIDENCE_THRESHOLD
                )
                payload["auto_resolve_retry_on_dictionary_change_only"] = True
            claim_id: str | None = None
            if self._relation_claims is not None:
                try:
                    created_claim = self._relation_claims.create(
                        research_space_id=research_space_id,
                        source_document_id=str(document.id),
                        agent_run_id=run_id,
                        source_type=effective_candidate.source_type,
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
                except (TypeError, ValueError, SQLAlchemyError) as exc:
                    self._rollback_after_persistence_error(
                        context="relation_claim_create",
                    )
                    error_code = self._map_relation_write_error_code(exc)
                    errors.append(
                        (
                            "relation_claim_create_failed:"
                            f"{error_code}:{effective_candidate.relation_type}"
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
                                "error_code": error_code,
                                "error": str(exc),
                            },
                        )

            if effective_candidate.validation_state == "FORBIDDEN":
                forbidden_count += 1
            if effective_candidate.validation_state == "UNDEFINED":
                undefined_count += 1

            if effective_candidate.persistability != "PERSISTABLE":
                non_persistable_claims_count += 1
                if claim_id is not None:
                    if relation_governance_mode == "FULL_AUTO":
                        terminal_status = self._resolve_full_auto_terminal_status(
                            candidate=effective_candidate,
                        )
                        status_errors = self._set_claim_system_status(
                            claim_id=claim_id,
                            claim_status=terminal_status,
                        )
                        errors.extend(status_errors)
                        if terminal_status == "NEEDS_MAPPING":
                            full_auto_retry_index[candidate_signature] = (
                                dictionary_fingerprint
                            )
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
                relation_governance_mode == "HUMAN_IN_LOOP"
                and effective_candidate.validation_state != "ALLOWED"
            ):
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
                        "Persist relation candidate deferred by governance mode",
                        extra={
                            "document_id": str(document.id),
                            "run_id": run_id,
                            "candidate_index": index,
                            "candidate_total": total_candidates,
                            "relation_governance_mode": relation_governance_mode,
                            "validation_state": effective_candidate.validation_state,
                            "claim_id": claim_id,
                        },
                    )
                continue

            if (
                relation_governance_mode == "FULL_AUTO"
                and effective_candidate.validation_state != "ALLOWED"
            ):
                if claim_id is not None:
                    terminal_status = self._resolve_full_auto_terminal_status(
                        candidate=effective_candidate,
                    )
                    status_errors = self._set_claim_system_status(
                        claim_id=claim_id,
                        claim_status=terminal_status,
                    )
                    errors.extend(status_errors)
                    if terminal_status == "NEEDS_MAPPING":
                        full_auto_retry_index[candidate_signature] = (
                            dictionary_fingerprint
                        )
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
                        "Persist relation candidate stopped: full-auto unresolved validation",
                        extra={
                            "document_id": str(document.id),
                            "run_id": run_id,
                            "candidate_index": index,
                            "candidate_total": total_candidates,
                            "validation_state": effective_candidate.validation_state,
                            "validation_reason": effective_candidate.validation_reason,
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
                    if relation_governance_mode == "FULL_AUTO":
                        status_errors = self._set_claim_system_status(
                            claim_id=claim_id,
                            claim_status="NEEDS_MAPPING",
                        )
                        errors.extend(status_errors)
                        full_auto_retry_index[candidate_signature] = (
                            dictionary_fingerprint
                        )
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

            relation_type_ready = self._ensure_relation_type_exists(
                relation_type=effective_candidate.relation_type,
                source_ref=relation_source_ref,
                policy_settings=relation_type_settings,
            )
            if not relation_type_ready:
                persistence_failed_count += 1
                errors.append(
                    (
                        "relation_persistence_failed:"
                        "relation_type_invalid_or_inactive:"
                        f"{effective_candidate.relation_type}"
                    ),
                )
                if claim_id is not None:
                    if relation_governance_mode == "FULL_AUTO":
                        status_errors = self._set_claim_system_status(
                            claim_id=claim_id,
                            claim_status="NEEDS_MAPPING",
                        )
                        errors.extend(status_errors)
                        full_auto_retry_index[candidate_signature] = (
                            dictionary_fingerprint
                        )
                    self._enqueue_review_item(
                        entity_type="relation_claim",
                        entity_id=claim_id,
                        research_space_id=research_space_id,
                        priority="high",
                    )
                    relation_claims_queued_for_review_count += 1
                if should_log_candidate:
                    logger.warning(
                        "Persist relation candidate relation type activation failed",
                        extra={
                            "document_id": str(document.id),
                            "run_id": run_id,
                            "candidate_index": index,
                            "candidate_total": total_candidates,
                            "relation_type": effective_candidate.relation_type,
                        },
                    )
                continue

            write_outcome = self._persist_candidate_relation(
                document=document,
                run_id=run_id,
                research_space_id=research_space_id,
                relation_governance_mode=relation_governance_mode,
                effective_candidate=effective_candidate,
                mapping_proposal=mapping_proposal,
                constraint_lookup=constraint_lookup,
                claim_id=claim_id,
                payload=payload,
                candidate_signature=candidate_signature,
                full_auto_retry_index=full_auto_retry_index,
                dictionary_fingerprint=dictionary_fingerprint,
                index=index,
                total_candidates=total_candidates,
                should_log_candidate=should_log_candidate,
            )
            persisted_count += write_outcome.persisted_relations_count
            pending_count += write_outcome.pending_review_relations_count
            relation_claims_count += write_outcome.relation_claims_count_delta
            relation_claims_queued_for_review_count += (
                write_outcome.relation_claims_queued_for_review_count
            )
            persistence_failed_count += write_outcome.persistence_failed_count
            errors.extend(write_outcome.errors)

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
                "full_auto_retry_skipped_count": full_auto_retry_skipped_count,
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
            full_auto_retry_skipped_count=full_auto_retry_skipped_count,
            errors=tuple(errors),
        )


__all__ = ["RelationPersistenceResult", "_ExtractionRelationPersistenceHelpers"]
