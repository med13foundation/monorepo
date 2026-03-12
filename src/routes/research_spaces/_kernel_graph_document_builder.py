"""Helpers to build unified graph documents with claim/evidence overlays."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.application.services.kernel import (
    KernelClaimEvidenceService,
    KernelClaimParticipantService,
    KernelEntityService,
    KernelRelationClaimService,
    KernelRelationService,
)
from src.domain.entities.kernel.claim_evidence import KernelClaimEvidence
from src.domain.entities.kernel.claim_participants import KernelClaimParticipant
from src.domain.entities.kernel.relation_claims import KernelRelationClaim
from src.domain.entities.kernel.relations import KernelRelation
from src.models.database.source_document import SourceDocumentModel
from src.routes.research_spaces._claim_evidence_paper_links import (
    resolve_claim_evidence_paper_links,
)
from src.routes.research_spaces._kernel_relation_subgraph_helpers import (
    collect_candidate_relations,
    limit_relations_to_anchor_component,
    materialize_nodes,
    ordered_node_ids_for_relations,
)
from src.routes.research_spaces.kernel_schemas import (
    KernelEntityResponse,
    KernelGraphDocumentCounts,
    KernelGraphDocumentEdge,
    KernelGraphDocumentMeta,
    KernelGraphDocumentNode,
    KernelGraphDocumentRequest,
    KernelGraphDocumentResponse,
)
from src.type_definitions.common import JSONObject

_CURATION_STATUS_ALIAS: dict[str, str] = {"PENDING_REVIEW": "DRAFT"}
_NODE_KIND_PRIORITY: dict[str, int] = {"ENTITY": 0, "CLAIM": 1, "EVIDENCE": 2}
_EDGE_KIND_PRIORITY: dict[str, int] = {
    "CANONICAL_RELATION": 0,
    "CLAIM_PARTICIPANT": 1,
    "CLAIM_EVIDENCE": 2,
}


def _normalize_filter_values(values: list[str] | None) -> set[str] | None:
    if values is None:
        return None
    normalized = {value.strip().upper() for value in values if value.strip()}
    return normalized or None


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


def _trim_label(value: str | None, fallback: str) -> str:
    label = (value or "").strip()
    if not label:
        label = fallback
    return label[:512]


def _participant_type_label(role: str, claim: KernelRelationClaim) -> str:
    normalized_role = role.strip().upper()
    if normalized_role == "SUBJECT":
        return claim.source_type.strip().upper()
    if normalized_role in {"OBJECT", "OUTCOME"}:
        return claim.target_type.strip().upper()
    return normalized_role


def _participant_label(
    participant: KernelClaimParticipant | None,
    *,
    role: str,
    claim: KernelRelationClaim,
) -> str:
    if participant is not None and participant.label is not None:
        normalized = participant.label.strip()
        if normalized:
            return normalized
    normalized_role = role.strip().upper()
    if normalized_role == "SUBJECT":
        return _trim_label(claim.source_label, claim.source_type)
    if normalized_role in {"OBJECT", "OUTCOME"}:
        return _trim_label(claim.target_label, claim.target_type)
    return normalized_role.title()


def _source_document_lookup(
    *,
    session: Session,
    evidence_rows: Iterable[KernelClaimEvidence],
) -> dict[str, SourceDocumentModel]:
    source_document_ids = {
        str(evidence_row.source_document_id)
        for evidence_row in evidence_rows
        if evidence_row.source_document_id is not None
    }
    if not source_document_ids:
        return {}
    source_documents = session.scalars(
        select(SourceDocumentModel).where(
            SourceDocumentModel.id.in_(source_document_ids),
        ),
    ).all()
    return {
        str(source_document.id): source_document for source_document in source_documents
    }


def _node_sort_key(node: KernelGraphDocumentNode) -> tuple[int, float, str]:
    return (
        _NODE_KIND_PRIORITY.get(node.kind, 99),
        -node.updated_at.timestamp(),
        node.id,
    )


def _edge_sort_key(edge: KernelGraphDocumentEdge) -> tuple[int, float, str]:
    return (
        _EDGE_KIND_PRIORITY.get(edge.kind, 99),
        -edge.updated_at.timestamp(),
        edge.id,
    )


def _claim_sort_key(claim: KernelRelationClaim) -> tuple[float, float]:
    return (claim.updated_at.timestamp(), float(claim.confidence))


def _selected_claims(
    claims: list[KernelRelationClaim],
    *,
    max_claims: int,
) -> list[KernelRelationClaim]:
    ordered = sorted(claims, key=_claim_sort_key, reverse=True)
    return ordered[:max_claims]


def _evidence_node_type_label(
    evidence: KernelClaimEvidence,
    paper_links_metadata: list[JSONObject],
) -> str:
    metadata = evidence.metadata_payload
    if isinstance(metadata, dict):
        for dataset_key in (
            "dataset_id",
            "dataset_accession",
            "dataset_name",
            "geo_accession",
            "gse_id",
        ):
            value = metadata.get(dataset_key)
            if isinstance(value, str) and value.strip():
                return "DATASET_EVIDENCE"
    if paper_links_metadata:
        return "PAPER_EVIDENCE"
    return "EVIDENCE"


def _evidence_node_label(
    evidence: KernelClaimEvidence,
    paper_links_metadata: list[JSONObject],
) -> str:
    if isinstance(evidence.sentence, str) and evidence.sentence.strip():
        return _trim_label(evidence.sentence, f"Evidence {evidence.id}")
    for link in paper_links_metadata:
        raw_label = link.get("label")
        if isinstance(raw_label, str) and raw_label.strip():
            return _trim_label(raw_label, f"Evidence {evidence.id}")
    return f"Evidence {str(evidence.id)[:8]}"


def _graph_entity_node(entity: KernelEntityResponse) -> KernelGraphDocumentNode:
    return KernelGraphDocumentNode(
        id=str(entity.id),
        resource_id=str(entity.id),
        kind="ENTITY",
        type_label=entity.entity_type,
        label=_trim_label(entity.display_label, str(entity.id)),
        confidence=None,
        curation_status=None,
        claim_status=None,
        polarity=None,
        canonical_relation_id=None,
        metadata=dict(entity.metadata),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _ensure_entity_anchor_node(
    *,
    node_by_id: dict[str, KernelGraphDocumentNode],
    entity_id: str,
    entity_service: KernelEntityService,
    space_id: str,
) -> str | None:
    if entity_id in node_by_id:
        return entity_id
    entity = entity_service.get_entity(entity_id)
    if entity is None or str(entity.research_space_id) != space_id:
        return None
    node_by_id[entity_id] = _graph_entity_node(KernelEntityResponse.from_model(entity))
    return entity_id


def _ensure_synthetic_entity_anchor_node(
    *,
    node_by_id: dict[str, KernelGraphDocumentNode],
    node_id: str,
    type_label: str,
    label: str,
    created_at: datetime,
    updated_at: datetime,
    metadata: JSONObject | None = None,
) -> str:
    if node_id not in node_by_id:
        node_by_id[node_id] = KernelGraphDocumentNode(
            id=node_id,
            resource_id=node_id,
            kind="ENTITY",
            type_label=type_label,
            label=_trim_label(label, type_label),
            confidence=None,
            curation_status=None,
            claim_status=None,
            polarity=None,
            canonical_relation_id=None,
            metadata={} if metadata is None else dict(metadata),
            created_at=created_at,
            updated_at=updated_at,
        )
    return node_id


def _participant_anchor_node_id(
    *,
    participant: KernelClaimParticipant,
    claim: KernelRelationClaim,
    node_by_id: dict[str, KernelGraphDocumentNode],
    entity_service: KernelEntityService,
    space_id: str,
) -> str:
    if participant.entity_id is not None:
        anchor_id = _ensure_entity_anchor_node(
            node_by_id=node_by_id,
            entity_id=str(participant.entity_id),
            entity_service=entity_service,
            space_id=space_id,
        )
        if anchor_id is not None:
            return anchor_id
    synthetic_node_id = (
        f"claim-anchor:{claim.id}:{participant.role.lower()}:{participant.id}"
    )
    return _ensure_synthetic_entity_anchor_node(
        node_by_id=node_by_id,
        node_id=synthetic_node_id,
        type_label=_participant_type_label(participant.role, claim),
        label=_participant_label(participant, role=participant.role, claim=claim),
        created_at=claim.created_at,
        updated_at=claim.updated_at,
        metadata={
            "synthetic": True,
            "anchor_source": "claim_participant",
            "role": participant.role,
        },
    )


def _fallback_claim_endpoint_anchor_node_id(
    *,
    role: str,
    claim: KernelRelationClaim,
    relation_by_id: dict[str, KernelRelation],
    node_by_id: dict[str, KernelGraphDocumentNode],
) -> str:
    linked_relation = (
        relation_by_id.get(str(claim.linked_relation_id))
        if claim.linked_relation_id is not None
        else None
    )
    normalized_role = role.strip().upper()
    if linked_relation is not None:
        if normalized_role == "SUBJECT":
            return str(linked_relation.source_id)
        return str(linked_relation.target_id)
    node_id = f"claim-anchor:{claim.id}:{normalized_role.lower()}:fallback"
    return _ensure_synthetic_entity_anchor_node(
        node_by_id=node_by_id,
        node_id=node_id,
        type_label=_participant_type_label(normalized_role, claim),
        label=_participant_label(None, role=normalized_role, claim=claim),
        created_at=claim.created_at,
        updated_at=claim.updated_at,
        metadata={
            "synthetic": True,
            "anchor_source": "claim_endpoint_fallback",
            "role": normalized_role,
        },
    )


def build_kernel_graph_document(  # noqa: PLR0912, PLR0913, PLR0915
    *,
    space_id: str,
    request: KernelGraphDocumentRequest,
    entity_service: KernelEntityService,
    relation_service: KernelRelationService,
    relation_claim_service: KernelRelationClaimService,
    claim_participant_service: KernelClaimParticipantService,
    claim_evidence_service: KernelClaimEvidenceService,
    session: Session,
) -> KernelGraphDocumentResponse:
    relation_types = _normalize_filter_values(request.relation_types)
    curation_statuses = _normalize_curation_status_filters(request.curation_statuses)
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
        str(entity.id): _graph_entity_node(entity) for entity in entity_nodes
    }
    relation_by_id = {str(relation.id): relation for relation in final_relations}

    linked_claims_all: list[KernelRelationClaim] = []
    if request.include_claims and final_relations:
        linked_claims_all = relation_claim_service.list_by_linked_relation_ids(
            research_space_id=space_id,
            linked_relation_ids=[str(relation.id) for relation in final_relations],
        )

    selected_claims = (
        _selected_claims(linked_claims_all, max_claims=request.max_claims)
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
    source_documents_by_id = _source_document_lookup(
        session=session,
        evidence_rows=all_selected_evidence_rows,
    )

    claims_by_relation_id: dict[str, list[KernelRelationClaim]] = {}
    for claim in linked_claims_all:
        if claim.linked_relation_id is None:
            continue
        relation_id = str(claim.linked_relation_id)
        claims_by_relation_id.setdefault(relation_id, []).append(claim)

    edges: list[KernelGraphDocumentEdge] = []
    for relation in final_relations:
        relation_id = str(relation.id)
        linked_claims = claims_by_relation_id.get(relation_id, [])
        support_count = sum(1 for claim in linked_claims if claim.polarity == "SUPPORT")
        refute_count = sum(1 for claim in linked_claims if claim.polarity == "REFUTE")
        edges.append(
            KernelGraphDocumentEdge(
                id=relation_id,
                resource_id=relation_id,
                kind="CANONICAL_RELATION",
                source_id=str(relation.source_id),
                target_id=str(relation.target_id),
                type_label=str(relation.relation_type),
                label=_trim_label(str(relation.relation_type), "relation"),
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
                    "linked_claim_ids": [str(claim.id) for claim in linked_claims],
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
            label=_trim_label(claim.claim_text, str(claim.relation_type)),
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
            anchor_node_id = _participant_anchor_node_id(
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
            anchor_node_id = _fallback_claim_endpoint_anchor_node_id(
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
                type_label=_evidence_node_type_label(evidence, paper_links_metadata),
                label=_evidence_node_label(evidence, paper_links_metadata),
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

    sorted_nodes = sorted(node_by_id.values(), key=_node_sort_key)
    sorted_edges = sorted(edges, key=_edge_sort_key)
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
