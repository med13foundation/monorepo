"""Entity routes for the standalone graph service."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.graph_api.auth import get_current_active_user
from services.graph_api.database import get_session
from services.graph_api.dependencies import (
    get_kernel_entity_service,
    get_space_access_port,
    require_space_role,
    verify_space_membership,
)
from src.application.services.kernel.kernel_entity_service import KernelEntityService
from src.domain.entities.research_space_membership import MembershipRole
from src.domain.entities.user import User
from src.domain.ports.space_access_port import SpaceAccessPort
from src.type_definitions.graph_service_contracts import (
    KernelEntityCreateRequest,
    KernelEntityListResponse,
    KernelEntityResponse,
    KernelEntityUpdateRequest,
    KernelEntityUpsertResponse,
)

router = APIRouter(prefix="/v1/spaces", tags=["entities"])


def _parse_entity_ids_param(
    entity_ids: list[str] | None,
) -> tuple[list[str], list[str]]:
    if entity_ids is None:
        return [], []

    normalized: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []
    invalid_seen: set[str] = set()
    for raw in entity_ids:
        for token in raw.split(","):
            trimmed = token.strip()
            if not trimmed:
                continue
            try:
                normalized_id = str(UUID(trimmed))
            except ValueError:
                if trimmed not in invalid_seen:
                    invalid_seen.add(trimmed)
                    invalid.append(trimmed)
                continue
            if normalized_id in seen:
                continue
            seen.add(normalized_id)
            normalized.append(normalized_id)

    return normalized, invalid


@router.get(
    "/{space_id}/entities",
    response_model=KernelEntityListResponse,
    summary="List entities in one graph space",
)
def list_entities(
    space_id: UUID,
    *,
    entity_type: str | None = Query(default=None, alias="type"),
    q: str | None = Query(default=None),
    ids: list[str] | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> KernelEntityListResponse:
    """List entities in one graph space."""
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    entity_ids, invalid_entity_ids = _parse_entity_ids_param(ids)
    if invalid_entity_ids:
        invalid_preview = ", ".join(invalid_entity_ids[:3])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity id(s): {invalid_preview}",
        )

    if ids is not None:
        paged_ids = entity_ids[offset : offset + limit]
        entities = []
        for entity_id in paged_ids:
            entity = entity_service.get_entity(entity_id)
            if entity is None or str(entity.research_space_id) != str(space_id):
                continue
            entities.append(entity)
    elif q:
        batch = entity_service.search(
            str(space_id),
            q,
            entity_type=entity_type,
            limit=offset + limit,
        )
        entities = batch[offset : offset + limit]
    else:
        if entity_type is None or not entity_type.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide either 'type' or 'q' when listing entities.",
            )
        entities = entity_service.list_by_type(
            str(space_id),
            entity_type,
            limit=limit,
            offset=offset,
        )

    return KernelEntityListResponse(
        entities=[KernelEntityResponse.from_model(entity) for entity in entities],
        total=len(entities),
        offset=offset,
        limit=limit,
    )


@router.post(
    "/{space_id}/entities",
    response_model=KernelEntityUpsertResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or resolve one entity",
)
def create_entity(
    space_id: UUID,
    request: KernelEntityCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> KernelEntityUpsertResponse:
    """Create or resolve one graph entity."""
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )

    try:
        entity, created = entity_service.create_or_resolve(
            research_space_id=str(space_id),
            entity_type=request.entity_type,
            identifiers=request.identifiers or None,
            display_label=request.display_label,
            metadata=request.metadata,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Entity identifiers already exist for another entity.",
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
            detail=f"Failed to create entity: {exc!s}",
        ) from exc

    return KernelEntityUpsertResponse(
        entity=KernelEntityResponse.from_model(entity),
        created=created,
    )


@router.get(
    "/{space_id}/entities/{entity_id}",
    response_model=KernelEntityResponse,
    summary="Get one entity",
)
def get_entity(
    space_id: UUID,
    entity_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> KernelEntityResponse:
    """Get one entity in one graph space."""
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    entity = entity_service.get_entity(str(entity_id))
    if entity is None or str(entity.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )
    return KernelEntityResponse.from_model(entity)


@router.put(
    "/{space_id}/entities/{entity_id}",
    response_model=KernelEntityResponse,
    summary="Update one entity",
)
def update_entity(
    space_id: UUID,
    entity_id: UUID,
    request: KernelEntityUpdateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> KernelEntityResponse:
    """Update one entity in one graph space."""
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )

    entity = entity_service.get_entity(str(entity_id))
    if entity is None or str(entity.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )

    try:
        updated_entity = entity
        if request.display_label is not None or request.metadata is not None:
            maybe_updated = entity_service.update_entity(
                str(entity_id),
                display_label=request.display_label,
                metadata=request.metadata,
            )
            if maybe_updated is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Entity not found",
                )
            updated_entity = maybe_updated

        if request.identifiers:
            for namespace, value in request.identifiers.items():
                entity_service.add_identifier(
                    entity_id=str(entity_id),
                    namespace=namespace,
                    identifier_value=value,
                )

        session.commit()
        return KernelEntityResponse.from_model(updated_entity)
    except HTTPException:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Identifier already exists",
        ) from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update entity: {exc!s}",
        ) from exc


@router.delete(
    "/{space_id}/entities/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one entity",
)
def delete_entity(
    space_id: UUID,
    entity_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> None:
    """Delete one entity in one graph space."""
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )

    entity = entity_service.get_entity(str(entity_id))
    if entity is None or str(entity.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )

    if not entity_service.delete_entity(str(entity_id)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )
    session.commit()


__all__ = [
    "router",
    "create_entity",
    "delete_entity",
    "get_entity",
    "list_entities",
    "update_entity",
]
