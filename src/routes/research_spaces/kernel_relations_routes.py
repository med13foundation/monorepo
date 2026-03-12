"""Kernel relation + graph endpoints scoped to research spaces."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.application.services.claim_first_metrics import (
    emit_graph_filter_preset_usage,
    increment_metric,
)
from src.database.session import get_session
from src.domain.entities.user import User, UserRole
from src.models.database.source_document import SourceDocumentModel
from src.routes.auth import get_current_active_user
from src.routes.research_spaces._claim_evidence_paper_links import (
    resolve_claim_evidence_paper_links,
)
from src.routes.research_spaces._kernel_relation_route_support import (
    CreateRelationDependencies,
    RelationClaimTriageDependencies,
    get_create_relation_dependencies,
    get_relation_claim_triage_dependencies,
    manual_relation_claim_text,
)
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    require_curator_role,
    verify_space_membership,
)
from src.routes.research_spaces.kernel_dependencies import (
    get_kernel_claim_evidence_service,
    get_kernel_entity_service,
    get_kernel_relation_claim_service,
    get_kernel_relation_service,
)
from src.routes.research_spaces.kernel_schemas import (
    KernelClaimEvidenceListResponse,
    KernelClaimEvidenceResponse,
    KernelEntityResponse,
    KernelGraphExportResponse,
    KernelGraphSubgraphMeta,
    KernelGraphSubgraphRequest,
    KernelGraphSubgraphResponse,
    KernelRelationClaimListResponse,
    KernelRelationClaimResponse,
    KernelRelationClaimTriageRequest,
    KernelRelationConflictListResponse,
    KernelRelationConflictResponse,
    KernelRelationCreateRequest,
    KernelRelationCurationUpdateRequest,
    KernelRelationListResponse,
    KernelRelationResponse,
)

from ._kernel_relation_evidence_presenter import load_relation_evidence_presentation
from ._kernel_relation_subgraph_helpers import (
    collect_candidate_relations,
    limit_relations_to_anchor_component,
    materialize_nodes,
    ordered_node_ids_for_relations,
)
from .router import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)

if TYPE_CHECKING:
    from src.application.services.kernel.kernel_claim_evidence_service import (
        KernelClaimEvidenceService,
    )
    from src.application.services.kernel.kernel_entity_service import (
        KernelEntityService,
    )
    from src.application.services.kernel.kernel_relation_claim_service import (
        KernelRelationClaimService,
    )
    from src.application.services.kernel.kernel_relation_service import (
        KernelRelationService,
    )
    from src.application.services.membership_management_service import (
        MembershipManagementService,
    )
    from src.domain.ports.dictionary_port import DictionaryPort

_CANONICAL_CURATION_STATUSES = frozenset(
    {"APPROVED", "UNDER_REVIEW", "DRAFT", "REJECTED", "RETRACTED"},
)
_CURATION_STATUS_ALIAS: dict[str, str] = {"PENDING_REVIEW": "DRAFT"}
_CLAIM_STATUSES = frozenset({"OPEN", "NEEDS_MAPPING", "REJECTED", "RESOLVED"})
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
_CLAIM_PERSISTABILITY = frozenset({"PERSISTABLE", "NON_PERSISTABLE"})
_CLAIM_POLARITIES = frozenset({"SUPPORT", "REFUTE", "UNCERTAIN", "HYPOTHESIS"})
_CERTAINTY_BANDS = frozenset({"HIGH", "MEDIUM", "LOW"})
_ClaimStatus = Literal["OPEN", "NEEDS_MAPPING", "REJECTED", "RESOLVED"]
_ClaimValidationState = Literal[
    "ALLOWED",
    "FORBIDDEN",
    "UNDEFINED",
    "INVALID_COMPONENTS",
    "ENDPOINT_UNRESOLVED",
    "SELF_LOOP",
]
_ClaimPersistability = Literal["PERSISTABLE", "NON_PERSISTABLE"]
_ClaimPolarity = Literal["SUPPORT", "REFUTE", "UNCERTAIN", "HYPOTHESIS"]
_CertaintyBand = Literal["HIGH", "MEDIUM", "LOW"]
_CLAIM_VALIDATION_STATE_MAP: dict[str, _ClaimValidationState] = {
    "ALLOWED": "ALLOWED",
    "FORBIDDEN": "FORBIDDEN",
    "UNDEFINED": "UNDEFINED",
    "INVALID_COMPONENTS": "INVALID_COMPONENTS",
    "ENDPOINT_UNRESOLVED": "ENDPOINT_UNRESOLVED",
    "SELF_LOOP": "SELF_LOOP",
}


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


def _activate_dictionary_dependencies_for_claim(  # noqa: PLR0913
    *,
    dictionary_service: DictionaryPort,
    source_type: str,
    relation_type: str,
    target_type: str,
    reviewed_by: str,
    source_ref: str,
) -> None:
    source_entity = dictionary_service.get_entity_type(
        source_type,
        include_inactive=True,
    )
    if source_entity is None:
        msg = f"Dictionary entity type '{source_type}' not found."
        raise ValueError(msg)
    if source_entity.review_status != "ACTIVE":
        dictionary_service.set_entity_type_review_status(
            source_type,
            review_status="ACTIVE",
            reviewed_by=reviewed_by,
        )

    target_entity = dictionary_service.get_entity_type(
        target_type,
        include_inactive=True,
    )
    if target_entity is None:
        msg = f"Dictionary entity type '{target_type}' not found."
        raise ValueError(msg)
    if target_entity.review_status != "ACTIVE":
        dictionary_service.set_entity_type_review_status(
            target_type,
            review_status="ACTIVE",
            reviewed_by=reviewed_by,
        )

    relation = dictionary_service.get_relation_type(
        relation_type,
        include_inactive=True,
    )
    if relation is None:
        msg = f"Dictionary relation type '{relation_type}' not found."
        raise ValueError(msg)
    if relation.review_status != "ACTIVE":
        dictionary_service.set_relation_type_review_status(
            relation_type,
            review_status="ACTIVE",
            reviewed_by=reviewed_by,
        )

    dictionary_service.create_relation_constraint(
        source_type=source_type,
        relation_type=relation_type,
        target_type=target_type,
        is_allowed=True,
        requires_evidence=True,
        created_by=reviewed_by,
        source_ref=source_ref,
    )


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


def _normalize_curation_status_filter(status: str | None) -> str | None:
    if status is None:
        return None
    normalized = status.strip().upper()
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


def _normalize_curation_status_update(status: str) -> str:
    normalized = status.strip().upper()
    if normalized not in _CANONICAL_CURATION_STATUSES:
        msg = "curation_status must be one of: " + ", ".join(
            sorted(_CANONICAL_CURATION_STATUSES),
        )
        raise ValueError(msg)
    return normalized


def _normalize_claim_status_filter(status: str | None) -> _ClaimStatus | None:
    if status is None:
        return None
    normalized = status.strip().upper()
    if not normalized:
        return None
    if normalized not in _CLAIM_STATUSES:
        msg = "claim_status must be one of: OPEN, NEEDS_MAPPING, REJECTED, RESOLVED"
        raise ValueError(msg)
    if normalized == "OPEN":
        return "OPEN"
    if normalized == "NEEDS_MAPPING":
        return "NEEDS_MAPPING"
    if normalized == "REJECTED":
        return "REJECTED"
    return "RESOLVED"


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
        msg = (
            "validation_state must be one of: ALLOWED, FORBIDDEN, UNDEFINED, "
            "INVALID_COMPONENTS, ENDPOINT_UNRESOLVED, SELF_LOOP"
        )
        raise ValueError(msg)
    return normalized_state


def _normalize_claim_persistability(
    value: str | None,
) -> _ClaimPersistability | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if normalized not in _CLAIM_PERSISTABILITY:
        msg = "persistability must be one of: PERSISTABLE, NON_PERSISTABLE"
        raise ValueError(msg)
    if normalized == "PERSISTABLE":
        return "PERSISTABLE"
    return "NON_PERSISTABLE"


def _normalize_claim_polarity(
    value: str | None,
) -> _ClaimPolarity | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if normalized not in _CLAIM_POLARITIES:
        msg = "polarity must be one of: SUPPORT, REFUTE, UNCERTAIN, HYPOTHESIS"
        raise ValueError(msg)
    if normalized == "SUPPORT":
        return "SUPPORT"
    if normalized == "REFUTE":
        return "REFUTE"
    if normalized == "UNCERTAIN":
        return "UNCERTAIN"
    return "HYPOTHESIS"


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
    validation_state: str | None = Query(None),
    source_document_id: str | None = Query(None),
    certainty_band: str | None = Query(None),
    node_query: str | None = Query(None),
    node_ids: list[str] | None = Query(
        None,
        description="Comma-separated entity IDs to match relation source or target.",
    ),
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

    normalized_curation_status = _normalize_curation_status_filter(curation_status)
    normalized_validation_state = _normalize_claim_validation_state(validation_state)
    normalized_certainty_band = _normalize_certainty_band(certainty_band)
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
        relation_ids=[relation.id for relation in relations],
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


@research_spaces_router.post(
    "/{space_id}/relations",
    response_model=KernelRelationResponse,
    summary="Create kernel relation (internal compatibility endpoint)",
    status_code=HTTP_201_CREATED,
)
def create_kernel_relation(
    space_id: UUID,
    request: KernelRelationCreateRequest,
    current_user: User = Depends(get_current_active_user),
    dependencies: CreateRelationDependencies = Depends(
        get_create_relation_dependencies,
    ),
) -> KernelRelationResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        dependencies.membership_service,
        dependencies.session,
        current_user.role,
    )
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=(
                "POST /relations is internal-only. Create or resolve claims to "
                "materialize canonical relations."
            ),
        )

    try:
        source_entity = dependencies.write_services.entity_service.get_entity(
            str(request.source_id),
        )
        target_entity = dependencies.write_services.entity_service.get_entity(
            str(request.target_id),
        )
        if source_entity is None or target_entity is None:
            msg = "Source or target entity not found after relation creation"
            raise ValueError(msg)
        manual_claim = dependencies.write_services.relation_claim_service.create_claim(
            research_space_id=str(space_id),
            source_document_id=None,
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
            claim_text=manual_relation_claim_text(
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
        dependencies.write_services.claim_participant_service.create_participant(
            claim_id=str(manual_claim.id),
            research_space_id=str(space_id),
            role="SUBJECT",
            label=source_entity.display_label,
            entity_id=str(source_entity.id),
            position=0,
            qualifiers={"origin": "manual_relation_api"},
        )
        dependencies.write_services.claim_participant_service.create_participant(
            claim_id=str(manual_claim.id),
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
        ):
            dependencies.write_services.claim_evidence_service.create_evidence(
                claim_id=str(manual_claim.id),
                source_document_id=None,
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
        materialized = dependencies.write_services.relation_projection_materialization_service.materialize_support_claim(
            claim_id=str(manual_claim.id),
            research_space_id=str(space_id),
            projection_origin="MANUAL_RELATION",
            reviewed_by=str(current_user.id),
        )
        relation = materialized.relation
        if relation is None:
            msg = "Manual relation claim did not materialize a canonical relation"
            raise ValueError(msg)
        dependencies.session.commit()
        return KernelRelationResponse.from_model(relation)
    except IntegrityError as e:
        dependencies.session.rollback()
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=(
                "Relation write conflicts with dictionary constraints, "
                "research-space isolation, or required evidence checks"
            ),
        ) from e
    except ValueError as e:
        dependencies.session.rollback()
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        dependencies.session.rollback()
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
        normalized_status = _normalize_curation_status_update(request.curation_status)
        updated = relation_service.update_curation_status(
            str(relation_id),
            curation_status=normalized_status,
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
            status_code=HTTP_400_BAD_REQUEST,
            detail="seed_entity_ids must be empty when mode='starter'.",
        )
    if mode == "seeded" and not seed_entity_ids:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
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
    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

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
    )
    final_node_ids = final_node_ids[: request.max_nodes]

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


@research_spaces_router.get(
    "/{space_id}/relation-claims",
    response_model=KernelRelationClaimListResponse,
    summary="List extraction relation claims",
)
def list_relation_claims(
    space_id: UUID,
    *,
    claim_status: str | None = Query(None),
    validation_state: str | None = Query(None),
    persistability: str | None = Query(None),
    polarity: str | None = Query(None),
    source_document_id: str | None = Query(None),
    relation_type: str | None = Query(None),
    linked_relation_id: str | None = Query(None),
    certainty_band: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    session: Session = Depends(get_session),
) -> KernelRelationClaimListResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    normalized_claim_status = _normalize_claim_status_filter(claim_status)
    normalized_validation_state = _normalize_claim_validation_state(validation_state)
    normalized_persistability = _normalize_claim_persistability(persistability)
    normalized_polarity = _normalize_claim_polarity(polarity)
    normalized_certainty_band = _normalize_certainty_band(certainty_band)

    claims = relation_claim_service.list_by_research_space(
        str(space_id),
        claim_status=normalized_claim_status,
        validation_state=normalized_validation_state,
        persistability=normalized_persistability,
        polarity=normalized_polarity,
        source_document_id=source_document_id,
        relation_type=relation_type,
        linked_relation_id=linked_relation_id,
        certainty_band=normalized_certainty_band,
        limit=limit,
        offset=offset,
    )
    total = relation_claim_service.count_by_research_space(
        str(space_id),
        claim_status=normalized_claim_status,
        validation_state=normalized_validation_state,
        persistability=normalized_persistability,
        polarity=normalized_polarity,
        source_document_id=source_document_id,
        relation_type=relation_type,
        linked_relation_id=linked_relation_id,
        certainty_band=normalized_certainty_band,
    )
    return KernelRelationClaimListResponse(
        claims=[KernelRelationClaimResponse.from_model(claim) for claim in claims],
        total=total,
        offset=offset,
        limit=limit,
    )


@research_spaces_router.get(
    "/{space_id}/relation-claims/{claim_id}/evidence",
    response_model=KernelClaimEvidenceListResponse,
    summary="List claim evidence rows for one relation claim",
)
def list_relation_claim_evidence(
    space_id: UUID,
    claim_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    claim_evidence_service: KernelClaimEvidenceService = Depends(
        get_kernel_claim_evidence_service,
    ),
    session: Session = Depends(get_session),
) -> KernelClaimEvidenceListResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    claim = relation_claim_service.get_claim(str(claim_id))
    if claim is None or str(claim.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Relation claim not found",
        )
    evidence_rows = claim_evidence_service.list_for_claim(str(claim_id))
    source_document_ids = {
        str(evidence_row.source_document_id)
        for evidence_row in evidence_rows
        if evidence_row.source_document_id is not None
    }
    source_documents_by_id: dict[str, SourceDocumentModel] = {}
    if source_document_ids:
        source_documents = session.scalars(
            select(SourceDocumentModel).where(
                SourceDocumentModel.id.in_(source_document_ids),
            ),
        ).all()
        source_documents_by_id = {
            str(source_document.id): source_document
            for source_document in source_documents
        }

    response_rows: list[KernelClaimEvidenceResponse] = []
    for evidence_row in evidence_rows:
        source_document = (
            source_documents_by_id.get(str(evidence_row.source_document_id))
            if evidence_row.source_document_id is not None
            else None
        )
        response_rows.append(
            KernelClaimEvidenceResponse.from_model(
                evidence_row,
                paper_links=resolve_claim_evidence_paper_links(
                    source_document=source_document,
                    evidence_metadata=evidence_row.metadata_payload,
                ),
            ),
        )
    return KernelClaimEvidenceListResponse(
        claim_id=claim_id,
        evidence=response_rows,
        total=len(evidence_rows),
    )


@research_spaces_router.get(
    "/{space_id}/relations/conflicts",
    response_model=KernelRelationConflictListResponse,
    summary="List mixed-polarity conflicts for canonical relations",
)
def list_relation_conflicts(
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
) -> KernelRelationConflictListResponse:
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    conflicts = relation_claim_service.list_conflicts_by_research_space(
        str(space_id),
        limit=limit,
        offset=offset,
    )
    if conflicts:
        increment_metric(
            "relations_conflict_detected_total",
            delta=len(conflicts),
            tags={"research_space_id": str(space_id)},
        )
    total = relation_claim_service.count_conflicts_by_research_space(str(space_id))
    return KernelRelationConflictListResponse(
        conflicts=[
            KernelRelationConflictResponse.from_model(item) for item in conflicts
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@research_spaces_router.patch(
    "/{space_id}/relation-claims/{claim_id}",
    response_model=KernelRelationClaimResponse,
    summary="Update relation-claim triage status",
)
def update_relation_claim_status(  # noqa: PLR0912
    space_id: UUID,
    claim_id: UUID,
    request: KernelRelationClaimTriageRequest,
    current_user: User = Depends(get_current_active_user),
    triage_dependencies: RelationClaimTriageDependencies = Depends(
        get_relation_claim_triage_dependencies,
    ),
) -> KernelRelationClaimResponse:
    membership_service = triage_dependencies.membership_service
    relation_claim_service = triage_dependencies.relation_claim_service
    relation_projection_materialization_service = (
        triage_dependencies.relation_projection_materialization_service
    )
    dictionary_service = triage_dependencies.dictionary_service
    session = triage_dependencies.session

    require_curator_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )
    existing = relation_claim_service.get_claim(str(claim_id))
    if existing is None or str(existing.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Relation claim not found",
        )
    try:
        normalized_status = _normalize_claim_status_filter(request.claim_status)
        if normalized_status is None:
            msg = "claim_status is required"
            raise ValueError(msg)
        updated = relation_claim_service.update_claim_status(
            str(claim_id),
            claim_status=normalized_status,
            triaged_by=str(current_user.id),
        )
        if normalized_status == "RESOLVED":
            if updated.persistability != "PERSISTABLE":
                msg = (
                    "Claim cannot be resolved yet because it is NON_PERSISTABLE. "
                    "Use Needs Mapping or Reject."
                )
                raise ValueError(msg)
            reviewed_by = str(current_user.id)
            source_ref = f"relation_claim:{updated.id}"
            _activate_dictionary_dependencies_for_claim(
                dictionary_service=dictionary_service,
                source_type=updated.source_type,
                relation_type=updated.relation_type,
                target_type=updated.target_type,
                reviewed_by=reviewed_by,
                source_ref=source_ref,
            )
            if updated.polarity == "SUPPORT":
                relation_projection_materialization_service.materialize_support_claim(
                    claim_id=str(updated.id),
                    research_space_id=str(space_id),
                    projection_origin="CLAIM_RESOLUTION",
                    reviewed_by=reviewed_by,
                )
                refreshed_claim = relation_claim_service.get_claim(str(updated.id))
                if refreshed_claim is not None:
                    updated = refreshed_claim
            else:
                linked_relation = None
                try:
                    linked_relation = relation_projection_materialization_service.find_claim_backed_relation_for_claim(
                        claim_id=str(updated.id),
                        research_space_id=str(space_id),
                    )
                except ValueError:
                    linked_relation = None
                if linked_relation is not None:
                    updated = relation_claim_service.link_claim_to_relation(
                        str(updated.id),
                        linked_relation_id=str(linked_relation.id),
                    )
                else:
                    updated = relation_claim_service.clear_claim_relation_link(
                        str(updated.id),
                    )
        elif existing.polarity == "SUPPORT":
            relation_projection_materialization_service.detach_claim_projection(
                str(existing.id),
                str(space_id),
            )
        else:
            updated = relation_claim_service.clear_claim_relation_link(
                str(updated.id),
            )
        session.commit()
        return KernelRelationClaimResponse.from_model(updated)
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
            detail=f"Failed to update relation claim: {exc!s}",
        ) from exc
