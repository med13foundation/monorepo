"""Deterministic relation and graph routes for the standalone graph service."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.graph_api._relation_evidence_presenter import (
    load_relation_evidence_presentation,
)
from services.graph_api._relation_subgraph_helpers import (
    collect_candidate_relations,
    limit_relations_to_anchor_component,
    materialize_nodes,
    ordered_node_ids_for_relations,
)
from services.graph_api.auth import (
    get_current_active_user,
    is_graph_service_admin,
)
from services.graph_api.database import get_session
from services.graph_api.dependencies import (
    get_kernel_claim_evidence_service,
    get_kernel_claim_participant_service,
    get_kernel_entity_service,
    get_kernel_relation_claim_service,
    get_kernel_relation_projection_materialization_service,
    get_kernel_relation_service,
    get_space_access_port,
    require_space_role,
    verify_space_membership,
)
from src.application.services.claim_first_metrics import (
    emit_graph_filter_preset_usage,
)
from src.application.services.kernel.kernel_claim_evidence_service import (
    KernelClaimEvidenceService,
)
from src.application.services.kernel.kernel_claim_participant_service import (
    KernelClaimParticipantService,
)
from src.application.services.kernel.kernel_entity_service import KernelEntityService
from src.application.services.kernel.kernel_relation_claim_service import (
    KernelRelationClaimService,
)
from src.application.services.kernel.kernel_relation_projection_materialization_service import (
    KernelRelationProjectionMaterializationService,
)
from src.application.services.kernel.kernel_relation_service import (
    KernelRelationService,
)
from src.domain.entities.research_space_membership import MembershipRole
from src.domain.entities.user import User
from src.domain.ports.space_access_port import SpaceAccessPort
from src.type_definitions.graph_service_contracts import (
    KernelGraphExportResponse,
    KernelGraphSubgraphMeta,
    KernelGraphSubgraphRequest,
    KernelGraphSubgraphResponse,
    KernelRelationCreateRequest,
    KernelRelationCurationUpdateRequest,
    KernelRelationListResponse,
    KernelRelationResponse,
)

router = APIRouter(prefix="/v1/spaces", tags=["relations"])

_CANONICAL_CURATION_STATUSES = frozenset(
    {"APPROVED", "UNDER_REVIEW", "DRAFT", "REJECTED", "RETRACTED"},
)
_CURATION_STATUS_ALIAS: dict[str, str] = {"PENDING_REVIEW": "DRAFT"}
_CLAIM_VALIDATION_STATES = frozenset(
    {
        "ALLOWED",
        "FORBIDDEN",
        "UNDEFINED",
        "INVALID_COMPONENTS",
        "ENDPOINT_UNRESOLVED",
        "SELF_LOOP",
    },
)
_CERTAINTY_BANDS = frozenset({"HIGH", "MEDIUM", "LOW"})
_ClaimValidationState = Literal[
    "ALLOWED",
    "FORBIDDEN",
    "UNDEFINED",
    "INVALID_COMPONENTS",
    "ENDPOINT_UNRESOLVED",
    "SELF_LOOP",
]
_CertaintyBand = Literal["HIGH", "MEDIUM", "LOW"]
_CLAIM_VALIDATION_STATE_MAP: dict[str, _ClaimValidationState] = {
    "ALLOWED": "ALLOWED",
    "FORBIDDEN": "FORBIDDEN",
    "UNDEFINED": "UNDEFINED",
    "INVALID_COMPONENTS": "INVALID_COMPONENTS",
    "ENDPOINT_UNRESOLVED": "ENDPOINT_UNRESOLVED",
    "SELF_LOOP": "SELF_LOOP",
}


def _normalize_filter_values(values: list[str] | None) -> set[str] | None:
    if values is None:
        return None
    normalized = {value.strip().upper() for value in values if value.strip()}
    return normalized or None


def _parse_node_ids_param(node_ids: list[str] | None) -> list[str]:
    if node_ids is None:
        return []
    normalized: list[str] = []
    for raw in node_ids:
        normalized.extend(part.strip() for part in raw.split(",") if part.strip())
    return normalized


def _normalize_curation_status_filter(status_value: str | None) -> str | None:
    if status_value is None:
        return None
    normalized = status_value.strip().upper()
    if not normalized:
        return None
    return _CURATION_STATUS_ALIAS.get(normalized, normalized)


def _normalize_curation_status_filters(
    statuses: list[str] | None,
) -> set[str] | None:
    normalized_values = _normalize_filter_values(statuses)
    if normalized_values is None:
        return None
    normalized = {
        _CURATION_STATUS_ALIAS.get(value, value) for value in normalized_values
    }
    return normalized or None


def _normalize_curation_status_update(status_value: str) -> str:
    normalized = status_value.strip().upper()
    if normalized not in _CANONICAL_CURATION_STATUSES:
        msg = "curation_status must be one of: " + ", ".join(
            sorted(_CANONICAL_CURATION_STATUSES),
        )
        raise ValueError(msg)
    return normalized


def _normalize_claim_validation_state(
    value: str | None,
) -> _ClaimValidationState | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    normalized_state = _CLAIM_VALIDATION_STATE_MAP.get(normalized)
    if normalized_state is None:
        msg = "validation_state must be one of: " + ", ".join(
            sorted(_CLAIM_VALIDATION_STATES),
        )
        raise ValueError(msg)
    return normalized_state


def _normalize_certainty_band(value: str | None) -> _CertaintyBand | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if normalized not in _CERTAINTY_BANDS:
        msg = "certainty_band must be one of: HIGH, MEDIUM, LOW"
        raise ValueError(msg)
    if normalized == "HIGH":
        return "HIGH"
    if normalized == "MEDIUM":
        return "MEDIUM"
    return "LOW"


def _normalize_claim_evidence_sentence_source(
    value: str | None,
) -> Literal["verbatim_span", "artana_generated"] | None:
    if value == "verbatim_span":
        return "verbatim_span"
    if value == "artana_generated":
        return "artana_generated"
    return None


def _normalize_claim_evidence_sentence_confidence(
    value: str | None,
) -> Literal["low", "medium", "high"] | None:
    if value == "low":
        return "low"
    if value == "medium":
        return "medium"
    if value == "high":
        return "high"
    return None


def _manual_relation_claim_text(
    *,
    evidence_summary: str | None,
    evidence_sentence: str | None,
    relation_type: str,
    source_label: str | None,
    target_label: str | None,
) -> str:
    if evidence_sentence is not None and evidence_sentence.strip():
        return evidence_sentence.strip()[:2000]
    if evidence_summary is not None and evidence_summary.strip():
        return evidence_summary.strip()[:2000]
    source_text = source_label.strip() if source_label is not None else ""
    target_text = target_label.strip() if target_label is not None else ""
    if source_text and target_text:
        return f"{source_text} {relation_type} {target_text}"
    if source_text:
        return f"{source_text} {relation_type}"
    if target_text:
        return f"{relation_type} {target_text}"
    return relation_type


@router.get(
    "/{space_id}/relations",
    response_model=KernelRelationListResponse,
    summary="List canonical relations in one graph space",
)
def list_relations(
    space_id: UUID,
    *,
    relation_type: str | None = Query(default=None),
    curation_status: str | None = Query(default=None),
    validation_state: str | None = Query(default=None),
    source_document_id: str | None = Query(default=None),
    certainty_band: str | None = Query(default=None),
    node_query: str | None = Query(default=None),
    node_ids: list[str] | None = Query(
        default=None,
        description="Comma-separated entity IDs to match relation source or target.",
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelRelationListResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    try:
        normalized_curation_status = _normalize_curation_status_filter(
            curation_status,
        )
        normalized_validation_state = _normalize_claim_validation_state(
            validation_state,
        )
        normalized_certainty_band = _normalize_certainty_band(certainty_band)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    parsed_node_ids = _parse_node_ids_param(node_ids)
    relations = relation_service.list_by_research_space(
        str(space_id),
        relation_type=relation_type,
        curation_status=normalized_curation_status,
        validation_state=normalized_validation_state,
        source_document_id=source_document_id,
        certainty_band=normalized_certainty_band,
        node_query=node_query,
        node_ids=parsed_node_ids,
        limit=limit,
        offset=offset,
    )
    total = relation_service.count_by_research_space(
        str(space_id),
        relation_type=relation_type,
        curation_status=normalized_curation_status,
        validation_state=normalized_validation_state,
        source_document_id=source_document_id,
        certainty_band=normalized_certainty_band,
        node_query=node_query,
        node_ids=parsed_node_ids,
    )
    evidence_by_relation_id = load_relation_evidence_presentation(
        session=session,
        relation_ids=[UUID(str(relation.id)) for relation in relations],
    )
    relation_rows: list[KernelRelationResponse] = []
    for relation in relations:
        evidence = evidence_by_relation_id.get(str(relation.id))
        relation_rows.append(
            KernelRelationResponse.from_model(
                relation,
                evidence_summary=evidence.evidence_summary if evidence else None,
                evidence_sentence=evidence.evidence_sentence if evidence else None,
                evidence_sentence_source=(
                    evidence.evidence_sentence_source if evidence else None
                ),
                evidence_sentence_confidence=(
                    evidence.evidence_sentence_confidence if evidence else None
                ),
                evidence_sentence_rationale=(
                    evidence.evidence_sentence_rationale if evidence else None
                ),
                paper_links=evidence.paper_links if evidence else [],
            ),
        )

    return KernelRelationListResponse(
        relations=relation_rows,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/{space_id}/relations",
    response_model=KernelRelationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one canonical relation from a manual support claim",
)
def create_relation(
    space_id: UUID,
    request: KernelRelationCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    claim_participant_service: KernelClaimParticipantService = Depends(
        get_kernel_claim_participant_service,
    ),
    claim_evidence_service: KernelClaimEvidenceService = Depends(
        get_kernel_claim_evidence_service,
    ),
    relation_projection_materialization_service: KernelRelationProjectionMaterializationService = Depends(
        get_kernel_relation_projection_materialization_service,
    ),
    session: Session = Depends(get_session),
) -> KernelRelationResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    if not is_graph_service_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "POST /relations requires graph-service admin access. Create or "
                "resolve claims to materialize canonical relations."
            ),
        )

    try:
        source_entity = entity_service.get_entity(str(request.source_id))
        target_entity = entity_service.get_entity(str(request.target_id))
        if (
            source_entity is None
            or target_entity is None
            or str(source_entity.research_space_id) != str(space_id)
            or str(target_entity.research_space_id) != str(space_id)
        ):
            msg = "Source or target entity not found"
            raise ValueError(msg)

        manual_claim = relation_claim_service.create_claim(
            research_space_id=str(space_id),
            source_document_id=None,
            source_document_ref=request.source_document_ref,
            agent_run_id=None,
            source_type=source_entity.entity_type,
            relation_type=request.relation_type,
            target_type=target_entity.entity_type,
            source_label=source_entity.display_label,
            target_label=target_entity.display_label,
            confidence=request.confidence,
            validation_state="ALLOWED",
            validation_reason="Created via canonical relation API",
            persistability="PERSISTABLE",
            claim_status="RESOLVED",
            polarity="SUPPORT",
            claim_text=_manual_relation_claim_text(
                evidence_summary=request.evidence_summary,
                evidence_sentence=request.evidence_sentence,
                relation_type=request.relation_type,
                source_label=source_entity.display_label,
                target_label=target_entity.display_label,
            ),
            claim_section=None,
            linked_relation_id=None,
            metadata={
                "origin": "manual_relation_api",
                "source_entity_id": str(request.source_id),
                "target_entity_id": str(request.target_id),
                "provenance_id": (
                    str(request.provenance_id)
                    if request.provenance_id is not None
                    else None
                ),
            },
        )
        claim_id = str(manual_claim.id)
        claim_participant_service.create_participant(
            claim_id=claim_id,
            research_space_id=str(space_id),
            role="SUBJECT",
            label=source_entity.display_label,
            entity_id=str(source_entity.id),
            position=0,
            qualifiers={"origin": "manual_relation_api"},
        )
        claim_participant_service.create_participant(
            claim_id=claim_id,
            research_space_id=str(space_id),
            role="OBJECT",
            label=target_entity.display_label,
            entity_id=str(target_entity.id),
            position=1,
            qualifiers={"origin": "manual_relation_api"},
        )
        if (
            request.evidence_summary is not None
            or request.evidence_sentence is not None
            or request.provenance_id is not None
            or request.source_document_ref is not None
        ):
            claim_evidence_service.create_evidence(
                claim_id=claim_id,
                source_document_id=None,
                source_document_ref=request.source_document_ref,
                agent_run_id=None,
                sentence=request.evidence_sentence,
                sentence_source=_normalize_claim_evidence_sentence_source(
                    request.evidence_sentence_source,
                ),
                sentence_confidence=_normalize_claim_evidence_sentence_confidence(
                    request.evidence_sentence_confidence,
                ),
                sentence_rationale=request.evidence_sentence_rationale,
                figure_reference=None,
                table_reference=None,
                confidence=request.confidence,
                metadata={
                    "origin": "manual_relation_api",
                    "evidence_summary": request.evidence_summary,
                    "evidence_tier": request.evidence_tier or "COMPUTATIONAL",
                    "provenance_id": (
                        str(request.provenance_id)
                        if request.provenance_id is not None
                        else None
                    ),
                },
            )
        materialized = (
            relation_projection_materialization_service.materialize_support_claim(
                claim_id=claim_id,
                research_space_id=str(space_id),
                projection_origin="MANUAL_RELATION",
                reviewed_by=str(current_user.id),
            )
        )
        relation = materialized.relation
        if relation is None:
            msg = "Manual relation claim did not materialize a canonical relation"
            raise ValueError(msg)
        session.commit()
        return KernelRelationResponse.from_model(relation)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Relation write conflicts with dictionary constraints, "
                "research-space isolation, or required evidence checks"
            ),
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create relation: {exc!s}",
        ) from exc


@router.put(
    "/{space_id}/relations/{relation_id}",
    response_model=KernelRelationResponse,
    summary="Update one relation curation status",
)
def update_relation_curation_status(
    space_id: UUID,
    relation_id: UUID,
    request: KernelRelationCurationUpdateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelRelationResponse:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.CURATOR,
    )

    existing = relation_service.get_relation(str(relation_id))
    if existing is None or str(existing.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relation not found",
        )

    try:
        normalized_status = _normalize_curation_status_update(request.curation_status)
        updated = relation_service.update_curation_status(
            str(relation_id),
            curation_status=normalized_status,
            reviewed_by=str(current_user.id),
        )
        session.commit()
        return KernelRelationResponse.from_model(updated)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update relation: {exc!s}",
        ) from exc


@router.post(
    "/{space_id}/graph/subgraph",
    response_model=KernelGraphSubgraphResponse,
    summary="Retrieve a bounded graph subgraph",
)
def get_subgraph(
    space_id: UUID,
    request: KernelGraphSubgraphRequest,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelGraphSubgraphResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    relation_types = _normalize_filter_values(request.relation_types)
    curation_statuses = _normalize_curation_status_filters(request.curation_statuses)
    emit_graph_filter_preset_usage(
        endpoint="subgraph",
        curation_statuses=(
            sorted(curation_statuses) if curation_statuses is not None else None
        ),
    )
    seed_entity_ids = [str(seed_id) for seed_id in request.seed_entity_ids]
    mode = request.mode
    space_id_str = str(space_id)

    if mode == "starter" and seed_entity_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="seed_entity_ids must be empty when mode='starter'.",
        )
    if mode == "seeded" and not seed_entity_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="seed_entity_ids is required when mode='seeded'.",
        )

    try:
        candidate_relations = collect_candidate_relations(
            mode=mode,
            space_id=space_id_str,
            request=request,
            relation_service=relation_service,
            relation_types=relation_types,
            curation_statuses=curation_statuses,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if mode == "starter":
        candidate_relations = limit_relations_to_anchor_component(
            relations=candidate_relations,
            preferred_seed_entity_ids=seed_entity_ids,
        )

    pre_cap_node_ids = set(seed_entity_ids)
    for relation in candidate_relations:
        pre_cap_node_ids.add(str(relation.source_id))
        pre_cap_node_ids.add(str(relation.target_id))
    pre_cap_edge_count = len(candidate_relations)
    pre_cap_node_count = len(pre_cap_node_ids)

    bounded_relations = candidate_relations[: request.max_edges]
    ordered_node_ids = ordered_node_ids_for_relations(
        bounded_relations,
        seed_entity_ids=seed_entity_ids,
    )
    bounded_node_ids = ordered_node_ids[: request.max_nodes]
    bounded_node_id_set = set(bounded_node_ids)

    final_relations = [
        relation
        for relation in bounded_relations
        if str(relation.source_id) in bounded_node_id_set
        and str(relation.target_id) in bounded_node_id_set
    ]
    final_node_ids = ordered_node_ids_for_relations(
        final_relations,
        seed_entity_ids=seed_entity_ids,
    )[: request.max_nodes]

    nodes = materialize_nodes(
        entity_ids=final_node_ids,
        space_id=space_id_str,
        entity_service=entity_service,
    )
    edges = [
        KernelRelationResponse.from_model(relation) for relation in final_relations
    ]
    return KernelGraphSubgraphResponse(
        nodes=nodes,
        edges=edges,
        meta=KernelGraphSubgraphMeta(
            mode=mode,
            seed_entity_ids=request.seed_entity_ids,
            requested_depth=request.depth,
            requested_top_k=request.top_k,
            pre_cap_node_count=pre_cap_node_count,
            pre_cap_edge_count=pre_cap_edge_count,
            truncated_nodes=len(nodes) < pre_cap_node_count,
            truncated_edges=len(edges) < pre_cap_edge_count,
        ),
    )


@router.get(
    "/{space_id}/graph/neighborhood/{entity_id}",
    response_model=KernelGraphExportResponse,
    summary="Get one entity neighborhood",
)
def get_neighborhood(
    space_id: UUID,
    entity_id: UUID,
    *,
    depth: int = Query(default=1, ge=1, le=3),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelGraphExportResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    try:
        relations = relation_service.get_neighborhood_in_space(
            str(space_id),
            str(entity_id),
            depth=depth,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    entity_ids: set[str] = {str(entity_id)}
    for relation in relations:
        entity_ids.add(str(relation.source_id))
        entity_ids.add(str(relation.target_id))

    nodes = materialize_nodes(
        entity_ids=sorted(entity_ids),
        space_id=str(space_id),
        entity_service=entity_service,
    )
    return KernelGraphExportResponse(
        nodes=nodes,
        edges=[KernelRelationResponse.from_model(relation) for relation in relations],
    )


__all__ = [
    "create_relation",
    "get_neighborhood",
    "get_subgraph",
    "list_relations",
    "router",
    "update_relation_curation_status",
]
