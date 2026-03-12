"""Application service for derived reasoning paths."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING

from sqlalchemy import select

from src.domain.repositories.kernel.reasoning_path_repository import (
    KernelReasoningPathRepository,
    ReasoningPathStepWrite,
    ReasoningPathWrite,
    ReasoningPathWriteBundle,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.application.services.kernel.kernel_claim_evidence_service import (
        KernelClaimEvidenceService,
    )
    from src.application.services.kernel.kernel_claim_participant_service import (
        KernelClaimParticipantService,
    )
    from src.application.services.kernel.kernel_claim_relation_service import (
        KernelClaimRelationService,
    )
    from src.application.services.kernel.kernel_relation_claim_service import (
        KernelRelationClaimService,
    )
    from src.application.services.kernel.kernel_relation_service import (
        KernelRelationService,
    )
    from src.domain.entities.kernel.claim_evidence import KernelClaimEvidence
    from src.domain.entities.kernel.claim_participants import KernelClaimParticipant
    from src.domain.entities.kernel.claim_relations import KernelClaimRelation
    from src.domain.entities.kernel.reasoning_paths import (
        KernelReasoningPath,
        KernelReasoningPathStep,
        ReasoningPathKind,
        ReasoningPathStatus,
    )
    from src.domain.entities.kernel.relation_claims import KernelRelationClaim
    from src.domain.entities.kernel.relations import KernelRelation
    from src.type_definitions.common import JSONValue


_ALLOWED_PATH_RELATION_TYPES = frozenset(
    {
        "CAUSES",
        "UPSTREAM_OF",
        "DOWNSTREAM_OF",
        "REFINES",
        "SUPPORTS",
        "GENERALIZES",
        "INSTANCE_OF",
    },
)


@dataclass(frozen=True)
class ReasoningPathListResult:
    """Paginated reasoning-path listing."""

    paths: tuple[KernelReasoningPath, ...]
    total: int
    offset: int
    limit: int


@dataclass(frozen=True)
class ReasoningPathRebuildSummary:
    """Summary of one reasoning-path rebuild run."""

    research_space_id: str
    eligible_claims: int
    accepted_claim_relations: int
    rebuilt_paths: int
    max_depth: int


@dataclass(frozen=True)
class KernelReasoningPathDetail:
    """Fully expanded reasoning-path read model."""

    path: KernelReasoningPath
    steps: tuple[KernelReasoningPathStep, ...]
    claims: tuple[KernelRelationClaim, ...]
    claim_relations: tuple[KernelClaimRelation, ...]
    canonical_relations: tuple[KernelRelation, ...]
    participants: tuple[KernelClaimParticipant, ...]
    evidence: tuple[KernelClaimEvidence, ...]


class KernelReasoningPathService:
    """Build and serve derived mechanism paths from grounded claim chains."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        reasoning_path_repo: KernelReasoningPathRepository,
        relation_claim_service: KernelRelationClaimService,
        claim_participant_service: KernelClaimParticipantService,
        claim_evidence_service: KernelClaimEvidenceService,
        claim_relation_service: KernelClaimRelationService,
        relation_service: KernelRelationService,
        session: Session | None = None,
    ) -> None:
        self._paths = reasoning_path_repo
        self._claims = relation_claim_service
        self._participants = claim_participant_service
        self._evidence = claim_evidence_service
        self._claim_relations = claim_relation_service
        self._relations = relation_service
        self._session = session

    def rebuild_for_space(
        self,
        research_space_id: str,
        *,
        max_depth: int = 4,
        replace_existing: bool = True,
    ) -> ReasoningPathRebuildSummary:
        grounded_claims = self._claims.list_by_research_space(
            research_space_id,
            claim_status="RESOLVED",
            persistability="PERSISTABLE",
            polarity="SUPPORT",
        )
        claim_ids = [str(claim.id) for claim in grounded_claims]
        participant_map = self._participants.list_for_claim_ids(claim_ids)
        evidence_map = self._evidence.list_for_claim_ids(claim_ids)

        eligible_claim_map: dict[str, KernelRelationClaim] = {}
        participant_anchor_map: dict[str, tuple[str, str]] = {}
        for claim in grounded_claims:
            claim_id = str(claim.id)
            participants = participant_map.get(claim_id, [])
            anchors = _resolve_participant_anchor_entities(participants)
            if anchors is None:
                continue
            if not evidence_map.get(claim_id):
                continue
            eligible_claim_map[claim_id] = claim
            participant_anchor_map[claim_id] = anchors

        accepted_relations = [
            relation
            for relation in self._claim_relations.list_by_research_space(
                research_space_id,
                review_status="ACCEPTED",
            )
            if relation.relation_type in _ALLOWED_PATH_RELATION_TYPES
            and str(relation.source_claim_id) in eligible_claim_map
            and str(relation.target_claim_id) in eligible_claim_map
        ]

        adjacency: dict[str, list[KernelClaimRelation]] = defaultdict(list)
        for relation in accepted_relations:
            adjacency[str(relation.source_claim_id)].append(relation)
        for relations in adjacency.values():
            relations.sort(
                key=lambda relation: (
                    -float(relation.confidence),
                    str(relation.target_claim_id),
                    str(relation.id),
                ),
            )

        bundles_by_signature: dict[str, ReasoningPathWriteBundle] = {}
        normalized_depth = max(1, min(4, int(max_depth)))
        for root_claim_id in sorted(eligible_claim_map):
            self._collect_paths_from_root(
                research_space_id=research_space_id,
                root_claim_id=root_claim_id,
                eligible_claim_map=eligible_claim_map,
                participant_anchor_map=participant_anchor_map,
                adjacency=adjacency,
                max_depth=normalized_depth,
                bundles_by_signature=bundles_by_signature,
            )

        persisted = self._paths.replace_for_space(
            research_space_id=research_space_id,
            bundles=list(bundles_by_signature.values()),
            replace_existing=replace_existing,
        )
        return ReasoningPathRebuildSummary(
            research_space_id=research_space_id,
            eligible_claims=len(eligible_claim_map),
            accepted_claim_relations=len(accepted_relations),
            rebuilt_paths=len(persisted),
            max_depth=normalized_depth,
        )

    def rebuild_global(
        self,
        *,
        max_depth: int = 4,
    ) -> list[ReasoningPathRebuildSummary]:
        if self._session is None:
            msg = "Session-backed global rebuild is unavailable"
            raise ValueError(msg)
        from src.models.database.research_space import ResearchSpaceModel

        space_rows = self._session.scalars(
            select(ResearchSpaceModel.id).order_by(ResearchSpaceModel.id.asc()),
        ).all()
        space_ids = [str(space_id) for space_id in space_rows]
        return [
            self.rebuild_for_space(space_id, max_depth=max_depth, replace_existing=True)
            for space_id in space_ids
        ]

    def list_paths(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        start_entity_id: str | None = None,
        end_entity_id: str | None = None,
        status: ReasoningPathStatus | None = None,
        path_kind: ReasoningPathKind | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ReasoningPathListResult:
        normalized_limit = max(1, min(200, int(limit)))
        normalized_offset = max(0, int(offset))
        paths = self._paths.list_paths(
            research_space_id=research_space_id,
            start_entity_id=start_entity_id,
            end_entity_id=end_entity_id,
            status=status,
            path_kind=path_kind,
            limit=normalized_limit,
            offset=normalized_offset,
        )
        total = self._paths.count_paths(
            research_space_id=research_space_id,
            start_entity_id=start_entity_id,
            end_entity_id=end_entity_id,
            status=status,
            path_kind=path_kind,
        )
        return ReasoningPathListResult(
            paths=tuple(paths),
            total=total,
            offset=normalized_offset,
            limit=normalized_limit,
        )

    def get_path(
        self,
        path_id: str,
        research_space_id: str,
    ) -> KernelReasoningPathDetail | None:
        path = self._paths.get_path(
            path_id=path_id,
            research_space_id=research_space_id,
        )
        if path is None:
            return None
        steps = self._paths.list_steps_for_path_ids(path_ids=[str(path.id)]).get(
            str(path.id),
            [],
        )
        ordered_claim_ids = _resolve_ordered_claim_ids(path=path, steps=steps)
        claims = self._claims.list_claims_by_ids(ordered_claim_ids)
        claims_by_id = {str(claim.id): claim for claim in claims}
        ordered_claims = tuple(
            claims_by_id[claim_id]
            for claim_id in ordered_claim_ids
            if claim_id in claims_by_id
        )

        claim_relation_ids = [str(step.claim_relation_id) for step in steps]
        claim_relations = tuple(
            relation
            for relation_id in claim_relation_ids
            if (relation := self._claim_relations.get_claim_relation(relation_id))
            is not None
        )

        participant_map = self._participants.list_for_claim_ids(ordered_claim_ids)
        evidence_map = self._evidence.list_for_claim_ids(ordered_claim_ids)
        participants = tuple(
            participant
            for claim_id in ordered_claim_ids
            for participant in participant_map.get(claim_id, [])
        )
        evidence = tuple(
            evidence_row
            for claim_id in ordered_claim_ids
            for evidence_row in evidence_map.get(claim_id, [])
        )

        canonical_relation_ids = _resolve_ordered_canonical_relation_ids(
            steps=steps,
            claims=ordered_claims,
        )
        canonical_relations_list: list[KernelRelation] = []
        for relation_id in canonical_relation_ids:
            canonical_relation = self._relations.get_relation(
                relation_id,
                claim_backed_only=True,
            )
            if canonical_relation is None:
                continue
            canonical_relations_list.append(canonical_relation)
        canonical_relations = tuple(canonical_relations_list)

        return KernelReasoningPathDetail(
            path=path,
            steps=tuple(steps),
            claims=ordered_claims,
            claim_relations=claim_relations,
            canonical_relations=canonical_relations,
            participants=participants,
            evidence=evidence,
        )

    def mark_stale_for_claim_ids(
        self,
        claim_ids: list[str],
        research_space_id: str,
    ) -> int:
        return self._paths.mark_stale_for_claim_ids(
            research_space_id=research_space_id,
            claim_ids=claim_ids,
        )

    def mark_stale_for_claim_relation_ids(
        self,
        relation_ids: list[str],
        research_space_id: str,
    ) -> int:
        return self._paths.mark_stale_for_claim_relation_ids(
            research_space_id=research_space_id,
            relation_ids=relation_ids,
        )

    def _collect_paths_from_root(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        root_claim_id: str,
        eligible_claim_map: dict[str, KernelRelationClaim],
        participant_anchor_map: dict[str, tuple[str, str]],
        adjacency: dict[str, list[KernelClaimRelation]],
        max_depth: int,
        bundles_by_signature: dict[str, ReasoningPathWriteBundle],
    ) -> None:
        def _walk(
            current_claim_id: str,
            visited_claim_ids: tuple[str, ...],
            traversed_relations: tuple[KernelClaimRelation, ...],
        ) -> None:
            if traversed_relations:
                bundle = _build_bundle(
                    research_space_id=research_space_id,
                    root_claim_id=root_claim_id,
                    claim_ids=visited_claim_ids,
                    traversed_relations=traversed_relations,
                    claim_map=eligible_claim_map,
                    participant_anchor_map=participant_anchor_map,
                )
                bundles_by_signature.setdefault(
                    bundle.path.path_signature_hash,
                    bundle,
                )
            if len(traversed_relations) >= max_depth:
                return
            for relation in adjacency.get(current_claim_id, []):
                next_claim_id = str(relation.target_claim_id)
                if next_claim_id in visited_claim_ids:
                    continue
                _walk(
                    next_claim_id,
                    (*visited_claim_ids, next_claim_id),
                    (*traversed_relations, relation),
                )

        _walk(root_claim_id, (root_claim_id,), ())


def _resolve_participant_anchor_entities(
    participants: list[KernelClaimParticipant],
) -> tuple[str, str] | None:
    subject_entity_id: str | None = None
    object_entity_id: str | None = None
    for participant in participants:
        if participant.entity_id is None:
            continue
        participant_entity_id = str(participant.entity_id)
        if participant.role == "SUBJECT" and subject_entity_id is None:
            subject_entity_id = participant_entity_id
        if participant.role == "OBJECT" and object_entity_id is None:
            object_entity_id = participant_entity_id
    if subject_entity_id is None or object_entity_id is None:
        return None
    return subject_entity_id, object_entity_id


def _build_bundle(  # noqa: PLR0913
    *,
    research_space_id: str,
    root_claim_id: str,
    claim_ids: tuple[str, ...],
    traversed_relations: tuple[KernelClaimRelation, ...],
    claim_map: dict[str, KernelRelationClaim],
    participant_anchor_map: dict[str, tuple[str, str]],
) -> ReasoningPathWriteBundle:
    start_entity_id = participant_anchor_map[root_claim_id][0]
    last_claim_id = claim_ids[-1]
    end_entity_id = participant_anchor_map[last_claim_id][1]
    path_confidence = min(
        max(0.0, min(1.0, float(relation.confidence)))
        for relation in traversed_relations
    )
    claim_relation_ids = [str(relation.id) for relation in traversed_relations]
    signature_hash = _build_signature_hash(
        claim_ids=claim_ids,
        claim_relation_ids=claim_relation_ids,
    )
    terminal_claim = claim_map[last_claim_id]
    metadata: dict[str, JSONValue] = {
        "supporting_claim_ids": list(claim_ids),
        "claim_relation_ids": claim_relation_ids,
        "start_claim_id": root_claim_id,
        "end_claim_id": last_claim_id,
        "terminal_relation_type": str(terminal_claim.relation_type),
    }
    steps = tuple(
        ReasoningPathStepWrite(
            step_index=index,
            source_claim_id=str(relation.source_claim_id),
            target_claim_id=str(relation.target_claim_id),
            claim_relation_id=str(relation.id),
            canonical_relation_id=_resolve_step_canonical_relation_id(
                source_claim=claim_map[str(relation.source_claim_id)],
                target_claim=claim_map[str(relation.target_claim_id)],
            ),
            metadata={
                "relation_type": str(relation.relation_type),
                "confidence": float(relation.confidence),
            },
        )
        for index, relation in enumerate(traversed_relations)
    )
    return ReasoningPathWriteBundle(
        path=ReasoningPathWrite(
            research_space_id=research_space_id,
            path_kind="MECHANISM",
            status="ACTIVE",
            start_entity_id=start_entity_id,
            end_entity_id=end_entity_id,
            root_claim_id=root_claim_id,
            path_length=len(traversed_relations),
            confidence=path_confidence,
            path_signature_hash=signature_hash,
            generated_by="kernel_reasoning_path_service",
            metadata=metadata,
        ),
        steps=steps,
    )


def _build_signature_hash(
    *,
    claim_ids: tuple[str, ...],
    claim_relation_ids: list[str],
) -> str:
    payload = json.dumps(
        {
            "claim_ids": list(claim_ids),
            "claim_relation_ids": claim_relation_ids,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _resolve_step_canonical_relation_id(
    *,
    source_claim: KernelRelationClaim,
    target_claim: KernelRelationClaim,
) -> str | None:
    if source_claim.linked_relation_id is not None:
        return str(source_claim.linked_relation_id)
    if target_claim.linked_relation_id is not None:
        return str(target_claim.linked_relation_id)
    return None


def _resolve_ordered_claim_ids(
    *,
    path: KernelReasoningPath,
    steps: list[KernelReasoningPathStep],
) -> list[str]:
    claim_ids = [str(path.root_claim_id)]
    seen = {str(path.root_claim_id)}
    for step in steps:
        source_claim_id = str(step.source_claim_id)
        target_claim_id = str(step.target_claim_id)
        if source_claim_id not in seen:
            claim_ids.append(source_claim_id)
            seen.add(source_claim_id)
        if target_claim_id not in seen:
            claim_ids.append(target_claim_id)
            seen.add(target_claim_id)
    return claim_ids


def _resolve_ordered_canonical_relation_ids(
    *,
    steps: tuple[KernelReasoningPathStep, ...] | list[KernelReasoningPathStep],
    claims: tuple[KernelRelationClaim, ...],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for step in steps:
        if step.canonical_relation_id is None:
            continue
        relation_id = str(step.canonical_relation_id)
        if relation_id in seen:
            continue
        seen.add(relation_id)
        ordered.append(relation_id)
    for claim in claims:
        if claim.linked_relation_id is None:
            continue
        relation_id = str(claim.linked_relation_id)
        if relation_id in seen:
            continue
        seen.add(relation_id)
        ordered.append(relation_id)
    return ordered


__all__ = [
    "KernelReasoningPathDetail",
    "KernelReasoningPathService",
    "ReasoningPathListResult",
    "ReasoningPathRebuildSummary",
]
