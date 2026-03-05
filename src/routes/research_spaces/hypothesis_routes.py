"""Hypothesis workflow endpoints scoped to research spaces."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.application.agents.services.hypothesis_generation_service import (
    HypothesisGenerationService,
)
from src.application.services.claim_first_metrics import increment_metric
from src.application.services.kernel.kernel_claim_participant_service import (
    KernelClaimParticipantService,
)
from src.database.session import get_session
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    require_researcher_role,
    verify_space_membership,
)
from src.routes.research_spaces.hypothesis_schemas import (
    CreateManualHypothesisRequest,
    GenerateHypothesesRequest,
    GenerateHypothesesResponse,
    HypothesisListResponse,
    HypothesisResponse,
)
from src.routes.research_spaces.kernel_dependencies import (
    get_concept_service,
    get_hypothesis_generation_service,
    get_kernel_claim_participant_service,
    get_kernel_entity_service,
    get_kernel_relation_claim_service,
)
from src.type_definitions.common import JSONObject

from .router import (
    HTTP_400_BAD_REQUEST,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)

if TYPE_CHECKING:
    from src.application.services.kernel import (
        KernelEntityService,
        KernelRelationClaimService,
    )
    from src.application.services.membership_management_service import (
        MembershipManagementService,
    )
    from src.domain.entities.user import User
    from src.domain.ports import ConceptPort

_HYPOTHESIS_GENERATION_ENABLED_ENV = "MED13_ENABLE_HYPOTHESIS_GENERATION"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _is_hypothesis_generation_enabled() -> bool:
    raw_value = os.getenv(_HYPOTHESIS_GENERATION_ENABLED_ENV, "0")
    return raw_value.strip().lower() in _TRUE_VALUES


def get_hypothesis_generation_service_provider(
    session: Session = Depends(get_session),
) -> Callable[[], HypothesisGenerationService]:
    """Return a lazy service provider so feature-flag checks can short-circuit early."""

    def _provider() -> HypothesisGenerationService:
        return get_hypothesis_generation_service(session)

    return _provider


@research_spaces_router.get(
    "/{space_id}/hypotheses",
    response_model=HypothesisListResponse,
    summary="List hypothesis claims in a research space",
)
def list_hypotheses(
    space_id: UUID,
    *,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    session: Session = Depends(get_session),
) -> HypothesisListResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    hypotheses = relation_claim_service.list_by_research_space(
        str(space_id),
        polarity="HYPOTHESIS",
        limit=limit,
        offset=offset,
    )
    total = relation_claim_service.count_by_research_space(
        str(space_id),
        polarity="HYPOTHESIS",
    )

    return HypothesisListResponse(
        hypotheses=[HypothesisResponse.from_claim(claim) for claim in hypotheses],
        total=total,
        offset=offset,
        limit=limit,
    )


@research_spaces_router.post(
    "/{space_id}/hypotheses/manual",
    response_model=HypothesisResponse,
    summary="Log one manual hypothesis",
)
def create_manual_hypothesis(  # noqa: PLR0912
    space_id: UUID,
    request: CreateManualHypothesisRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    concept_service: ConceptPort = Depends(get_concept_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    claim_participant_service: KernelClaimParticipantService = Depends(
        get_kernel_claim_participant_service,
    ),
    session: Session = Depends(get_session),
) -> HypothesisResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    try:
        normalized_statement = request.statement.strip()
        normalized_rationale = request.rationale.strip()
        if not normalized_statement:
            msg = "statement is required"
            raise ValueError(msg)
        if not normalized_rationale:
            msg = "rationale is required"
            raise ValueError(msg)

        seed_entity_ids = _normalize_seed_entity_ids(request.seed_entity_ids)
        (
            participant_seed_entity_ids,
            unresolved_seed_entity_ids,
        ) = _resolve_seed_entities_for_participants(
            seed_entity_ids=seed_entity_ids,
            space_id=space_id,
            entity_service=entity_service,
        )
        normalized_source_type = request.source_type.strip()

        concept_set_id = _resolve_hypothesis_concept_set_id(
            concept_service=concept_service,
            space_id=space_id,
        )
        concept_decision_id: str | None = None
        concept_decision_error: str | None = None

        decision_payload: JSONObject = {
            "workflow": "hypothesis",
            "statement": normalized_statement,
            "rationale": normalized_rationale,
            "seed_entity_ids": seed_entity_ids,
            "participant_seed_entity_ids": participant_seed_entity_ids,
            "source_type": normalized_source_type,
        }
        if unresolved_seed_entity_ids:
            decision_payload["unresolved_seed_entity_ids"] = unresolved_seed_entity_ids
        if concept_set_id is not None:
            try:
                concept_decision = concept_service.propose_decision(
                    research_space_id=str(space_id),
                    decision_type="CREATE",
                    proposed_by=f"manual:{current_user.id}",
                    decision_payload=decision_payload,
                    evidence_payload={"origin": "manual"},
                    confidence=None,
                    rationale=normalized_rationale,
                    concept_set_id=concept_set_id,
                )
                concept_decision_id = concept_decision.id
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                concept_decision_error = str(exc)
        else:
            concept_decision_error = "missing_concept_set"

        metadata_payload: JSONObject = {
            "workflow": "hypothesis",
            "origin": "manual",
            "statement": normalized_statement,
            "rationale": normalized_rationale,
            "seed_entity_ids": participant_seed_entity_ids,
            "requested_seed_entity_ids": seed_entity_ids,
            "source_type": normalized_source_type,
            "actor_user_id": str(current_user.id),
        }
        if unresolved_seed_entity_ids:
            metadata_payload["unresolved_seed_entity_ids"] = unresolved_seed_entity_ids
            metadata_payload["manual_warnings"] = [
                "some_seed_entity_ids_not_found_in_space",
            ]
        if concept_decision_id is not None:
            metadata_payload["concept_decision_id"] = concept_decision_id
        if concept_decision_error is not None:
            metadata_payload["concept_decision_error"] = concept_decision_error

        claim = relation_claim_service.create_hypothesis_claim(
            research_space_id=str(space_id),
            source_document_id=None,
            agent_run_id=None,
            source_type="HYPOTHESIS",
            relation_type="PROPOSES",
            target_type="HYPOTHESIS",
            source_label="Manual hypothesis",
            target_label=None,
            confidence=0.5,
            validation_state="UNDEFINED",
            validation_reason="manual_hypothesis_submission",
            persistability="NON_PERSISTABLE",
            claim_text=normalized_statement,
            metadata=metadata_payload,
            claim_status="OPEN",
        )
        if participant_seed_entity_ids:
            for index, seed_entity_id in enumerate(participant_seed_entity_ids):
                claim_participant_service.create_participant(
                    claim_id=str(claim.id),
                    research_space_id=str(space_id),
                    role="SUBJECT",
                    label=None,
                    entity_id=seed_entity_id,
                    position=index,
                    qualifiers=None,
                )
        else:
            claim_participant_service.create_participant(
                claim_id=str(claim.id),
                research_space_id=str(space_id),
                role="SUBJECT",
                label=normalized_statement,
                entity_id=None,
                position=0,
                qualifiers=None,
            )

        increment_metric(
            "hypotheses_manual_created_total",
            tags={"research_space_id": str(space_id)},
        )

        session.commit()
        return HypothesisResponse.from_claim(claim)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Manual hypothesis creation failed: {exc!s}",
        ) from exc


@research_spaces_router.post(
    "/{space_id}/hypotheses/generate",
    response_model=GenerateHypothesesResponse,
    summary="Auto-generate hypotheses from graph exploration",
)
async def generate_hypotheses(
    space_id: UUID,
    request: GenerateHypothesesRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    hypothesis_generation_service_provider: Callable[
        [],
        HypothesisGenerationService,
    ] = Depends(
        get_hypothesis_generation_service_provider,
    ),
    session: Session = Depends(get_session),
) -> GenerateHypothesesResponse:
    if not _is_hypothesis_generation_enabled():
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail={
                "code": "FEATURE_DISABLED",
                "message": (
                    "Hypothesis generation is disabled. Enable "
                    f"{_HYPOTHESIS_GENERATION_ENABLED_ENV}=1 to use this endpoint."
                ),
            },
        )

    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    try:
        hypothesis_generation_service = hypothesis_generation_service_provider()
        result = await hypothesis_generation_service.generate_hypotheses(
            research_space_id=str(space_id),
            seed_entity_ids=request.seed_entity_ids,
            source_type=request.source_type,
            relation_types=request.relation_types,
            max_depth=request.max_depth,
            max_hypotheses=request.max_hypotheses,
            model_id=request.model_id,
        )
        session.commit()
        return GenerateHypothesesResponse(
            run_id=result.run_id,
            requested_seed_count=result.requested_seed_count,
            used_seed_count=result.used_seed_count,
            candidates_seen=result.candidates_seen,
            created_count=result.created_count,
            deduped_count=result.deduped_count,
            errors=list(result.errors),
            hypotheses=[
                HypothesisResponse.from_claim(claim) for claim in result.hypotheses
            ],
        )
    except ValueError as exc:
        session.rollback()
        increment_metric(
            "hypotheses_generation_failed_total",
            tags={"research_space_id": str(space_id)},
        )
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        increment_metric(
            "hypotheses_generation_failed_total",
            tags={"research_space_id": str(space_id)},
        )
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Hypothesis generation failed: {exc!s}",
        ) from exc


def _normalize_seed_entity_ids(seed_entity_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in seed_entity_ids:
        trimmed = value.strip()
        if not trimmed:
            continue
        canonical = str(UUID(trimmed))
        if canonical in seen:
            continue
        seen.add(canonical)
        normalized.append(canonical)
    return normalized


def _resolve_hypothesis_concept_set_id(
    *,
    concept_service: ConceptPort,
    space_id: UUID,
) -> str | None:
    existing_sets = concept_service.list_concept_sets(
        research_space_id=str(space_id),
        include_inactive=True,
    )
    if existing_sets:
        return existing_sets[0].id
    return None


def _resolve_seed_entities_for_participants(
    *,
    seed_entity_ids: list[str],
    space_id: UUID,
    entity_service: KernelEntityService,
) -> tuple[list[str], list[str]]:
    resolved: list[str] = []
    unresolved: list[str] = []
    for entity_id in seed_entity_ids:
        entity = entity_service.get_entity(entity_id)
        if entity is None:
            unresolved.append(entity_id)
            continue
        if str(entity.research_space_id) != str(space_id):
            unresolved.append(entity_id)
            continue
        resolved.append(str(entity.id))
    return resolved, unresolved


__all__ = [
    "create_manual_hypothesis",
    "generate_hypotheses",
    "get_hypothesis_generation_service_provider",
    "list_hypotheses",
]
