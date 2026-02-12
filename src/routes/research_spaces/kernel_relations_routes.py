"""Kernel relation + graph endpoints scoped to research spaces."""

from __future__ import annotations

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
