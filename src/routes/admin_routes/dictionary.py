"""
Admin dictionary endpoints for the kernel (Layer 1).

These endpoints allow platform administrators to browse and curate the
master dictionary: variable definitions, transforms, resolution policies,
entity types, relation types, and relation constraints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.application.services.kernel.dictionary_management_service import (
    DictionaryManagementService,
)
from src.domain.entities.user import User, UserRole
from src.domain.ports import DictionaryPort
from src.infrastructure.embeddings import HybridTextEmbeddingProvider
from src.infrastructure.repositories.kernel.kernel_dictionary_repository import (
    SqlAlchemyDictionaryRepository,
)
from src.routes.admin_routes.dependencies import get_admin_db_session
from src.routes.auth import get_current_active_user

from .dictionary_schemas import (
    DictionaryChangelogListResponse,
    DictionaryChangelogResponse,
    DictionaryEntityTypeCreateRequest,
    DictionaryEntityTypeListResponse,
    DictionaryEntityTypeResponse,
    DictionaryMergeRequest,
    DictionaryReembedRequest,
    DictionaryReembedResponse,
    DictionaryRelationTypeCreateRequest,
    DictionaryRelationTypeListResponse,
    DictionaryRelationTypeResponse,
    DictionarySearchListResponse,
    DictionarySearchResultResponse,
    EntityResolutionPolicyListResponse,
    EntityResolutionPolicyResponse,
    KernelDictionaryDimension,
    RelationConstraintListResponse,
    RelationConstraintResponse,
    ValueSetCreateRequest,
    ValueSetItemActiveRequest,
    ValueSetItemCreateRequest,
    ValueSetItemListResponse,
    ValueSetItemResponse,
    ValueSetListResponse,
    ValueSetResponse,
    VariableDefinitionCreateRequest,
    VariableDefinitionListResponse,
    VariableDefinitionResponse,
    VariableDefinitionReviewStatusRequest,
    VariableDefinitionRevokeRequest,
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
) -> DictionaryPort:
    """Build a DictionaryManagementService backed by a scoped admin DB session."""
    from src.infrastructure.llm.adapters.dictionary_search_harness_adapter import (
        ArtanaDictionarySearchHarnessAdapter,
    )

    repo = SqlAlchemyDictionaryRepository(session)
    embedding_provider = HybridTextEmbeddingProvider()
    search_harness = ArtanaDictionarySearchHarnessAdapter(
        dictionary_repo=repo,
        embedding_provider=embedding_provider,
    )
    return DictionaryManagementService(
        dictionary_repo=repo,
        dictionary_search_harness=search_harness,
        embedding_provider=embedding_provider,
    )


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
    service: DictionaryPort = Depends(get_dictionary_service),
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
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
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
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
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
    "/dictionary/entity-types",
    response_model=DictionaryEntityTypeListResponse,
    summary="List dictionary entity types",
)
async def list_dictionary_entity_types(
    domain_context: str | None = Query(None, description="Filter by domain context"),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryEntityTypeListResponse:
    entity_types = service.list_entity_types(domain_context=domain_context)
    return DictionaryEntityTypeListResponse(
        entity_types=[DictionaryEntityTypeResponse.from_model(e) for e in entity_types],
        total=len(entity_types),
    )


@router.get(
    "/dictionary/entity-types/{entity_type_id}",
    response_model=DictionaryEntityTypeResponse,
    summary="Get dictionary entity type",
)
async def get_dictionary_entity_type(
    entity_type_id: str,
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryEntityTypeResponse:
    entity_type = service.get_entity_type(entity_type_id)
    if entity_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity type '{entity_type_id}' not found",
        )
    return DictionaryEntityTypeResponse.from_model(entity_type)


@router.post(
    "/dictionary/entity-types",
    response_model=DictionaryEntityTypeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create dictionary entity type",
)
async def create_dictionary_entity_type(
    request: DictionaryEntityTypeCreateRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryEntityTypeResponse:
    try:
        entity_type = service.create_entity_type(
            entity_type=request.id,
            display_name=request.display_name,
            description=request.description,
            domain_context=request.domain_context,
            external_ontology_ref=request.external_ontology_ref,
            expected_properties=dict(request.expected_properties),
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
        return DictionaryEntityTypeResponse.from_model(entity_type)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Entity type already exists or references invalid domain context",
        ) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.patch(
    "/dictionary/entity-types/{entity_type_id}/review-status",
    response_model=DictionaryEntityTypeResponse,
    summary="Set dictionary entity type review status",
)
async def set_dictionary_entity_type_review_status(
    entity_type_id: str,
    request: VariableDefinitionReviewStatusRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryEntityTypeResponse:
    try:
        entity_type = service.set_entity_type_review_status(
            entity_type_id,
            review_status=request.review_status.value,
            reviewed_by=f"manual:{current_user.id}",
            revocation_reason=request.revocation_reason,
        )
        session.commit()
        return DictionaryEntityTypeResponse.from_model(entity_type)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post(
    "/dictionary/entity-types/{entity_type_id}/revoke",
    response_model=DictionaryEntityTypeResponse,
    summary="Revoke dictionary entity type",
)
async def revoke_dictionary_entity_type(
    entity_type_id: str,
    request: VariableDefinitionRevokeRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryEntityTypeResponse:
    try:
        entity_type = service.revoke_entity_type(
            entity_type_id,
            reason=request.reason,
            reviewed_by=f"manual:{current_user.id}",
        )
        session.commit()
        return DictionaryEntityTypeResponse.from_model(entity_type)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post(
    "/dictionary/entity-types/{entity_type_id}/merge",
    response_model=DictionaryEntityTypeResponse,
    summary="Merge dictionary entity type into another",
)
async def merge_dictionary_entity_type(
    entity_type_id: str,
    request: DictionaryMergeRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryEntityTypeResponse:
    try:
        entity_type = service.merge_entity_type(
            entity_type_id,
            request.target_id,
            reason=request.reason,
            reviewed_by=f"manual:{current_user.id}",
        )
        session.commit()
        return DictionaryEntityTypeResponse.from_model(entity_type)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/dictionary/relation-types",
    response_model=DictionaryRelationTypeListResponse,
    summary="List dictionary relation types",
)
async def list_dictionary_relation_types(
    domain_context: str | None = Query(None, description="Filter by domain context"),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationTypeListResponse:
    relation_types = service.list_relation_types(domain_context=domain_context)
    return DictionaryRelationTypeListResponse(
        relation_types=[
            DictionaryRelationTypeResponse.from_model(r) for r in relation_types
        ],
        total=len(relation_types),
    )


@router.get(
    "/dictionary/relation-types/{relation_type_id}",
    response_model=DictionaryRelationTypeResponse,
    summary="Get dictionary relation type",
)
async def get_dictionary_relation_type(
    relation_type_id: str,
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationTypeResponse:
    relation_type = service.get_relation_type(relation_type_id)
    if relation_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Relation type '{relation_type_id}' not found",
        )
    return DictionaryRelationTypeResponse.from_model(relation_type)


@router.post(
    "/dictionary/relation-types",
    response_model=DictionaryRelationTypeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create dictionary relation type",
)
async def create_dictionary_relation_type(
    request: DictionaryRelationTypeCreateRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationTypeResponse:
    try:
        relation_type = service.create_relation_type(
            relation_type=request.id,
            display_name=request.display_name,
            description=request.description,
            domain_context=request.domain_context,
            is_directional=request.is_directional,
            inverse_label=request.inverse_label,
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
        return DictionaryRelationTypeResponse.from_model(relation_type)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Relation type already exists or references invalid domain context",
        ) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.patch(
    "/dictionary/relation-types/{relation_type_id}/review-status",
    response_model=DictionaryRelationTypeResponse,
    summary="Set dictionary relation type review status",
)
async def set_dictionary_relation_type_review_status(
    relation_type_id: str,
    request: VariableDefinitionReviewStatusRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationTypeResponse:
    try:
        relation_type = service.set_relation_type_review_status(
            relation_type_id,
            review_status=request.review_status.value,
            reviewed_by=f"manual:{current_user.id}",
            revocation_reason=request.revocation_reason,
        )
        session.commit()
        return DictionaryRelationTypeResponse.from_model(relation_type)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post(
    "/dictionary/relation-types/{relation_type_id}/revoke",
    response_model=DictionaryRelationTypeResponse,
    summary="Revoke dictionary relation type",
)
async def revoke_dictionary_relation_type(
    relation_type_id: str,
    request: VariableDefinitionRevokeRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationTypeResponse:
    try:
        relation_type = service.revoke_relation_type(
            relation_type_id,
            reason=request.reason,
            reviewed_by=f"manual:{current_user.id}",
        )
        session.commit()
        return DictionaryRelationTypeResponse.from_model(relation_type)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post(
    "/dictionary/relation-types/{relation_type_id}/merge",
    response_model=DictionaryRelationTypeResponse,
    summary="Merge dictionary relation type into another",
)
async def merge_dictionary_relation_type(
    relation_type_id: str,
    request: DictionaryMergeRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryRelationTypeResponse:
    try:
        relation_type = service.merge_relation_type(
            relation_type_id,
            request.target_id,
            reason=request.reason,
            reviewed_by=f"manual:{current_user.id}",
        )
        session.commit()
        return DictionaryRelationTypeResponse.from_model(relation_type)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/dictionary/value-sets",
    response_model=ValueSetListResponse,
    summary="List dictionary value sets",
)
async def list_dictionary_value_sets(
    variable_id: str | None = Query(
        default=None,
        description="Filter by variable ID",
    ),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> ValueSetListResponse:
    value_sets = service.list_value_sets(variable_id=variable_id)
    return ValueSetListResponse(
        value_sets=[ValueSetResponse.from_model(vs) for vs in value_sets],
        total=len(value_sets),
    )


@router.post(
    "/dictionary/value-sets",
    response_model=ValueSetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create dictionary value set",
)
async def create_dictionary_value_set(
    request: ValueSetCreateRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> ValueSetResponse:
    try:
        value_set = service.create_value_set(
            value_set_id=request.id,
            variable_id=request.variable_id,
            name=request.name,
            description=request.description,
            external_ref=request.external_ref,
            is_extensible=request.is_extensible,
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
        return ValueSetResponse.from_model(value_set)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Value set already exists or references invalid variable",
        ) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/dictionary/value-sets/{value_set_id}/items",
    response_model=ValueSetItemListResponse,
    summary="List dictionary value set items",
)
async def list_dictionary_value_set_items(
    value_set_id: str,
    include_inactive: bool = Query(
        default=False,
        description="Include inactive value set items",
    ),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> ValueSetItemListResponse:
    items = service.list_value_set_items(
        value_set_id=value_set_id,
        include_inactive=include_inactive,
    )
    return ValueSetItemListResponse(
        items=[ValueSetItemResponse.from_model(item) for item in items],
        total=len(items),
    )


@router.post(
    "/dictionary/value-sets/{value_set_id}/items",
    response_model=ValueSetItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create dictionary value set item",
)
async def create_dictionary_value_set_item(
    value_set_id: str,
    request: ValueSetItemCreateRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> ValueSetItemResponse:
    try:
        item = service.create_value_set_item(
            value_set_id=value_set_id,
            code=request.code,
            display_label=request.display_label,
            synonyms=request.synonyms,
            external_ref=request.external_ref,
            sort_order=request.sort_order,
            is_active=request.is_active,
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
        return ValueSetItemResponse.from_model(item)
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Value set item already exists or references invalid value set",
        ) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.patch(
    "/dictionary/value-set-items/{value_set_item_id}/active",
    response_model=ValueSetItemResponse,
    summary="Activate/deactivate a dictionary value set item",
)
async def set_dictionary_value_set_item_active(
    value_set_item_id: int,
    request: ValueSetItemActiveRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> ValueSetItemResponse:
    try:
        item = service.set_value_set_item_active(
            value_set_item_id,
            is_active=request.is_active,
            reviewed_by=f"manual:{current_user.id}",
            revocation_reason=request.revocation_reason,
        )
        session.commit()
        return ValueSetItemResponse.from_model(item)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/dictionary/search",
    response_model=DictionarySearchListResponse,
    summary="Search dictionary entries",
)
async def search_dictionary_entries(
    terms: list[str] = Query(
        ...,
        description="Search terms (repeat parameter for multiple terms)",
    ),
    dimensions: list[KernelDictionaryDimension] | None = Query(
        default=None,
        description="Optional dictionary dimensions to search",
    ),
    domain_context: str | None = Query(
        default=None,
        description="Optional domain context filter",
    ),
    limit: int = Query(default=50, ge=1, le=500),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionarySearchListResponse:
    requested_dimensions = (
        [dimension.value for dimension in dimensions] if dimensions else None
    )
    results = service.dictionary_search(
        terms=terms,
        dimensions=requested_dimensions,
        domain_context=domain_context,
        limit=limit,
    )
    return DictionarySearchListResponse(
        results=[
            DictionarySearchResultResponse.from_model(result) for result in results
        ],
        total=len(results),
    )


@router.get(
    "/dictionary/search/by-domain/{domain_context}",
    response_model=DictionarySearchListResponse,
    summary="List dictionary entries by domain",
)
async def search_dictionary_entries_by_domain(
    domain_context: str,
    limit: int = Query(default=200, ge=1, le=500),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionarySearchListResponse:
    results = service.dictionary_search_by_domain(
        domain_context=domain_context,
        limit=limit,
    )
    return DictionarySearchListResponse(
        results=[
            DictionarySearchResultResponse.from_model(result) for result in results
        ],
        total=len(results),
    )


@router.post(
    "/dictionary/reembed",
    response_model=DictionaryReembedResponse,
    summary="Recompute dictionary description embeddings",
)
async def reembed_dictionary_descriptions(
    request: DictionaryReembedRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryReembedResponse:
    try:
        updated_records = service.reembed_descriptions(
            model_name=request.model_name,
            limit_per_dimension=request.limit_per_dimension,
            changed_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
        return DictionaryReembedResponse(
            updated_records=updated_records,
            model_name=request.model_name,
        )
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/dictionary/resolution-policies",
    response_model=EntityResolutionPolicyListResponse,
    summary="List entity resolution policies",
)
async def list_entity_resolution_policies(
    service: DictionaryPort = Depends(get_dictionary_service),
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
    service: DictionaryPort = Depends(get_dictionary_service),
) -> RelationConstraintListResponse:
    constraints = service.get_constraints(
        source_type=source_type,
        relation_type=relation_type,
    )
    return RelationConstraintListResponse(
        constraints=[RelationConstraintResponse.from_model(c) for c in constraints],
        total=len(constraints),
    )


@router.get(
    "/dictionary/changelog",
    response_model=DictionaryChangelogListResponse,
    summary="List dictionary changelog entries",
)
async def list_dictionary_changelog_entries(
    table_name: str | None = Query(
        default=None,
        description="Filter by dictionary table name",
    ),
    record_id: str | None = Query(
        default=None,
        description="Filter by dictionary record ID",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> DictionaryChangelogListResponse:
    changelog_entries = service.list_changelog_entries(
        table_name=table_name,
        record_id=record_id,
        limit=limit,
    )
    return DictionaryChangelogListResponse(
        changelog_entries=[
            DictionaryChangelogResponse.from_model(entry) for entry in changelog_entries
        ],
        total=len(changelog_entries),
    )


@router.patch(
    "/dictionary/variables/{variable_id}/review-status",
    response_model=VariableDefinitionResponse,
    summary="Set dictionary variable review status",
)
async def set_dictionary_variable_review_status(
    variable_id: str,
    request: VariableDefinitionReviewStatusRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> VariableDefinitionResponse:
    try:
        variable = service.set_review_status(
            variable_id,
            review_status=request.review_status.value,
            reviewed_by=f"manual:{current_user.id}",
            revocation_reason=request.revocation_reason,
        )
        session.commit()
        return VariableDefinitionResponse.from_model(variable)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post(
    "/dictionary/variables/{variable_id}/revoke",
    response_model=VariableDefinitionResponse,
    summary="Revoke dictionary variable",
)
async def revoke_dictionary_variable(
    variable_id: str,
    request: VariableDefinitionRevokeRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> VariableDefinitionResponse:
    try:
        variable = service.revoke_variable(
            variable_id,
            reason=request.reason,
            reviewed_by=f"manual:{current_user.id}",
        )
        session.commit()
        return VariableDefinitionResponse.from_model(variable)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post(
    "/dictionary/variables/{variable_id}/merge",
    response_model=VariableDefinitionResponse,
    summary="Merge dictionary variable into another",
)
async def merge_dictionary_variable(
    variable_id: str,
    request: DictionaryMergeRequest,
    current_user: User = Depends(require_admin_user),
    session: Session = Depends(get_admin_db_session),
    service: DictionaryPort = Depends(get_dictionary_service),
) -> VariableDefinitionResponse:
    try:
        variable = service.merge_variable_definition(
            variable_id,
            request.target_id,
            reason=request.reason,
            reviewed_by=f"manual:{current_user.id}",
        )
        session.commit()
        return VariableDefinitionResponse.from_model(variable)
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


__all__ = ["router"]
