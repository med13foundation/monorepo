"""Write-phase relation candidate persistence flow extracted for file-size limits."""

from __future__ import annotations

# ruff: noqa: SLF001
import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from src.application.agents.services._extraction_relation_auto_resolve_helpers import (
    _FULL_AUTO_CONFIDENCE_THRESHOLD,
)
from src.application.agents.services._relation_persistence_payload_helpers import (
    candidate_payload,
    normalize_run_id,
)

if TYPE_CHECKING:
    from src.application.agents.services._extraction_relation_persistence_helpers import (
        _ExtractionRelationPersistenceHelpers,
    )
    from src.application.agents.services._extraction_relation_policy_helpers import (
        RelationGovernanceMode,
        _ResolvedRelationCandidate,
    )
    from src.domain.agents.contracts.extraction_policy import ExtractionPolicyContract
    from src.domain.entities.source_document import SourceDocument
    from src.type_definitions.common import JSONObject, ResearchSpaceSettings

_PER_CANDIDATE_LOG_THRESHOLD = 25
_PER_CANDIDATE_LOG_INTERVAL = 10
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PersistCandidatesResult:
    persisted_relations_count: int = 0
    pending_review_relations_count: int = 0
    relation_claims_count: int = 0
    relation_claims_queued_for_review_count: int = 0
    non_persistable_claims_count: int = 0
    forbidden_relations_count: int = 0
    undefined_relations_count: int = 0
    evidence_span_missing_count: int = 0
    rejected_relation_reasons: tuple[str, ...] = ()
    rejected_relation_details: tuple[JSONObject, ...] = ()
    persistence_failed_count: int = 0
    full_auto_retry_skipped_count: int = 0
    errors: tuple[str, ...] = ()


