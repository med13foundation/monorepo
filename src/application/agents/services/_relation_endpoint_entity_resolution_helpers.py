"""Endpoint entity-resolution helpers for extraction relation persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.agents.services._relation_endpoint_label_resolution_helpers import (
    build_concept_family_key,
    build_entity_concept_key,
    build_label_variants,
    evaluate_entity_shape,
    select_best_candidate,
)
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
    from src.domain.entities.kernel.entities import KernelEntity
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
    from src.type_definitions.common import JSONObject
else:
    JSONObject = dict[str, object]

logger = logging.getLogger(__name__)
_ENDPOINT_ENTITY_TYPE_CREATED_BY = "agent:extraction_endpoint_entity_bootstrap"
_ENDPOINT_SHAPE_ACCEPT_VARIABLE_ID = "ACCEPT_ENDPOINT_LABEL"
_ENDPOINT_SHAPE_REJECT_VARIABLE_ID = "REJECT_ENDPOINT_LABEL"


@dataclass(frozen=True)
class EndpointEntityResolutionResult:
    """Structured endpoint resolution result with rejection diagnostics."""

    entity_id: str | None
    failure_reason: str | None = None
    failure_metadata: JSONObject | None = None


@dataclass(frozen=True)
class _BorderlineShapeJudgeResult:
    accepted: bool
    reason_code: str
    metadata: JSONObject


class _RelationEndpointEntityResolutionHelpers:
    """Shared endpoint resolution and concept-identifier helpers."""

    _entities: KernelEntityRepository | None
    _dictionary: DictionaryPort | None
    _endpoint_shape_judge: MappingJudgePort | None

    def _resolve_relation_endpoint_entity_id(  # noqa: C901, PLR0911
        self,
        *,
        research_space_id: str,
        entity_type: str,
        label: str | None,
        publication_entity_id: str | None,
        endpoint_name: str,
    ) -> EndpointEntityResolutionResult:
        normalized_type = entity_type.strip().upper()
        if not normalized_type:
            return EndpointEntityResolutionResult(
                entity_id=None,
                failure_reason="relation_endpoint_invalid_entity_type",
            )

        if normalized_type == "PUBLICATION" and publication_entity_id is not None:
            return EndpointEntityResolutionResult(entity_id=publication_entity_id)

        normalized_label = label.strip() if isinstance(label, str) else ""
        if not normalized_label:
            return EndpointEntityResolutionResult(
                entity_id=None,
                failure_reason="relation_endpoint_missing_label",
            )

        if self._entities is None:
            return EndpointEntityResolutionResult(
                entity_id=None,
                failure_reason="relation_endpoint_entity_repository_unavailable",
            )

        concept_match = self._resolve_existing_entity_by_concept_key(
            research_space_id=research_space_id,
            entity_type=normalized_type,
            normalized_label=normalized_label,
        )
        if concept_match is not None:
            return EndpointEntityResolutionResult(entity_id=concept_match)

        label_search_match = self._resolve_existing_entity_by_label_search(
            research_space_id=research_space_id,
            entity_type=normalized_type,
            normalized_label=normalized_label,
        )
        if label_search_match is not None:
            return EndpointEntityResolutionResult(entity_id=label_search_match)

        shape_decision = evaluate_entity_shape(
            entity_type=normalized_type,
            label=normalized_label,
        )
        if shape_decision.outcome == "REJECT":
            return EndpointEntityResolutionResult(
                entity_id=None,
                failure_reason="relation_endpoint_shape_rejected",
                failure_metadata={
                    "shape_guard_reason": shape_decision.reason_code,
                    "shape_guard_outcome": shape_decision.outcome,
                    "shape_guard_signals": list(shape_decision.signals),
                    "shape_rejection_subreason": "hard_reject",
                },
            )
        if shape_decision.outcome == "BORDERLINE":
            judge_result = self._judge_borderline_endpoint_shape(
                research_space_id=research_space_id,
                entity_type=normalized_type,
                endpoint_name=endpoint_name,
                normalized_label=shape_decision.normalized_label,
                shape_signals=shape_decision.signals,
            )
            if not judge_result.accepted:
                return EndpointEntityResolutionResult(
                    entity_id=None,
                    failure_reason="relation_endpoint_shape_rejected",
                    failure_metadata=judge_result.metadata,
                )

        created_entity_id = self._create_relation_endpoint_entity(
            research_space_id=research_space_id,
            entity_type=normalized_type,
            normalized_label=shape_decision.normalized_label,
            endpoint_name=endpoint_name,
        )
        if created_entity_id is None:
            return EndpointEntityResolutionResult(
                entity_id=None,
                failure_reason="relation_endpoint_create_failed",
            )
        return EndpointEntityResolutionResult(entity_id=created_entity_id)

    def _resolve_existing_entity_by_concept_key(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        normalized_label: str,
    ) -> str | None:
        if self._entities is None:
            return None
        concept_key = build_entity_concept_key(entity_type, normalized_label)
        if concept_key is None:
            return None
        concept_entity = self._entities.find_by_identifier(
            namespace="CONCEPT_KEY",
            identifier_value=concept_key,
            research_space_id=research_space_id,
        )
        if concept_entity is None:
            return None
        if concept_entity.entity_type.strip().upper() != entity_type:
            return None
        concept_entity_id = str(concept_entity.id)
        self._ensure_concept_identifiers(
            entity_id=concept_entity_id,
            entity_type=entity_type,
            label=(
                concept_entity.display_label
                if isinstance(concept_entity.display_label, str)
                else normalized_label
            ),
        )
        return concept_entity_id

    def _resolve_existing_entity_by_label_search(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        normalized_label: str,
    ) -> str | None:
        if self._entities is None:
            return None
        label_variants = build_label_variants(normalized_label)
        candidate_by_id: dict[str, KernelEntity] = {}
        for query_variant in label_variants:
            for candidate in self._entities.search(
                research_space_id,
                query_variant,
                entity_type=entity_type,
                limit=10,
            ):
                candidate_by_id[str(candidate.id)] = candidate
        candidates = tuple(candidate_by_id.values())
        resolved = select_best_candidate(
            query_label=normalized_label,
            candidates=candidates,
        )
        if resolved is not None:
            resolved_id = str(resolved.id)
            self._ensure_concept_identifiers(
                entity_id=resolved_id,
                entity_type=entity_type,
                label=(
                    resolved.display_label
                    if isinstance(resolved.display_label, str)
                    else normalized_label
                ),
            )
            return resolved_id
        if candidates:
            logger.info(
                "Endpoint label search returned candidates but no safe match; creating new entity",
                extra={
                    "entity_type": entity_type,
                    "query_label": normalized_label,
                    "candidate_count": len(candidates),
                },
            )
        return None

    def _create_relation_endpoint_entity(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        normalized_label: str,
        endpoint_name: str,
    ) -> str | None:
        if self._entities is None:
            return None
        if not self._ensure_active_endpoint_entity_type(
            entity_type=entity_type,
            endpoint_name=endpoint_name,
        ):
            return None

        metadata: JSONObject = {
            "created_from": "extraction_relation_endpoint",
            "endpoint": endpoint_name,
        }
        try:
            created = self._entities.create(
                research_space_id=research_space_id,
                entity_type=entity_type,
                display_label=normalized_label,
                metadata={
                    str(key): to_json_value(value) for key, value in metadata.items()
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to create extraction endpoint entity type=%s label=%s: %s",
                entity_type,
                normalized_label,
                exc,
            )
            return None
        created_id = str(created.id)
        self._ensure_concept_identifiers(
            entity_id=created_id,
            entity_type=entity_type,
            label=normalized_label,
        )
        return created_id

    def _judge_borderline_endpoint_shape(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        endpoint_name: str,
        normalized_label: str,
        shape_signals: tuple[str, ...],
    ) -> _BorderlineShapeJudgeResult:
        mapping_judge = self._endpoint_shape_judge
        if mapping_judge is None:
            return _BorderlineShapeJudgeResult(
                accepted=False,
                reason_code="shape_borderline_without_agent",
                metadata={
                    "shape_guard_reason": "shape_borderline",
                    "shape_guard_outcome": "BORDERLINE",
                    "shape_guard_signals": list(shape_signals),
                    "shape_rejection_subreason": "borderline_no_agent",
                },
            )

        try:
            from src.domain.agents.contexts.mapping_judge_context import (
                MappingJudgeContext,
            )
            from src.domain.agents.contracts.mapping_judge import MappingJudgeCandidate

            contract = mapping_judge.judge(
                MappingJudgeContext(
                    field_key=f"{entity_type}:{endpoint_name}:endpoint_label",
                    field_value_preview=normalized_label[:2000],
                    source_id=research_space_id[:128],
                    source_type="extraction_endpoint_shape",
                    domain_context="kernel",
                    record_metadata={
                        "entity_type": entity_type,
                        "endpoint_name": endpoint_name,
                        "shape_guard_signals": list(shape_signals),
                    },
                    candidates=[
                        MappingJudgeCandidate(
                            variable_id=_ENDPOINT_SHAPE_ACCEPT_VARIABLE_ID,
                            display_name="Accept endpoint label",
                            match_method="exact",
                            similarity_score=1.0,
                            description=(
                                "The label is a concrete entity mention and can be"
                                " safely persisted as a graph node."
                            ),
                            metadata={"action": "accept"},
                        ),
                        MappingJudgeCandidate(
                            variable_id=_ENDPOINT_SHAPE_REJECT_VARIABLE_ID,
                            display_name="Reject endpoint label",
                            match_method="exact",
                            similarity_score=1.0,
                            description=(
                                "The label is sentence-like/noisy and should not be"
                                " persisted as a graph node."
                            ),
                            metadata={"action": "reject"},
                        ),
                    ],
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Endpoint shape borderline judge failed entity_type=%s label=%s: %s",
                entity_type,
                normalized_label,
                exc,
            )
            return _BorderlineShapeJudgeResult(
                accepted=False,
                reason_code="shape_borderline_agent_failed",
                metadata={
                    "shape_guard_reason": "shape_borderline",
                    "shape_guard_outcome": "BORDERLINE",
                    "shape_guard_signals": list(shape_signals),
                    "shape_rejection_subreason": "borderline_agent_failed",
                    "shape_guard_agent_error": type(exc).__name__,
                },
            )

        selected_variable_id = (
            contract.selected_variable_id.strip().upper()
            if isinstance(contract.selected_variable_id, str)
            else ""
        )
        base_metadata: JSONObject = {
            "shape_guard_reason": "shape_borderline",
            "shape_guard_outcome": "BORDERLINE",
            "shape_guard_signals": list(shape_signals),
            "shape_guard_agent_decision": contract.decision,
            "shape_guard_agent_selected_variable_id": selected_variable_id or None,
            "shape_guard_agent_confidence": float(contract.confidence_score),
            "shape_guard_agent_run_id": contract.agent_run_id,
            "shape_guard_agent_rationale": contract.selection_rationale,
        }
        if selected_variable_id == _ENDPOINT_SHAPE_ACCEPT_VARIABLE_ID:
            return _BorderlineShapeJudgeResult(
                accepted=True,
                reason_code="shape_borderline_agent_accept",
                metadata={**base_metadata, "shape_rejection_subreason": None},
            )
        if selected_variable_id == _ENDPOINT_SHAPE_REJECT_VARIABLE_ID:
            return _BorderlineShapeJudgeResult(
                accepted=False,
                reason_code="shape_borderline_agent_reject",
                metadata={
                    **base_metadata,
                    "shape_rejection_subreason": "borderline_agent_reject",
                },
            )
        return _BorderlineShapeJudgeResult(
            accepted=False,
            reason_code="shape_borderline_agent_ambiguous",
            metadata={
                **base_metadata,
                "shape_rejection_subreason": "borderline_agent_ambiguous",
            },
        )

    def _ensure_active_endpoint_entity_type(
        self,
        *,
        entity_type: str,
        endpoint_name: str,
    ) -> bool:
        dictionary = self._dictionary
        if dictionary is None:
            return False

        existing = dictionary.get_entity_type(
            entity_type,
            include_inactive=True,
        )
        if existing is not None:
            if existing.is_active and existing.review_status == "ACTIVE":
                return True
            try:
                dictionary.set_entity_type_review_status(
                    entity_type,
                    review_status="ACTIVE",
                    reviewed_by=_ENDPOINT_ENTITY_TYPE_CREATED_BY,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to activate endpoint entity type=%s: %s",
                    entity_type,
                    exc,
                )
                return False
            else:
                return True

        try:
            dictionary.create_entity_type(
                entity_type=entity_type,
                display_name=entity_type.replace("_", " ").title(),
                description=(
                    "Auto-created entity type for extraction relation endpoint "
                    "persistence."
                ),
                domain_context="general",
                created_by=_ENDPOINT_ENTITY_TYPE_CREATED_BY,
                source_ref=f"extraction_relation_endpoint:{endpoint_name}",
                research_space_settings={"dictionary_agent_creation_policy": "ACTIVE"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to create endpoint entity type=%s: %s",
                entity_type,
                exc,
            )
            return False
        else:
            return True

    def _ensure_concept_identifiers(
        self,
        *,
        entity_id: str,
        entity_type: str,
        label: str,
    ) -> None:
        if self._entities is None:
            return
        concept_key = build_entity_concept_key(entity_type, label)
        if concept_key is not None:
            self._add_internal_identifier(
                entity_id=entity_id,
                namespace="CONCEPT_KEY",
                identifier_value=concept_key,
            )
        family_key = build_concept_family_key(entity_type, label)
        if family_key is not None:
            self._add_internal_identifier(
                entity_id=entity_id,
                namespace="CONCEPT_FAMILY",
                identifier_value=family_key,
            )

    def _add_internal_identifier(
        self,
        *,
        entity_id: str,
        namespace: str,
        identifier_value: str,
    ) -> None:
        if self._entities is None:
            return
        try:
            self._entities.add_identifier(
                entity_id=entity_id,
                namespace=namespace,
                identifier_value=identifier_value,
                sensitivity="INTERNAL",
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            logger.debug(
                "Failed to add %s identifier for entity_id=%s: %s",
                namespace,
                entity_id,
                exc,
            )


__all__ = [
    "EndpointEntityResolutionResult",
    "_RelationEndpointEntityResolutionHelpers",
]
