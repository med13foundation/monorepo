"""Relation persistence helpers for extraction orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

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
from src.domain.value_objects.relation_types import normalize_relation_type

if TYPE_CHECKING:
    from src.domain.agents.contracts.extraction import (
        ExtractedRelation,
        ExtractionContract,
    )
    from src.domain.agents.contracts.extraction_policy import ExtractionPolicyContract
    from src.domain.entities.source_document import SourceDocument
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
    from src.domain.repositories.kernel.relation_repository import (
        KernelRelationRepository,
    )
    from src.type_definitions.common import JSONObject


@dataclass(frozen=True)
class RelationPersistenceResult:
    """Persistence + review outcome for extracted relation candidates."""

    persisted_relations_count: int = 0
    pending_review_relations_count: int = 0
    forbidden_relations_count: int = 0
    undefined_relations_count: int = 0
    policy_proposals_count: int = 0
    policy_run_id: str | None = None
    rejected_relation_reasons: tuple[str, ...] = ()
    rejected_relation_details: tuple[JSONObject, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _CandidateBuildResult:
    candidates: tuple[_ResolvedRelationCandidate, ...] = ()
    rejected_relation_reasons: tuple[str, ...] = ()
    rejected_relation_details: tuple[JSONObject, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _PersistCandidatesResult:
    persisted_relations_count: int = 0
    pending_review_relations_count: int = 0
    forbidden_relations_count: int = 0
    undefined_relations_count: int = 0
    rejected_relation_reasons: tuple[str, ...] = ()
    rejected_relation_details: tuple[JSONObject, ...] = ()
    errors: tuple[str, ...] = ()


class _ExtractionRelationPersistenceHelpers(
    _RelationEndpointEntityResolutionHelpers,
    _ExtractionRelationPolicyHelpers,
):
    """Shared relation-persistence helpers for extraction service."""

    _relations: KernelRelationRepository | None
    _entities: KernelEntityRepository | None

    async def _persist_extracted_relations(
        self,
        *,
        document: SourceDocument,
        contract: ExtractionContract,
        publication_entity_ids: tuple[str, ...],
        run_id: str | None,
        model_id: str | None,
    ) -> RelationPersistenceResult:
        if document.research_space_id is None:
            return RelationPersistenceResult(
                errors=("relation_persistence_missing_research_space_id",),
            )
        research_space_id = str(document.research_space_id)
        if not contract.relations:
            return RelationPersistenceResult()
        if self._relations is None or self._entities is None:
            return RelationPersistenceResult(
                errors=("relation_persistence_unavailable",),
            )

        publication_entity_id = (
            publication_entity_ids[0] if publication_entity_ids else None
        )
        candidate_build = self._build_relation_candidates(
            research_space_id=research_space_id,
            relations=contract.relations,
            publication_entity_id=publication_entity_id,
        )
        unknown_patterns = self._build_unknown_relation_patterns(
            candidate_build.candidates,
        )
        policy_step = await self._run_policy_step(
            research_space_id=research_space_id,
            document=document,
            source_type=contract.source_type,
            unknown_patterns=unknown_patterns,
            model_id=model_id,
        )
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
        )
        persist_result = self._persist_relation_candidates(
            research_space_id=research_space_id,
            document=document,
            run_id=run_id,
            candidates=candidate_build.candidates,
            policy_contract=policy_step.contract,
        )
        return RelationPersistenceResult(
            persisted_relations_count=persist_result.persisted_relations_count,
            pending_review_relations_count=persist_result.pending_review_relations_count,
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
                        "validation_state": "UNDEFINED",
                        "validation_reason": (
                            "source_type, relation_type, and target_type are required"
                        ),
                    },
                )
                errors.append("relation_persistence_skipped_invalid_components")
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
                        "validation_state": "UNDEFINED",
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
                continue
            if source_entity_id == target_entity_id:
                self._record_rejected_relation(
                    reasons=rejected_reasons,
                    details=rejected_details,
                    reason="relation_self_loop",
                    payload=payload,
                    metadata={
                        "validation_state": "FORBIDDEN",
                        "validation_reason": "self-loop relations are not allowed",
                    },
                )
                errors.append(
                    (
                        "relation_persistence_skipped_self_loop:"
                        f"{normalized_relation_type}:{source_entity_id}"
                    ),
                )
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
                ),
            )

        return _CandidateBuildResult(
            candidates=tuple(candidates),
            rejected_relation_reasons=tuple(rejected_reasons),
            rejected_relation_details=tuple(rejected_details),
            errors=tuple(errors),
        )

    def _persist_relation_candidates(
        self,
        *,
        research_space_id: str,
        document: SourceDocument,
        run_id: str | None,
        candidates: tuple[_ResolvedRelationCandidate, ...],
        policy_contract: ExtractionPolicyContract | None,
    ) -> _PersistCandidatesResult:
        if self._relations is None:
            return _PersistCandidatesResult(
                errors=("relation_persistence_unavailable",),
            )

        persisted_count = 0
        pending_count = 0
        forbidden_count = 0
        undefined_count = 0
        rejected_reasons: list[str] = []
        rejected_details: list[JSONObject] = []
        errors: list[str] = []

        constraint_lookup = self._index_constraint_proposals(policy_contract)
        mapping_lookup = self._index_mapping_proposals(policy_contract)

        for candidate in candidates:
            payload = candidate_payload(candidate)
            if candidate.validation_state == "FORBIDDEN":
                forbidden_count += 1
                self._record_rejected_relation(
                    reasons=rejected_reasons,
                    details=rejected_details,
                    reason="forbidden_by_dictionary_constraint",
                    payload=payload,
                    metadata={
                        "validation_state": candidate.validation_state,
                        "validation_reason": candidate.validation_reason,
                    },
                )
                continue

            try:
                created_relation = self._relations.create(
                    research_space_id=research_space_id,
                    source_id=candidate.source_entity_id,
                    relation_type=candidate.relation_type,
                    target_id=candidate.target_entity_id,
                    confidence=candidate.confidence,
                    evidence_summary=self._build_relation_evidence_summary(
                        document=document,
                        candidate=candidate,
                        constraint_proposal=constraint_lookup.get(
                            (
                                candidate.source_type,
                                candidate.relation_type,
                                candidate.target_type,
                            ),
                        ),
                        mapping_proposal=mapping_lookup.get(
                            (
                                candidate.source_type,
                                candidate.relation_type,
                                candidate.target_type,
                            ),
                        ),
                    ),
                    evidence_tier="COMPUTATIONAL",
                    curation_status=(
                        "PENDING_REVIEW"
                        if candidate.validation_state == "UNDEFINED"
                        else "DRAFT"
                    ),
                    source_document_id=str(document.id),
                    agent_run_id=run_id,
                )
                persisted_count += 1
            except (TypeError, ValueError) as exc:
                errors.append(
                    (
                        "relation_persistence_failed:"
                        f"{candidate.relation_type}:{candidate.source_entity_id}"
                        f"->{candidate.target_entity_id}:{exc!s}"
                    ),
                )
                continue

            if candidate.validation_state != "UNDEFINED":
                continue

            pending_count += 1
            undefined_count += 1
            self._record_rejected_relation(
                reasons=rejected_reasons,
                details=rejected_details,
                reason="undefined_relation_persisted_pending_review",
                payload=payload,
                metadata={
                    "status": "pending_review",
                    "validation_state": candidate.validation_state,
                    "validation_reason": candidate.validation_reason,
                },
            )
            self._enqueue_review_item(
                entity_type="relation",
                entity_id=str(created_relation.id),
                research_space_id=research_space_id,
                priority="medium",
            )

        return _PersistCandidatesResult(
            persisted_relations_count=persisted_count,
            pending_review_relations_count=pending_count,
            forbidden_relations_count=forbidden_count,
            undefined_relations_count=undefined_count,
            rejected_relation_reasons=tuple(rejected_reasons),
            rejected_relation_details=tuple(rejected_details),
            errors=tuple(errors),
        )

    @staticmethod
    def _normalize_component(raw_value: str) -> str:
        return raw_value.strip().upper()


__all__ = ["RelationPersistenceResult", "_ExtractionRelationPersistenceHelpers"]
