"""Policy and validation helper mixin for extraction relation persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.domain.agents.contracts.extraction_policy import (
        ExtractionPolicyContract,
        RelationConstraintProposal,
        RelationTypeMappingProposal,
        UnknownRelationPattern,
    )
    from src.domain.agents.ports.extraction_policy_agent_port import (
        ExtractionPolicyAgentPort,
    )
    from src.domain.entities.source_document import SourceDocument
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.type_definitions.common import JSONObject, ResearchSpaceSettings

logger = logging.getLogger(__name__)

type RelationValidationState = Literal["ALLOWED", "FORBIDDEN", "UNDEFINED"]

_POLICY_AGENT_CREATED_BY = "agent:extraction_policy_step"


@dataclass(frozen=True)
class _ResolvedRelationCandidate:
    source_entity_id: str
    target_entity_id: str
    source_type: str
    relation_type: str
    target_type: str
    source_label: str | None
    target_label: str | None
    confidence: float
    validation_state: RelationValidationState
    validation_reason: str


@dataclass(frozen=True)
class _PolicyStepResult:
    contract: ExtractionPolicyContract | None = None
    errors: tuple[str, ...] = ()


class _ExtractionRelationPolicyHelpers:
    """Policy-step and dictionary-validation helpers."""

    _dictionary: DictionaryPort | None
    _policy_agent: ExtractionPolicyAgentPort | None
    _review_queue_submitter: Callable[[str, str, str | None, str], None] | None

    async def _run_policy_step(
        self,
        *,
        research_space_id: str,
        document: SourceDocument,
        source_type: str,
        unknown_patterns: tuple[UnknownRelationPattern, ...],
        model_id: str | None,
    ) -> _PolicyStepResult:
        policy_agent = self._policy_agent
        if policy_agent is None or not unknown_patterns:
            return _PolicyStepResult()

        from src.domain.agents.contexts.extraction_policy_context import (
            ExtractionPolicyContext,
        )

        context = ExtractionPolicyContext(
            document_id=str(document.id),
            source_type=source_type.strip().lower(),
            research_space_id=research_space_id,
            unknown_relation_patterns=list(unknown_patterns),
            current_constraints=list(
                self._build_constraints_snapshot(unknown_patterns),
            ),
            existing_relation_types=list(self._list_active_relation_types()),
            shadow_mode=False,
        )
        try:
            contract = await policy_agent.propose(context, model_id=model_id)
            return _PolicyStepResult(contract=contract)
        except Exception as exc:  # noqa: BLE001 - never block fail-open persistence
            logger.warning(
                "Policy step failed for document_id=%s: %s",
                document.id,
                exc,
            )
            return _PolicyStepResult(
                errors=(f"relation_policy_step_failed:{type(exc).__name__}",),
            )

    def _store_policy_constraint_proposals(
        self,
        *,
        research_space_id: str,
        document: SourceDocument,
        policy_contract: ExtractionPolicyContract | None,
        policy_run_id: str | None,
    ) -> tuple[int, tuple[str, ...]]:
        if self._dictionary is None or policy_contract is None:
            return 0, ()
        source_ref = f"source_document:{document.id}"
        if policy_run_id is not None:
            source_ref = f"{source_ref}:policy_run:{policy_run_id}"

        created_count = 0
        errors: list[str] = []
        seen_keys: set[tuple[str, str, str]] = set()

        for proposal in policy_contract.relation_constraint_proposals:
            triple = self._proposal_triple_key(
                proposal.source_type,
                proposal.relation_type,
                proposal.target_type,
            )
            if triple is None or triple in seen_keys:
                continue
            seen_keys.add(triple)
            if self._create_pending_constraint(
                triple=triple,
                is_allowed=proposal.proposed_is_allowed,
                requires_evidence=proposal.proposed_requires_evidence,
                source_ref=source_ref,
                errors=errors,
            ):
                created_count += 1
                self._enqueue_review_item(
                    entity_type="relation_constraint",
                    entity_id=f"{triple[0]}:{triple[1]}:{triple[2]}",
                    research_space_id=research_space_id,
                    priority="low",
                )

        for mapping in policy_contract.relation_type_mapping_proposals:
            triple = self._proposal_triple_key(
                mapping.source_type,
                mapping.mapped_relation_type,
                mapping.target_type,
            )
            if triple is None or triple in seen_keys:
                continue
            seen_keys.add(triple)
            if self._create_pending_constraint(
                triple=triple,
                is_allowed=True,
                requires_evidence=True,
                source_ref=source_ref,
                errors=errors,
            ):
                created_count += 1
                self._enqueue_review_item(
                    entity_type="relation_constraint",
                    entity_id=f"{triple[0]}:{triple[1]}:{triple[2]}",
                    research_space_id=research_space_id,
                    priority="low",
                )

        return created_count, tuple(errors)

    def _create_pending_constraint(
        self,
        *,
        triple: tuple[str, str, str],
        is_allowed: bool,
        requires_evidence: bool,
        source_ref: str,
        errors: list[str],
    ) -> bool:
        if self._dictionary is None:
            return False
        policy_settings: ResearchSpaceSettings = {
            "dictionary_agent_creation_policy": "PENDING_REVIEW",
        }
        try:
            self._dictionary.create_relation_constraint(
                source_type=triple[0],
                relation_type=triple[1],
                target_type=triple[2],
                is_allowed=is_allowed,
                requires_evidence=requires_evidence,
                created_by=_POLICY_AGENT_CREATED_BY,
                source_ref=source_ref,
                research_space_settings=policy_settings,
            )
        except ValueError as exc:
            errors.append(
                (
                    "relation_policy_proposal_store_failed:"
                    f"{triple[0]}:{triple[1]}:{triple[2]}:{exc!s}"
                ),
            )
            return False
        else:
            return True

    def _build_unknown_relation_patterns(
        self,
        candidates: tuple[_ResolvedRelationCandidate, ...],
    ) -> tuple[UnknownRelationPattern, ...]:
        from src.domain.agents.contracts.extraction_policy import UnknownRelationPattern

        aggregated: dict[
            tuple[str, str, str],
            tuple[str | None, str | None, int],
        ] = {}
        for candidate in candidates:
            if candidate.validation_state != "UNDEFINED":
                continue
            key = (
                candidate.source_type,
                candidate.relation_type,
                candidate.target_type,
            )
            current = aggregated.get(key)
            if current is None:
                aggregated[key] = (
                    candidate.source_label,
                    candidate.target_label,
                    1,
                )
                continue
            aggregated[key] = (current[0], current[1], current[2] + 1)

        patterns = [
            UnknownRelationPattern(
                source_type=source_type,
                relation_type=relation_type,
                target_type=target_type,
                source_label_example=source_label,
                target_label_example=target_label,
                occurrences=count,
            )
            for (source_type, relation_type, target_type), (
                source_label,
                target_label,
                count,
            ) in aggregated.items()
        ]
        return tuple(patterns)

    def _build_constraints_snapshot(
        self,
        unknown_patterns: tuple[UnknownRelationPattern, ...],
    ) -> tuple[JSONObject, ...]:
        if self._dictionary is None:
            return ()

        snapshot: list[JSONObject] = []
        seen_keys: set[tuple[str, str, str, str, bool, bool, bool]] = set()
        for pattern in unknown_patterns:
            constraints = self._dictionary.get_constraints(
                source_type=pattern.source_type,
                relation_type=pattern.relation_type,
                include_inactive=True,
            )
            for constraint in constraints:
                key = (
                    constraint.source_type,
                    constraint.relation_type,
                    constraint.target_type,
                    constraint.review_status,
                    bool(constraint.is_allowed),
                    bool(constraint.requires_evidence),
                    bool(constraint.is_active),
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                snapshot.append(
                    {
                        "source_type": constraint.source_type,
                        "relation_type": constraint.relation_type,
                        "target_type": constraint.target_type,
                        "review_status": constraint.review_status,
                        "is_allowed": constraint.is_allowed,
                        "requires_evidence": constraint.requires_evidence,
                        "is_active": constraint.is_active,
                    },
                )
        return tuple(snapshot)

    def _list_active_relation_types(self) -> tuple[str, ...]:
        if self._dictionary is None:
            return ()

        relation_types = []
        for relation_type in self._dictionary.list_relation_types(
            include_inactive=False,
        ):
            if not relation_type.is_active:
                continue
            if relation_type.review_status != "ACTIVE":
                continue
            normalized = relation_type.id.strip().upper()
            if not normalized or normalized in relation_types:
                continue
            relation_types.append(normalized)
        return tuple(relation_types)

    def _resolve_relation_validation_state(
        self,
        *,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> tuple[RelationValidationState, str]:
        if self._dictionary is None:
            return "UNDEFINED", "dictionary_service_unavailable"

        constraints = self._dictionary.get_constraints(
            source_type=source_type,
            relation_type=relation_type,
            include_inactive=True,
        )
        matching = [
            constraint
            for constraint in constraints
            if constraint.target_type == target_type
        ]
        if not matching:
            return "UNDEFINED", "constraint_not_defined"

        active_constraints = [
            constraint
            for constraint in matching
            if constraint.is_active and constraint.review_status == "ACTIVE"
        ]
        if active_constraints:
            if any(constraint.is_allowed for constraint in active_constraints):
                return "ALLOWED", "allowed_by_active_constraint"
            return "FORBIDDEN", "forbidden_by_active_constraint"

        if any(
            constraint.is_active and constraint.review_status == "PENDING_REVIEW"
            for constraint in matching
        ):
            return "UNDEFINED", "constraint_pending_review"
        return "UNDEFINED", "constraint_inactive_or_revoked"

    def _build_relation_evidence_summary(
        self,
        *,
        document: SourceDocument,
        candidate: _ResolvedRelationCandidate,
        constraint_proposal: RelationConstraintProposal | None,
        mapping_proposal: RelationTypeMappingProposal | None,
    ) -> str:
        parts = [f"Extracted from source_document:{document.id}"]
        if candidate.validation_state == "UNDEFINED":
            parts.append(f"validation:{candidate.validation_reason}")
            if constraint_proposal is not None:
                parts.append(
                    (
                        "constraint_proposal:"
                        f"allowed={constraint_proposal.proposed_is_allowed},"
                        f"requires_evidence={constraint_proposal.proposed_requires_evidence}"
                    ),
                )
            if mapping_proposal is not None:
                parts.append(
                    (
                        "mapping_proposal:"
                        f"{mapping_proposal.observed_relation_type}"
                        f"->{mapping_proposal.mapped_relation_type}"
                    ),
                )
        return " | ".join(parts)

    def _index_constraint_proposals(
        self,
        policy_contract: ExtractionPolicyContract | None,
    ) -> dict[tuple[str, str, str], RelationConstraintProposal]:
        if policy_contract is None:
            return {}
        indexed: dict[tuple[str, str, str], RelationConstraintProposal] = {}
        for proposal in policy_contract.relation_constraint_proposals:
            key = self._proposal_triple_key(
                proposal.source_type,
                proposal.relation_type,
                proposal.target_type,
            )
            if key is None:
                continue
            current = indexed.get(key)
            if current is None or proposal.confidence > current.confidence:
                indexed[key] = proposal
        return indexed

    def _index_mapping_proposals(
        self,
        policy_contract: ExtractionPolicyContract | None,
    ) -> dict[tuple[str, str, str], RelationTypeMappingProposal]:
        if policy_contract is None:
            return {}
        indexed: dict[tuple[str, str, str], RelationTypeMappingProposal] = {}
        for proposal in policy_contract.relation_type_mapping_proposals:
            key = self._proposal_triple_key(
                proposal.source_type,
                proposal.observed_relation_type,
                proposal.target_type,
            )
            if key is None:
                continue
            current = indexed.get(key)
            if current is None or proposal.confidence > current.confidence:
                indexed[key] = proposal
        return indexed

    def _proposal_triple_key(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> tuple[str, str, str] | None:
        normalized_source = self._normalize_component(source_type)
        normalized_relation = self._normalize_component(relation_type)
        normalized_target = self._normalize_component(target_type)
        if not normalized_source or not normalized_relation or not normalized_target:
            return None
        return normalized_source, normalized_relation, normalized_target

    def _record_rejected_relation(
        self,
        *,
        reasons: list[str],
        details: list[JSONObject],
        reason: str,
        payload: JSONObject,
        metadata: JSONObject | None = None,
    ) -> None:
        normalized_reason = reason.strip()
        if normalized_reason and normalized_reason not in reasons:
            reasons.append(normalized_reason)
        detail: JSONObject = {
            "reason": normalized_reason,
            "status": "rejected",
            "payload": payload,
        }
        if metadata is not None:
            for key, value in metadata.items():
                detail[str(key)] = to_json_value(value)
        details.append(detail)

    @staticmethod
    def _merge_unique_reasons(
        first: tuple[str, ...],
        second: tuple[str, ...],
    ) -> tuple[str, ...]:
        merged: list[str] = []
        for reason in first + second:
            normalized = reason.strip()
            if not normalized or normalized in merged:
                continue
            merged.append(normalized)
        return tuple(merged)

    def _enqueue_review_item(
        self,
        *,
        entity_type: str,
        entity_id: str,
        research_space_id: str | None,
        priority: str,
    ) -> None:
        submitter = self._review_queue_submitter
        if submitter is None:
            return
        try:
            submitter(entity_type, entity_id, research_space_id, priority)
        except Exception as exc:  # noqa: BLE001 - never block extraction on queue write
            logger.warning(
                "Failed to enqueue review item entity_type=%s entity_id=%s: %s",
                entity_type,
                entity_id,
                exc,
            )

    @staticmethod
    def _normalize_component(raw_value: str) -> str:
        msg = "subclass must implement _normalize_component"
        raise NotImplementedError(msg)

    @staticmethod
    def _normalize_run_id(run_id: str | None) -> str | None:
        msg = "subclass must implement _normalize_run_id"
        raise NotImplementedError(msg)
