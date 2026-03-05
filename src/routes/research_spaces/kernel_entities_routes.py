"""Kernel entity endpoints scoped to research spaces."""

from __future__ import annotations

import os
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.application.services.kernel.hybrid_graph_errors import EmbeddingNotReadyError
from src.application.services.kernel.kernel_entity_service import KernelEntityService
from src.application.services.kernel.kernel_entity_similarity_service import (
    KernelEntitySimilarityService,
)
from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    require_researcher_role,
    verify_space_membership,
)
from src.routes.research_spaces.kernel_dependencies import (
    get_kernel_entity_service,
    get_kernel_entity_similarity_service,
)
from src.routes.research_spaces.kernel_schemas import (
    KernelEntityCreateRequest,
    KernelEntityEmbeddingRefreshRequest,
    KernelEntityEmbeddingRefreshResponse,
    KernelEntityListResponse,
    KernelEntityResponse,
    KernelEntitySimilarityListResponse,
    KernelEntitySimilarityResponse,
    KernelEntitySimilarityScoreBreakdownResponse,
    KernelEntityUpdateRequest,
    KernelEntityUpsertResponse,
)

from .router import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)

_ENTITY_EMBEDDINGS_ENABLED_ENV = "MED13_ENABLE_ENTITY_EMBEDDINGS"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _is_entity_embeddings_enabled() -> bool:
    raw_value = os.getenv(_ENTITY_EMBEDDINGS_ENABLED_ENV, "0")
    return raw_value.strip().lower() in _TRUE_VALUES


def _feature_disabled_error(flag_name: str) -> HTTPException:
    return HTTPException(
        status_code=HTTP_400_BAD_REQUEST,
        detail={
            "code": "FEATURE_DISABLED",
            "message": (
                "This endpoint is disabled. "
                f"Enable {flag_name}=1 to use hybrid graph embeddings."
            ),
        },
    )


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


@research_spaces_router.get(
    "/{space_id}/entities",
    response_model=KernelEntityListResponse,
    summary="List kernel entities",
    description="List entities in a research space (optionally filtered).",
)
def list_kernel_entities(
    space_id: UUID,
    *,
    entity_type: str | None = Query(
        None,
        alias="type",
        description="Filter by entity type, e.g. GENE, VARIANT",
    ),
    q: str | None = Query(None, description="Search query on display label"),
    ids: list[str] | None = Query(
        None,
        description="Comma-separated entity IDs to fetch directly.",
    ),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> KernelEntityListResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    entity_ids, invalid_entity_ids = _parse_entity_ids_param(ids)
    if invalid_entity_ids:
        invalid_preview = ", ".join(invalid_entity_ids[:3])
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity id(s): {invalid_preview}",
        )

    if ids is not None:
        paged_ids = entity_ids[offset : offset + limit]
        entities = []
        for entity_id in paged_ids:
            entity = service.get_entity(entity_id)
            if entity is None:
                continue
            if str(entity.research_space_id) != str(space_id):
                continue
            entities.append(entity)
    elif q:
        # Repository search doesn't support offset directly; fetch offset+limit and slice.
        batch = service.search(
            str(space_id),
            q,
            entity_type=entity_type,
            limit=offset + limit,
        )
        entities = batch[offset : offset + limit]
    else:
        if entity_type is None or not entity_type.strip():
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="Provide either 'type' or 'q' when listing entities.",
            )
        entities = service.list_by_type(
            str(space_id),
            entity_type,
            limit=limit,
            offset=offset,
        )

    return KernelEntityListResponse(
        entities=[KernelEntityResponse.from_model(e) for e in entities],
        total=len(entities),
        offset=offset,
        limit=limit,
    )


@research_spaces_router.post(
    "/{space_id}/entities",
    response_model=KernelEntityUpsertResponse,
    summary="Create or resolve a kernel entity",
    status_code=HTTP_201_CREATED,
)
def create_kernel_entity(
    space_id: UUID,
    request: KernelEntityCreateRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> KernelEntityUpsertResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    try:
        entity, created = service.create_or_resolve(
            research_space_id=str(space_id),
            entity_type=request.entity_type,
            identifiers=request.identifiers or None,
            display_label=request.display_label,
            metadata=request.metadata,
        )
        session.commit()
        return KernelEntityUpsertResponse(
            entity=KernelEntityResponse.from_model(entity),
            created=created,
        )
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail="Entity identifiers already exist for another entity.",
        ) from e
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
            detail=f"Failed to create entity: {e!s}",
        ) from e


