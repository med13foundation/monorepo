"""Kernel relation + graph endpoints scoped to research spaces."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.application.services.kernel.kernel_entity_service import KernelEntityService
from src.application.services.kernel.kernel_relation_service import (
    KernelRelationService,
)
from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.database.session import get_session
from src.domain.entities.kernel.relations import KernelRelation
from src.domain.entities.user import User
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    require_curator_role,
    require_researcher_role,
    verify_space_membership,
)
from src.routes.research_spaces.kernel_dependencies import (
    get_kernel_entity_service,
    get_kernel_relation_service,
)
from src.routes.research_spaces.kernel_schemas import (
    KernelEntityResponse,
    KernelGraphExportResponse,
    KernelGraphSubgraphMeta,
    KernelGraphSubgraphRequest,
    KernelGraphSubgraphResponse,
    KernelRelationCreateRequest,
    KernelRelationCurationUpdateRequest,
    KernelRelationListResponse,
    KernelRelationResponse,
)

from .router import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)

_CURATION_STATUS_PRIORITY: dict[str, int] = {
    "APPROVED": 5,
    "UNDER_REVIEW": 4,
    "DRAFT": 3,
    "REJECTED": 2,
    "RETRACTED": 1,
}
_STARTER_FETCH_MULTIPLIER = 6


def _normalize_filter_values(values: list[str] | None) -> set[str] | None:
    if values is None:
        return None
    normalized = {value.strip().upper() for value in values if value.strip()}
    return normalized or None


def _status_priority(status: str) -> int:
    return _CURATION_STATUS_PRIORITY.get(status.strip().upper(), 0)


def _sort_relations_for_subgraph(
    relations: Iterable[KernelRelation],
) -> list[KernelRelation]:
    return sorted(
        relations,
        key=lambda relation: (
            _status_priority(str(relation.curation_status)),
            relation.updated_at,
        ),
        reverse=True,
    )


def _filter_relations(
    relations: Iterable[KernelRelation],
    *,
    relation_types: set[str] | None,
    curation_statuses: set[str] | None,
) -> list[KernelRelation]:
    filtered: list[KernelRelation] = []
    for relation in relations:
        relation_type_normalized = str(relation.relation_type).strip().upper()
        curation_status_normalized = str(relation.curation_status).strip().upper()
        if (
            relation_types is not None
            and relation_type_normalized not in relation_types
        ):
            continue
        if (
            curation_statuses is not None
            and curation_status_normalized not in curation_statuses
        ):
            continue
        filtered.append(relation)
    return filtered


def _ordered_node_ids_for_relations(
    relations: Iterable[KernelRelation],
    *,
    seed_entity_ids: list[str],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for seed_id in seed_entity_ids:
        if seed_id not in seen:
            seen.add(seed_id)
            ordered.append(seed_id)
    for relation in relations:
        for entity_id in (str(relation.source_id), str(relation.target_id)):
            if entity_id in seen:
                continue
            seen.add(entity_id)
            ordered.append(entity_id)
    return ordered


def _collect_candidate_relations(
    *,
    mode: Literal["starter", "seeded"],
    space_id: str,
    request: KernelGraphSubgraphRequest,
    relation_service: KernelRelationService,
    relation_types: set[str] | None,
    curation_statuses: set[str] | None,
) -> list[KernelRelation]:
    if mode == "starter":
        fetch_limit = max(
            request.max_edges * _STARTER_FETCH_MULTIPLIER,
            request.top_k * _STARTER_FETCH_MULTIPLIER,
            200,
        )
        relations = relation_service.list_by_research_space(
            space_id,
            limit=fetch_limit,
            offset=0,
        )
        filtered = _filter_relations(
            relations,
            relation_types=relation_types,
            curation_statuses=curation_statuses,
        )
        return _sort_relations_for_subgraph(filtered)

    deduped: dict[str, KernelRelation] = {}
    for seed_entity_id in request.seed_entity_ids:
        seed_relations = relation_service.get_neighborhood_in_space(
            space_id,
            str(seed_entity_id),
            depth=request.depth,
            relation_types=list(relation_types) if relation_types is not None else None,
            limit=request.top_k,
        )
        filtered_seed_relations = _filter_relations(
            seed_relations,
            relation_types=relation_types,
            curation_statuses=curation_statuses,
        )
        for relation in _sort_relations_for_subgraph(filtered_seed_relations)[
            : request.top_k
        ]:
            deduped[str(relation.id)] = relation
    return _sort_relations_for_subgraph(deduped.values())


def _materialize_nodes(
    *,
    entity_ids: list[str],
    space_id: str,
    entity_service: KernelEntityService,
) -> list[KernelEntityResponse]:
    nodes: list[KernelEntityResponse] = []
    for entity_id in entity_ids:
        entity = entity_service.get_entity(entity_id)
        if entity is None:
            continue
        if str(entity.research_space_id) != space_id:
            continue
        nodes.append(KernelEntityResponse.from_model(entity))
    return nodes


@research_spaces_router.get(
    "/{space_id}/relations",
    response_model=KernelRelationListResponse,
    summary="List kernel relations",
)
def list_kernel_relations(
    space_id: UUID,
    *,
    relation_type: str | None = Query(None),
    curation_status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelRelationListResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    relations = relation_service.list_by_research_space(
        str(space_id),
        relation_type=relation_type,
        curation_status=curation_status,
        limit=limit,
        offset=offset,
    )

    return KernelRelationListResponse(
        relations=[KernelRelationResponse.from_model(r) for r in relations],
        total=len(relations),
        offset=offset,
        limit=limit,
    )


@research_spaces_router.post(
    "/{space_id}/relations",
    response_model=KernelRelationResponse,
    summary="Create kernel relation",
    status_code=HTTP_201_CREATED,
)
def create_kernel_relation(
    space_id: UUID,
    request: KernelRelationCreateRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelRelationResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    try:
        relation = relation_service.create_relation(
            research_space_id=str(space_id),
            source_id=str(request.source_id),
            relation_type=request.relation_type,
            target_id=str(request.target_id),
            confidence=request.confidence,
            evidence_summary=request.evidence_summary,
            evidence_tier=request.evidence_tier,
            provenance_id=str(request.provenance_id) if request.provenance_id else None,
        )
        session.commit()
        return KernelRelationResponse.from_model(relation)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create relation: {e!s}",
        ) from e


@research_spaces_router.put(
    "/{space_id}/relations/{relation_id}",
    response_model=KernelRelationResponse,
    summary="Update relation curation status",
)
def update_relation_curation_status(
    space_id: UUID,
    relation_id: UUID,
    request: KernelRelationCurationUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelRelationResponse:
    require_curator_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    existing = relation_service.get_relation(str(relation_id))
    if existing is None or str(existing.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Relation not found",
        )

    try:
        updated = relation_service.update_curation_status(
            str(relation_id),
            curation_status=request.curation_status,
            reviewed_by=str(current_user.id),
        )
        session.commit()
        return KernelRelationResponse.from_model(updated)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update relation: {e!s}",
        ) from e


@research_spaces_router.get(
    "/{space_id}/graph/export",
    response_model=KernelGraphExportResponse,
    summary="Export knowledge graph",
)
def export_kernel_graph(
    space_id: UUID,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelGraphExportResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    relations = relation_service.list_by_research_space(str(space_id))
    entity_ids: set[str] = set()
    for rel in relations:
        entity_ids.add(str(rel.source_id))
        entity_ids.add(str(rel.target_id))

    nodes: list[KernelEntityResponse] = []
    for entity_id in entity_ids:
        entity = entity_service.get_entity(entity_id)
        if entity is None:
            continue
        if str(entity.research_space_id) != str(space_id):
            continue
        nodes.append(KernelEntityResponse.from_model(entity))

    return KernelGraphExportResponse(
        nodes=nodes,
        edges=[KernelRelationResponse.from_model(r) for r in relations],
    )


@research_spaces_router.post(
    "/{space_id}/graph/subgraph",
    response_model=KernelGraphSubgraphResponse,
    summary="Retrieve bounded subgraph for interactive knowledge graph rendering",
)
def get_kernel_subgraph(
    space_id: UUID,
    request: KernelGraphSubgraphRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelGraphSubgraphResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    relation_types = _normalize_filter_values(request.relation_types)
    curation_statuses = _normalize_filter_values(request.curation_statuses)
    seed_entity_ids = [str(seed_id) for seed_id in request.seed_entity_ids]
    mode = request.mode
    space_id_str = str(space_id)

    if mode == "starter" and seed_entity_ids:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="seed_entity_ids must be empty when mode='starter'.",
        )
    if mode == "seeded" and not seed_entity_ids:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="seed_entity_ids is required when mode='seeded'.",
        )

    try:
        candidate_relations = _collect_candidate_relations(
            mode=mode,
            space_id=space_id_str,
            request=request,
            relation_service=relation_service,
            relation_types=relation_types,
            curation_statuses=curation_statuses,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    pre_cap_node_ids = set(seed_entity_ids)
    for relation in candidate_relations:
        pre_cap_node_ids.add(str(relation.source_id))
        pre_cap_node_ids.add(str(relation.target_id))
    pre_cap_edge_count = len(candidate_relations)
    pre_cap_node_count = len(pre_cap_node_ids)

    bounded_relations = candidate_relations[: request.max_edges]

    ordered_node_ids = _ordered_node_ids_for_relations(
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

    final_node_ids = _ordered_node_ids_for_relations(
        final_relations,
        seed_entity_ids=seed_entity_ids,
    )
    final_node_ids = final_node_ids[: request.max_nodes]

    nodes = _materialize_nodes(
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


@research_spaces_router.get(
    "/{space_id}/graph/neighborhood/{entity_id}",
    response_model=KernelGraphExportResponse,
    summary="Get entity neighborhood subgraph",
)
def get_kernel_neighborhood(
    space_id: UUID,
    entity_id: UUID,
    *,
    depth: int = Query(1, ge=1, le=3),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelGraphExportResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    try:
        relations = relation_service.get_neighborhood_in_space(
            str(space_id),
            str(entity_id),
            depth=depth,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    entity_ids: set[str] = {str(entity_id)}
    for rel in relations:
        entity_ids.add(str(rel.source_id))
        entity_ids.add(str(rel.target_id))

    nodes: list[KernelEntityResponse] = []
    for node_id in entity_ids:
        entity = entity_service.get_entity(node_id)
        if entity is None or str(entity.research_space_id) != str(space_id):
            continue
        nodes.append(KernelEntityResponse.from_model(entity))

    return KernelGraphExportResponse(
        nodes=nodes,
        edges=[KernelRelationResponse.from_model(r) for r in relations],
    )
