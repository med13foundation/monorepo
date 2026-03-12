"""Build unified graph documents with claim and evidence overlays."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.application.services.kernel import (
    KernelClaimEvidenceService,
    KernelClaimParticipantService,
    KernelEntityService,
    KernelRelationClaimService,
    KernelRelationProjectionSourceService,
    KernelRelationService,
)
from src.domain.entities.kernel.claim_evidence import KernelClaimEvidence
from src.domain.entities.kernel.relation_claims import KernelRelationClaim
from src.routes.research_spaces._claim_evidence_paper_links import (
    resolve_claim_evidence_paper_links,
)
from src.routes.research_spaces._kernel_graph_document_support import (
    edge_sort_key,
    evidence_node_label,
    evidence_node_type_label,
    fallback_claim_endpoint_anchor_node_id,
    graph_entity_node,
    node_sort_key,
    normalize_curation_status_filters,
    normalize_filter_values,
    participant_anchor_node_id,
    source_document_lookup,
    trim_label,
)
from src.routes.research_spaces._kernel_graph_document_support import (
    selected_claims as select_claims,
)
from src.routes.research_spaces._kernel_relation_subgraph_helpers import (
    collect_candidate_relations,
    limit_relations_to_anchor_component,
    materialize_nodes,
    ordered_node_ids_for_relations,
)
from src.routes.research_spaces.kernel_schemas import (
    KernelGraphDocumentCounts,
    KernelGraphDocumentEdge,
    KernelGraphDocumentMeta,
    KernelGraphDocumentNode,
    KernelGraphDocumentRequest,
    KernelGraphDocumentResponse,
)
from src.type_definitions.common import JSONObject


def build_kernel_graph_document(  # noqa: PLR0912, PLR0913, PLR0915
    *,
    space_id: str,
    request: KernelGraphDocumentRequest,
    entity_service: KernelEntityService,
    relation_service: KernelRelationService,
    relation_claim_service: KernelRelationClaimService,
    relation_projection_source_service: KernelRelationProjectionSourceService,
    claim_participant_service: KernelClaimParticipantService,
    claim_evidence_service: KernelClaimEvidenceService,
    session: Session,
) -> KernelGraphDocumentResponse:
    relation_types = normalize_filter_values(request.relation_types)
    curation_statuses = normalize_curation_status_filters(request.curation_statuses)
    seed_entity_ids = [str(seed_id) for seed_id in request.seed_entity_ids]
    mode = request.mode

    if mode == "starter" and seed_entity_ids:
        msg = "seed_entity_ids must be empty when mode='starter'."
        raise ValueError(msg)
    if mode == "seeded" and not seed_entity_ids:
        msg = "seed_entity_ids is required when mode='seeded'."
        raise ValueError(msg)

    candidate_relations = collect_candidate_relations(
        mode=mode,
        space_id=space_id,
        request=request,
        relation_service=relation_service,
        relation_types=relation_types,
        curation_statuses=curation_statuses,
    )
    if mode == "starter":
        candidate_relations = limit_relations_to_anchor_component(
            relations=candidate_relations,
            preferred_seed_entity_ids=seed_entity_ids,
        )

    pre_cap_entity_node_ids = set(seed_entity_ids)
    for relation in candidate_relations:
        pre_cap_entity_node_ids.add(str(relation.source_id))
        pre_cap_entity_node_ids.add(str(relation.target_id))
    pre_cap_canonical_edge_count = len(candidate_relations)
    pre_cap_entity_node_count = len(pre_cap_entity_node_ids)

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
    final_entity_node_ids = ordered_node_ids_for_relations(
        final_relations,
        seed_entity_ids=seed_entity_ids,
    )[: request.max_nodes]
    entity_nodes = materialize_nodes(
        entity_ids=final_entity_node_ids,
        space_id=space_id,
        entity_service=entity_service,
    )

    node_by_id: dict[str, KernelGraphDocumentNode] = {
        str(entity.id): graph_entity_node(entity) for entity in entity_nodes
    }
    relation_by_id = {str(relation.id): relation for relation in final_relations}

    linked_claims_all: list[KernelRelationClaim] = []
    projection_claims_all: list[KernelRelationClaim] = []
    if request.include_claims and final_relations:
        linked_claims_all = relation_claim_service.list_by_linked_relation_ids(
            research_space_id=space_id,
            linked_relation_ids=[str(relation.id) for relation in final_relations],
        )
        projection_claim_ids: list[str] = []
        for relation in final_relations:
            for projection_row in relation_projection_source_service.list_for_relation(
                str(relation.id),
            ):
                claim_id = str(projection_row.claim_id)
                if claim_id not in projection_claim_ids:
                    projection_claim_ids.append(claim_id)
        if projection_claim_ids:
            projection_claims_all = relation_claim_service.list_claims_by_ids(
                projection_claim_ids,
            )

    selected_claims = (
        select_claims(projection_claims_all, max_claims=request.max_claims)
        if request.include_claims
        else []
    )
    selected_claim_ids = [str(claim.id) for claim in selected_claims]

    participants_by_claim_id = (
        claim_participant_service.list_for_claim_ids(selected_claim_ids)
        if selected_claim_ids
        else {}
    )
    evidence_by_claim_id = (
        claim_evidence_service.list_for_claim_ids(selected_claim_ids)
        if request.include_claims and request.include_evidence and selected_claim_ids
        else {}
    )

    all_selected_evidence_rows: list[KernelClaimEvidence] = []
    if evidence_by_claim_id:
        for claim_id in selected_claim_ids:
            claim_rows = evidence_by_claim_id.get(claim_id, [])
            all_selected_evidence_rows.extend(
                claim_rows[: request.evidence_limit_per_claim],
            )
    source_documents_by_id = source_document_lookup(
        session=session,
        evidence_rows=all_selected_evidence_rows,
    )

    claims_by_relation_id: dict[str, list[KernelRelationClaim]] = {}
    for claim in linked_claims_all:
        if claim.linked_relation_id is None:
            continue
        relation_id = str(claim.linked_relation_id)
        claims_by_relation_id.setdefault(relation_id, []).append(claim)
    projection_claims_by_relation_id: dict[str, list[KernelRelationClaim]] = {}
    if projection_claims_all:
        projection_claims_by_id = {
            str(claim.id): claim for claim in projection_claims_all
        }
        for relation in final_relations:
            relation_id = str(relation.id)
            projection_claims_by_relation_id[relation_id] = [
                projection_claims_by_id[str(row.claim_id)]
                for row in relation_projection_source_service.list_for_relation(
                    relation_id,
                )
                if str(row.claim_id) in projection_claims_by_id
            ]

    edges: list[KernelGraphDocumentEdge] = []
    for relation in final_relations:
        relation_id = str(relation.id)
        linked_claims = claims_by_relation_id.get(relation_id, [])
        projection_claims = projection_claims_by_relation_id.get(relation_id, [])
        support_count = len(projection_claims)
        refute_count = sum(1 for claim in linked_claims if claim.polarity == "REFUTE")
        edges.append(
            KernelGraphDocumentEdge(
                id=relation_id,
                resource_id=relation_id,
                kind="CANONICAL_RELATION",
                source_id=str(relation.source_id),
                target_id=str(relation.target_id),
                type_label=str(relation.relation_type),
                label=trim_label(str(relation.relation_type), "relation"),
                confidence=float(relation.aggregate_confidence),
                curation_status=str(relation.curation_status),
                claim_id=None,
                canonical_relation_id=relation.id,
                evidence_id=None,
                metadata={
                    "source_count": int(relation.source_count),
                    "highest_evidence_tier": relation.highest_evidence_tier,
                    "support_claim_count": support_count,
                    "refute_claim_count": refute_count,
                    "has_conflict": support_count > 0 and refute_count > 0,
                    "projection_claim_ids": [
                        str(claim.id) for claim in projection_claims
                    ],
                    "linked_claim_ids": [str(claim.id) for claim in linked_claims],
                    "explainable_by_projection": support_count > 0,
                },
                created_at=relation.created_at,
                updated_at=relation.updated_at,
            ),
        )

    for claim in selected_claims:
        claim_id = str(claim.id)
        claim_node_id = f"claim:{claim_id}"
        participants = participants_by_claim_id.get(claim_id, [])
        node_by_id[claim_node_id] = KernelGraphDocumentNode(
            id=claim_node_id,
            resource_id=claim_id,
            kind="CLAIM",
            type_label="CLAIM",
            label=trim_label(claim.claim_text, str(claim.relation_type)),
            confidence=float(claim.confidence),
            curation_status=None,
            claim_status=str(claim.claim_status),
            polarity=str(claim.polarity),
            canonical_relation_id=claim.linked_relation_id,
            metadata={
                "source_type": claim.source_type,
                "source_label": claim.source_label,
                "target_type": claim.target_type,
                "target_label": claim.target_label,
                "relation_type": claim.relation_type,
                "validation_state": claim.validation_state,
                "validation_reason": claim.validation_reason,
                "persistability": claim.persistability,
                "claim_text": claim.claim_text,
                "claim_section": claim.claim_section,
                "participant_count": len(participants),
            },
            created_at=claim.created_at,
            updated_at=claim.updated_at,
        )

        seen_roles: set[str] = set()
        for participant in participants:
            anchor_node_id = participant_anchor_node_id(
                participant=participant,
                claim=claim,
                node_by_id=node_by_id,
                entity_service=entity_service,
                space_id=space_id,
            )
            role = participant.role.strip().upper()
            seen_roles.add(role)
            edges.append(
                KernelGraphDocumentEdge(
                    id=f"claim-participant:{participant.id}",
                    resource_id=str(participant.id),
                    kind="CLAIM_PARTICIPANT",
                    source_id=anchor_node_id,
                    target_id=claim_node_id,
                    type_label=role,
                    label=role.title(),
                    confidence=float(claim.confidence),
                    curation_status=None,
                    claim_id=claim.id,
                    canonical_relation_id=claim.linked_relation_id,
                    evidence_id=None,
                    metadata={
                        "participant_label": participant.label,
                        "entity_id": (
                            str(participant.entity_id)
                            if participant.entity_id is not None
                            else None
                        ),
                        "position": participant.position,
                        "qualifiers": dict(participant.qualifiers),
                        "fallback": False,
                    },
                    created_at=participant.created_at,
                    updated_at=participant.updated_at or participant.created_at,
                ),
            )

        for fallback_role in ("SUBJECT", "OBJECT"):
            if fallback_role in seen_roles:
                continue
            anchor_node_id = fallback_claim_endpoint_anchor_node_id(
                role=fallback_role,
                claim=claim,
                relation_by_id=relation_by_id,
                node_by_id=node_by_id,
            )
            edges.append(
                KernelGraphDocumentEdge(
                    id=f"claim-participant:{claim_id}:{fallback_role.lower()}:fallback",
                    resource_id=None,
                    kind="CLAIM_PARTICIPANT",
                    source_id=anchor_node_id,
                    target_id=claim_node_id,
                    type_label=fallback_role,
                    label=fallback_role.title(),
                    confidence=float(claim.confidence),
                    curation_status=None,
                    claim_id=claim.id,
                    canonical_relation_id=claim.linked_relation_id,
                    evidence_id=None,
                    metadata={"fallback": True},
                    created_at=claim.created_at,
                    updated_at=claim.updated_at,
                ),
            )

        if not request.include_evidence:
            continue
        evidence_rows = evidence_by_claim_id.get(claim_id, [])[
            : request.evidence_limit_per_claim
        ]
        for evidence in evidence_rows:
            evidence_id = str(evidence.id)
            evidence_node_id = f"evidence:{evidence_id}"
            source_document = (
                source_documents_by_id.get(str(evidence.source_document_id))
                if evidence.source_document_id is not None
                else None
            )
            paper_links = resolve_claim_evidence_paper_links(
                source_document=source_document,
                evidence_metadata=evidence.metadata_payload,
            )
            paper_links_metadata: list[JSONObject] = [
                {
                    "label": link.label,
                    "url": link.url,
                    "source": link.source,
                }
                for link in paper_links
            ]
            node_by_id[evidence_node_id] = KernelGraphDocumentNode(
                id=evidence_node_id,
                resource_id=evidence_id,
                kind="EVIDENCE",
                type_label=evidence_node_type_label(evidence, paper_links_metadata),
                label=evidence_node_label(evidence, paper_links_metadata),
                confidence=float(evidence.confidence),
                curation_status=None,
                claim_status=None,
                polarity=None,
                canonical_relation_id=claim.linked_relation_id,
                metadata={
                    "claim_id": claim_id,
                    "source_document_id": (
                        str(evidence.source_document_id)
                        if evidence.source_document_id is not None
                        else None
                    ),
                    "sentence": evidence.sentence,
                    "sentence_source": evidence.sentence_source,
                    "sentence_confidence": evidence.sentence_confidence,
                    "sentence_rationale": evidence.sentence_rationale,
                    "figure_reference": evidence.figure_reference,
                    "table_reference": evidence.table_reference,
                    "paper_links": paper_links_metadata,
                    "raw_metadata": dict(evidence.metadata_payload),
                },
                created_at=evidence.created_at,
                updated_at=evidence.created_at,
            )
            edges.append(
                KernelGraphDocumentEdge(
                    id=f"claim-evidence:{evidence_id}",
                    resource_id=evidence_id,
                    kind="CLAIM_EVIDENCE",
                    source_id=claim_node_id,
                    target_id=evidence_node_id,
                    type_label="EVIDENCE",
                    label="Evidence",
                    confidence=float(evidence.confidence),
                    curation_status=None,
                    claim_id=claim.id,
                    canonical_relation_id=claim.linked_relation_id,
                    evidence_id=evidence.id,
                    metadata={"paper_links": paper_links_metadata},
                    created_at=evidence.created_at,
                    updated_at=evidence.created_at,
                ),
            )

    sorted_nodes = sorted(node_by_id.values(), key=node_sort_key)
    sorted_edges = sorted(edges, key=edge_sort_key)
    counts = KernelGraphDocumentCounts(
        entity_nodes=sum(1 for node in sorted_nodes if node.kind == "ENTITY"),
        claim_nodes=sum(1 for node in sorted_nodes if node.kind == "CLAIM"),
        evidence_nodes=sum(1 for node in sorted_nodes if node.kind == "EVIDENCE"),
        canonical_edges=sum(
            1 for edge in sorted_edges if edge.kind == "CANONICAL_RELATION"
        ),
        claim_participant_edges=sum(
            1 for edge in sorted_edges if edge.kind == "CLAIM_PARTICIPANT"
        ),
        claim_evidence_edges=sum(
            1 for edge in sorted_edges if edge.kind == "CLAIM_EVIDENCE"
        ),
    )
    return KernelGraphDocumentResponse(
        nodes=sorted_nodes,
        edges=sorted_edges,
        meta=KernelGraphDocumentMeta(
            mode=mode,
            seed_entity_ids=request.seed_entity_ids,
            requested_depth=request.depth,
            requested_top_k=request.top_k,
            pre_cap_entity_node_count=pre_cap_entity_node_count,
            pre_cap_canonical_edge_count=pre_cap_canonical_edge_count,
            truncated_entity_nodes=len(entity_nodes) < pre_cap_entity_node_count,
            truncated_canonical_edges=len(final_relations)
            < pre_cap_canonical_edge_count,
            included_claims=request.include_claims,
            included_evidence=request.include_claims and request.include_evidence,
            max_claims=request.max_claims,
            evidence_limit_per_claim=request.evidence_limit_per_claim,
            counts=counts,
        ),
    )


__all__ = ["build_kernel_graph_document"]