@research_spaces_router.get(
    "/{space_id}/entities/{entity_id}",
    response_model=KernelEntityResponse,
    summary="Get kernel entity",
)
def get_kernel_entity(
    space_id: UUID,
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> KernelEntityResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    entity = service.get_entity(str(entity_id))
    if entity is None or str(entity.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )
    return KernelEntityResponse.from_model(entity)


@research_spaces_router.put(
    "/{space_id}/entities/{entity_id}",
    response_model=KernelEntityResponse,
    summary="Update kernel entity",
)
def update_kernel_entity(
    space_id: UUID,
    entity_id: UUID,
    request: KernelEntityUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> KernelEntityResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    entity = service.get_entity(str(entity_id))
    if entity is None or str(entity.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )

    try:
        updated_entity = entity
        if request.display_label is not None or request.metadata is not None:
            maybe_updated = service.update_entity(
                str(entity_id),
                display_label=request.display_label,
                metadata=request.metadata,
            )
            if maybe_updated is None:
                raise HTTPException(
                    status_code=HTTP_404_NOT_FOUND,
                    detail="Entity not found",
                )
            updated_entity = maybe_updated

        if request.identifiers:
            for namespace, value in request.identifiers.items():
                service.add_identifier(
                    entity_id=str(entity_id),
                    namespace=namespace,
                    identifier_value=value,
                )

        session.commit()
        return KernelEntityResponse.from_model(updated_entity)
    except HTTPException:
        session.rollback()
        raise
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail="Identifier already exists",
        ) from e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update entity: {e!s}",
        ) from e


@research_spaces_router.delete(
    "/{space_id}/entities/{entity_id}",
    summary="Delete kernel entity",
)
def delete_kernel_entity(
    space_id: UUID,
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> None:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    entity = service.get_entity(str(entity_id))
    if entity is None or str(entity.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )

    success = service.delete_entity(str(entity_id))
    if not success:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )

    session.commit()


@research_spaces_router.get(
    "/{space_id}/entities/{entity_id}/similar",
    response_model=KernelEntitySimilarityListResponse,
    summary="Find similar entities using hybrid graph + embedding scoring",
)
def list_similar_entities(
    space_id: UUID,
    entity_id: UUID,
    *,
    limit: int = Query(20, ge=1, le=100),
    min_similarity: float = Query(0.72, ge=0.0, le=1.0),
    target_entity_types: list[str] | None = Query(
        default=None,
        description="Optional repeated filter for target entity types.",
    ),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    similarity_service: KernelEntitySimilarityService = Depends(
        get_kernel_entity_similarity_service,
    ),
    session: Session = Depends(get_session),
) -> KernelEntitySimilarityListResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    if not _is_entity_embeddings_enabled():
        raise _feature_disabled_error(_ENTITY_EMBEDDINGS_ENABLED_ENV)

    try:
        similar_entities = similarity_service.get_similar_entities(
            research_space_id=str(space_id),
            entity_id=str(entity_id),
            limit=limit,
            min_similarity=min_similarity,
            target_entity_types=target_entity_types,
        )
    except EmbeddingNotReadyError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail={"code": "EMBEDDING_NOT_READY", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    results = [
        KernelEntitySimilarityResponse(
            entity_id=row.entity_id,
            entity_type=row.entity_type,
            display_label=row.display_label,
            similarity_score=row.similarity_score,
            score_breakdown=KernelEntitySimilarityScoreBreakdownResponse(
                vector_score=row.score_breakdown.vector_score,
                graph_overlap_score=row.score_breakdown.graph_overlap_score,
            ),
        )
        for row in similar_entities
    ]
    return KernelEntitySimilarityListResponse(
        source_entity_id=entity_id,
        results=results,
        total=len(results),
        limit=limit,
        min_similarity=min_similarity,
    )


@research_spaces_router.post(
    "/{space_id}/entities/embeddings/refresh",
    response_model=KernelEntityEmbeddingRefreshResponse,
    summary="Refresh entity embeddings for one research space",
)
def refresh_entity_embeddings(
    space_id: UUID,
    request: KernelEntityEmbeddingRefreshRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    similarity_service: KernelEntitySimilarityService = Depends(
        get_kernel_entity_similarity_service,
    ),
    session: Session = Depends(get_session),
) -> KernelEntityEmbeddingRefreshResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    if not _is_entity_embeddings_enabled():
        raise _feature_disabled_error(_ENTITY_EMBEDDINGS_ENABLED_ENV)

    try:
        summary = similarity_service.refresh_embeddings(
            research_space_id=str(space_id),
            entity_ids=(
                [str(entity_id) for entity_id in request.entity_ids]
                if request.entity_ids is not None
                else None
            ),
            limit=request.limit,
            model_name=request.model_name,
            embedding_version=request.embedding_version,
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh entity embeddings: {exc!s}",
        ) from exc

    return KernelEntityEmbeddingRefreshResponse(
        requested=summary.requested,
        processed=summary.processed,
        refreshed=summary.refreshed,
        unchanged=summary.unchanged,
        missing_entities=list(summary.missing_entities),
    )