def persist_relation_candidates(  # noqa: C901, PLR0912, PLR0913, PLR0915
    *,
    helper: _ExtractionRelationPersistenceHelpers,
    document: SourceDocument,
    run_id: str | None,
    candidates: tuple[_ResolvedRelationCandidate, ...],
    policy_contract: ExtractionPolicyContract | None,
    relation_governance_mode: RelationGovernanceMode,
    research_space_settings: ResearchSpaceSettings,
) -> _PersistCandidatesResult:
    if helper._relations is None:
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
    evidence_span_missing_count = 0
    rejected_reasons: list[str] = []
    rejected_details: list[JSONObject] = []
    errors: list[str] = []
    persistence_failed_count = 0

    constraint_lookup = helper._index_constraint_proposals(policy_contract)
    mapping_lookup = helper._index_mapping_proposals(policy_contract)
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
    dictionary_fingerprint = helper._resolve_dictionary_fingerprint()
    full_auto_retry_index = helper._load_full_auto_retry_index(
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
            ) = helper._canonicalize_relation_candidate(
                candidate=effective_candidate,
                mapping_proposal=mapping_proposal,
                document=document,
            )
            validation_state, validation_reason = (
                helper._resolve_relation_validation_state(
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
            effective_candidate = helper._resolve_full_auto_candidate(
                candidate=effective_candidate,
                mapping_proposal=mapping_proposal,
                source_ref=f"source_document:{document.id}:full_auto_persist",
            )

        candidate_signature = helper._candidate_signature(effective_candidate)
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

        effective_constraint_proposal = constraint_lookup.get(
            (
                effective_candidate.source_type,
                effective_candidate.relation_type,
                effective_candidate.target_type,
            ),
        )
        requires_evidence_span = helper._should_require_relation_evidence_span(
            document=document,
            candidate=effective_candidate,
            research_space_settings=research_space_settings,
        )
        (
            relation_evidence_summary,
            relation_evidence_metadata,
            relation_evidence_failure,
        ) = helper._prepare_relation_evidence_summary(
            document=document,
            candidate=effective_candidate,
            relation_governance_mode=relation_governance_mode,
            constraint_proposal=effective_constraint_proposal,
            mapping_proposal=mapping_proposal,
            requires_evidence_span=requires_evidence_span,
        )
        payload["relation_evidence"] = relation_evidence_metadata

        claim_id: str | None = None
        if helper._relation_claims is not None:
            try:
                created_claim = helper._relation_claims.create(
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
                helper._rollback_after_persistence_error(
                    context="relation_claim_create",
                )
                error_code = helper._map_relation_write_error_code(exc)
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
                    terminal_status = helper._resolve_full_auto_terminal_status(
                        candidate=effective_candidate,
                    )
                    status_errors = helper._set_claim_system_status(
                        claim_id=claim_id,
                        claim_status=terminal_status,
                    )
                    errors.extend(status_errors)
                    if terminal_status == "NEEDS_MAPPING":
                        full_auto_retry_index[candidate_signature] = (
                            dictionary_fingerprint
                        )
                helper._enqueue_review_item(
                    entity_type="relation_claim",
                    entity_id=claim_id,
                    research_space_id=research_space_id,
                    priority=helper._review_priority_for_candidate(
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
                helper._enqueue_review_item(
                    entity_type="relation_claim",
                    entity_id=claim_id,
                    research_space_id=research_space_id,
                    priority=helper._review_priority_for_candidate(
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
                terminal_status = helper._resolve_full_auto_terminal_status(
                    candidate=effective_candidate,
                )
                status_errors = helper._set_claim_system_status(
                    claim_id=claim_id,
                    claim_status=terminal_status,
                )
                errors.extend(status_errors)
                if terminal_status == "NEEDS_MAPPING":
                    full_auto_retry_index[candidate_signature] = dictionary_fingerprint
                helper._enqueue_review_item(
                    entity_type="relation_claim",
                    entity_id=claim_id,
                    research_space_id=research_space_id,
                    priority=helper._review_priority_for_candidate(
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

        if relation_evidence_failure is not None:
            evidence_span_missing_count += 1
            non_persistable_claims_count += 1
            helper._record_rejected_relation(
                reasons=rejected_reasons,
                details=rejected_details,
                reason="relation_evidence_span_missing",
                payload=payload,
                metadata={
                    "validation_state": "EVIDENCE_SPAN_MISSING",
                    "validation_reason": relation_evidence_failure,
                    "relation_evidence": relation_evidence_metadata,
                },
            )
            if claim_id is not None:
                if relation_governance_mode == "FULL_AUTO":
                    status_errors = helper._set_claim_system_status(
                        claim_id=claim_id,
                        claim_status="NEEDS_MAPPING",
                    )
                    errors.extend(status_errors)
                    full_auto_retry_index[candidate_signature] = dictionary_fingerprint
                helper._enqueue_review_item(
                    entity_type="relation_claim",
                    entity_id=claim_id,
                    research_space_id=research_space_id,
                    priority="high",
                )
                relation_claims_queued_for_review_count += 1
            if should_log_candidate:
                logger.info(
                    "Persist relation candidate blocked by evidence-span requirement",
                    extra={
                        "document_id": str(document.id),
                        "run_id": run_id,
                        "candidate_index": index,
                        "candidate_total": total_candidates,
                        "relation_type": effective_candidate.relation_type,
                        "validation_reason": relation_evidence_failure,
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
                    status_errors = helper._set_claim_system_status(
                        claim_id=claim_id,
                        claim_status="NEEDS_MAPPING",
                    )
                    errors.extend(status_errors)
                    full_auto_retry_index[candidate_signature] = dictionary_fingerprint
                helper._enqueue_review_item(
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

        relation_type_ready = helper._ensure_relation_type_exists(
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
                    status_errors = helper._set_claim_system_status(
                        claim_id=claim_id,
                        claim_status="NEEDS_MAPPING",
                    )
                    errors.extend(status_errors)
                    full_auto_retry_index[candidate_signature] = dictionary_fingerprint
                helper._enqueue_review_item(
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

        write_outcome = helper._persist_candidate_relation(
            document=document,
            run_id=run_id,
            research_space_id=research_space_id,
            relation_governance_mode=relation_governance_mode,
            effective_candidate=effective_candidate,
            evidence_summary=relation_evidence_summary,
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
            "duration_ms": int((datetime.now(UTC) - started_at).total_seconds() * 1000),
            "candidate_count": total_candidates,
            "persisted_relations_count": persisted_count,
            "pending_review_relations_count": pending_count,
            "relation_claims_count": relation_claims_count,
            "relation_claims_queued_for_review_count": (
                relation_claims_queued_for_review_count
            ),
            "non_persistable_claims_count": non_persistable_claims_count,
            "evidence_span_missing_count": evidence_span_missing_count,
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
        evidence_span_missing_count=evidence_span_missing_count,
        rejected_relation_reasons=tuple(rejected_reasons),
        rejected_relation_details=tuple(rejected_details),
        persistence_failed_count=persistence_failed_count,
        full_auto_retry_skipped_count=full_auto_retry_skipped_count,
        errors=tuple(errors),
    )


__all__ = ["_PersistCandidatesResult", "persist_relation_candidates"]
