"""
Admin dictionary endpoints for the kernel (Layer 1).

These endpoints allow platform administrators to browse and curate the
master dictionary: variable definitions, transforms, resolution policies,
and relation constraints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.application.services.kernel.dictionary_service import DictionaryService
from src.domain.entities.user import User, UserRole
from src.infrastructure.repositories.kernel.kernel_dictionary_repository import (
    SqlAlchemyDictionaryRepository,
)
from src.routes.admin_routes.dependencies import get_admin_db_session
from src.routes.auth import get_current_active_user

from .dictionary_schemas import (
    EntityResolutionPolicyListResponse,
    EntityResolutionPolicyResponse,
    RelationConstraintListResponse,
    RelationConstraintResponse,
    TransformRegistryListResponse,
    TransformRegistryResponse,
    VariableDefinitionCreateRequest,
    VariableDefinitionListResponse,
    VariableDefinitionResponse,
)


async def require_admin_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Ensure the authenticated user is a platform admin."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required",
        )
    return current_user


def get_dictionary_service(
    session: Session = Depends(get_admin_db_session),
) -> DictionaryService:
    """Build a DictionaryService backed by a scoped admin DB session."""
    repo = SqlAlchemyDictionaryRepository(session)
    return DictionaryService(dictionary_repo=repo)


router = APIRouter(
    dependencies=[Depends(require_admin_user)],
    tags=["dictionary"],
)


@router.get(
    "/dictionary/variables",
    response_model=VariableDefinitionListResponse,
    summary="List dictionary variables",
)
async def list_dictionary_variables(
    domain_context: str | None = Query(None, description="Filter by domain context"),
    data_type: str | None = Query(None, description="Filter by kernel data type"),
    service: DictionaryService = Depends(get_dictionary_service),
) -> VariableDefinitionListResponse:
    variables = service.list_variables(
        domain_context=domain_context,
        data_type=data_type,
    )
    return VariableDefinitionListResponse(
        variables=[VariableDefinitionResponse.from_model(v) for v in variables],
        total=len(variables),
    )


@router.post(
    "/dictionary/variables",
    response_model=VariableDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create dictionary variable",
)
async def create_dictionary_variable(
    request: VariableDefinitionCreateRequest,
    session: Session = Depends(get_admin_db_session),
    service: DictionaryService = Depends(get_dictionary_service),
) -> VariableDefinitionResponse:
    try:
        variable = service.create_variable(
            variable_id=request.id,
            canonical_name=request.canonical_name,
            display_name=request.display_name,
            data_type=request.data_type.value,
            domain_context=request.domain_context,
            sensitivity=request.sensitivity.value,
            preferred_unit=request.preferred_unit,
            constraints=dict(request.constraints),
            description=request.description,
        )
        session.commit()
        return VariableDefinitionResponse.from_model(variable)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Variable already exists",
        ) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/dictionary/transforms",
    response_model=TransformRegistryListResponse,
    summary="List transform registry",
)
async def list_transform_registry(
    status_filter: str = Query("ACTIVE", alias="status"),
    service: DictionaryService = Depends(get_dictionary_service),
) -> TransformRegistryListResponse:
    transforms = service.list_transforms(status=status_filter)
    return TransformRegistryListResponse(
        transforms=[TransformRegistryResponse.from_model(t) for t in transforms],
        total=len(transforms),
    )


@router.get(
    "/dictionary/resolution-policies",
    response_model=EntityResolutionPolicyListResponse,
    summary="List entity resolution policies",
)
async def list_entity_resolution_policies(
    service: DictionaryService = Depends(get_dictionary_service),
) -> EntityResolutionPolicyListResponse:
    policies = service.list_resolution_policies()
    return EntityResolutionPolicyListResponse(
        policies=[EntityResolutionPolicyResponse.from_model(p) for p in policies],
        total=len(policies),
    )


@router.get(
    "/dictionary/relation-constraints",
    response_model=RelationConstraintListResponse,
    summary="List relation constraints",
)
async def list_relation_constraints(
    source_type: str | None = Query(None, description="Filter by source entity type"),
    relation_type: str | None = Query(
        None,
        description="Filter by relation type",
    ),
    service: DictionaryService = Depends(get_dictionary_service),
) -> RelationConstraintListResponse:
    constraints = service.get_constraints(
        source_type=source_type,
        relation_type=relation_type,
    )
    return RelationConstraintListResponse(
        constraints=[RelationConstraintResponse.from_model(c) for c in constraints],
        total=len(constraints),
    )


__all__ = ["router"]
