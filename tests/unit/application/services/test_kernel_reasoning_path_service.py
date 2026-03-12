"""Unit tests for derived reasoning-path service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from src.application.services.kernel.kernel_reasoning_path_service import (
    KernelReasoningPathService,
)
from src.domain.entities.kernel.claim_evidence import KernelClaimEvidence
from src.domain.entities.kernel.claim_participants import KernelClaimParticipant
from src.domain.entities.kernel.claim_relations import KernelClaimRelation
from src.domain.entities.kernel.reasoning_paths import (
    KernelReasoningPath,
    KernelReasoningPathStep,
)
from src.domain.entities.kernel.relation_claims import KernelRelationClaim
from src.domain.entities.kernel.relations import KernelRelation
from src.domain.repositories.kernel.reasoning_path_repository import (
    ReasoningPathStepWrite,
    ReasoningPathWrite,
    ReasoningPathWriteBundle,
)

pytestmark = pytest.mark.graph

if TYPE_CHECKING:
    from src.domain.entities.kernel.reasoning_paths import (
        ReasoningPathKind,
        ReasoningPathStatus,
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _build_claim(  # noqa: PLR0913
    *,
    claim_id: UUID,
    research_space_id: UUID,
    relation_type: str,
    linked_relation_id: UUID | None = None,
    claim_status: str = "RESOLVED",
    persistability: str = "PERSISTABLE",
    polarity: str = "SUPPORT",
) -> KernelRelationClaim:
    now = _now()
    return KernelRelationClaim(
        id=claim_id,
        research_space_id=research_space_id,
        source_document_id=None,
        agent_run_id=None,
        source_type="GENE",
        relation_type=relation_type,
        target_type="PHENOTYPE",
        source_label="Source",
        target_label="Target",
        confidence=0.9,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability=persistability,  # type: ignore[arg-type]
        claim_status=claim_status,  # type: ignore[arg-type]
        polarity=polarity,  # type: ignore[arg-type]
        claim_text="claim",
        claim_section=None,
        linked_relation_id=linked_relation_id,
        metadata_payload={},
        triaged_by=None,
        triaged_at=None,
        created_at=now,
        updated_at=now,
    )


def _build_participant(
    *,
    claim_id: UUID,
    research_space_id: UUID,
    role: str,
    entity_id: UUID,
    position: int,
) -> KernelClaimParticipant:
    now = _now()
    return KernelClaimParticipant(
        id=uuid4(),
        claim_id=claim_id,
        research_space_id=research_space_id,
        label=None,
        entity_id=entity_id,
        role=role,  # type: ignore[arg-type]
        position=position,
        qualifiers={},
        created_at=now,
        updated_at=now,
    )


def _build_evidence(*, claim_id: UUID) -> KernelClaimEvidence:
    return KernelClaimEvidence(
        id=uuid4(),
        claim_id=claim_id,
        source_document_id=None,
        agent_run_id=None,
        sentence="evidence",
        sentence_source="verbatim_span",
        sentence_confidence="high",
        sentence_rationale=None,
        figure_reference=None,
        table_reference=None,
        confidence=0.8,
        metadata_payload={},
        created_at=_now(),
    )


def _build_claim_relation(
    *,
    relation_id: UUID,
    research_space_id: UUID,
    source_claim_id: UUID,
    target_claim_id: UUID,
    relation_type: str = "CAUSES",
    confidence: float = 0.7,
    review_status: str = "ACCEPTED",
) -> KernelClaimRelation:
    now = _now()
    return KernelClaimRelation(
        id=relation_id,
        research_space_id=research_space_id,
        source_claim_id=source_claim_id,
        target_claim_id=target_claim_id,
        relation_type=relation_type,  # type: ignore[arg-type]
        agent_run_id=None,
        source_document_id=None,
        confidence=confidence,
        review_status=review_status,  # type: ignore[arg-type]
        evidence_summary=None,
        metadata_payload={},
        created_at=now,
        updated_at=now,
    )


def _build_relation(
    *,
    relation_id: UUID,
    research_space_id: UUID,
) -> KernelRelation:
    now = _now()
    return KernelRelation(
        id=relation_id,
        research_space_id=research_space_id,
        source_id=uuid4(),
        relation_type="ASSOCIATED_WITH",
        target_id=uuid4(),
        aggregate_confidence=0.8,
        source_count=1,
        highest_evidence_tier="COMPUTATIONAL",
        curation_status="DRAFT",
        provenance_id=None,
        reviewed_by=None,
        reviewed_at=None,
        created_at=now,
        updated_at=now,
    )


@dataclass
class StubReasoningPathRepository:
    stored_paths: dict[str, KernelReasoningPath] = field(default_factory=dict)
    stored_steps: dict[str, list[KernelReasoningPathStep]] = field(default_factory=dict)

    def replace_for_space(
        self,
        *,
        research_space_id: str,
        bundles: list[ReasoningPathWriteBundle],
        replace_existing: bool,
    ) -> list[KernelReasoningPath]:
        if replace_existing:
            self.stored_paths = {
                path_id: path
                for path_id, path in self.stored_paths.items()
                if str(path.research_space_id) != research_space_id
            }
            self.stored_steps = {
                path_id: steps
                for path_id, steps in self.stored_steps.items()
                if path_id in self.stored_paths
            }
        created: list[KernelReasoningPath] = []
        now = _now()
        for bundle in bundles:
            path_id = uuid4()
            path = KernelReasoningPath(
                id=path_id,
                research_space_id=UUID(bundle.path.research_space_id),
                path_kind=bundle.path.path_kind,
                status=bundle.path.status,
                start_entity_id=UUID(bundle.path.start_entity_id),
                end_entity_id=UUID(bundle.path.end_entity_id),
                root_claim_id=UUID(bundle.path.root_claim_id),
                path_length=bundle.path.path_length,
                confidence=bundle.path.confidence,
                path_signature_hash=bundle.path.path_signature_hash,
                generated_by=bundle.path.generated_by,
                generated_at=now,
                metadata_payload=bundle.path.metadata,
                created_at=now,
                updated_at=now,
            )
            steps = [
                KernelReasoningPathStep(
                    id=uuid4(),
                    path_id=path_id,
                    step_index=step.step_index,
                    source_claim_id=UUID(step.source_claim_id),
                    target_claim_id=UUID(step.target_claim_id),
                    claim_relation_id=UUID(step.claim_relation_id),
                    canonical_relation_id=(
                        UUID(step.canonical_relation_id)
                        if step.canonical_relation_id is not None
                        else None
                    ),
                    metadata_payload=step.metadata,
                    created_at=now,
                )
                for step in bundle.steps
            ]
            self.stored_paths[str(path_id)] = path
            self.stored_steps[str(path_id)] = steps
            created.append(path)
        return created

    def list_paths(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        start_entity_id: str | None = None,
        end_entity_id: str | None = None,
        status: ReasoningPathStatus | None = None,
        path_kind: ReasoningPathKind | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelReasoningPath]:
        del offset
        paths = [
            path
            for path in self.stored_paths.values()
            if str(path.research_space_id) == research_space_id
            and (
                start_entity_id is None or str(path.start_entity_id) == start_entity_id
            )
            and (end_entity_id is None or str(path.end_entity_id) == end_entity_id)
            and (status is None or path.status == status)
            and (path_kind is None or path.path_kind == path_kind)
        ]
        paths.sort(key=lambda item: (-item.confidence, item.path_length, str(item.id)))
        if limit is not None:
            return paths[:limit]
        return paths

    def count_paths(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        start_entity_id: str | None = None,
        end_entity_id: str | None = None,
        status: ReasoningPathStatus | None = None,
        path_kind: ReasoningPathKind | None = None,
    ) -> int:
        return len(
            self.list_paths(
                research_space_id=research_space_id,
                start_entity_id=start_entity_id,
                end_entity_id=end_entity_id,
                status=status,
                path_kind=path_kind,
            ),
        )

    def get_path(
        self,
        *,
        path_id: str,
        research_space_id: str,
    ) -> KernelReasoningPath | None:
        path = self.stored_paths.get(path_id)
        if path is None or str(path.research_space_id) != research_space_id:
            return None
        return path

    def list_steps_for_path_ids(
        self,
        *,
        path_ids: list[str],
    ) -> dict[str, list[KernelReasoningPathStep]]:
        return {
            path_id: list(self.stored_steps.get(path_id, [])) for path_id in path_ids
        }

    def mark_stale_for_claim_ids(
        self,
        *,
        research_space_id: str,
        claim_ids: list[str],
    ) -> int:
        touched = 0
        for path_id, path in list(self.stored_paths.items()):
            if str(path.research_space_id) != research_space_id:
                continue
            step_rows = self.stored_steps.get(path_id, [])
            step_claim_ids = {str(step.source_claim_id) for step in step_rows} | {
                str(step.target_claim_id) for step in step_rows
            }
            if str(path.root_claim_id) in claim_ids or step_claim_ids.intersection(
                claim_ids,
            ):
                self.stored_paths[path_id] = path.model_copy(update={"status": "STALE"})
                touched += 1
        return touched

    def mark_stale_for_claim_relation_ids(
        self,
        *,
        research_space_id: str,
        relation_ids: list[str],
    ) -> int:
        touched = 0
        for path_id, path in list(self.stored_paths.items()):
            if str(path.research_space_id) != research_space_id:
                continue
            step_relation_ids = {
                str(step.claim_relation_id)
                for step in self.stored_steps.get(path_id, [])
            }
            if step_relation_ids.intersection(relation_ids):
                self.stored_paths[path_id] = path.model_copy(update={"status": "STALE"})
                touched += 1
        return touched


@dataclass
class StubRelationClaimService:
    claims: list[KernelRelationClaim]

    def list_by_research_space(
        self,
        research_space_id: str,
        **kwargs: object,
    ) -> list[KernelRelationClaim]:
        filtered = [
            claim
            for claim in self.claims
            if str(claim.research_space_id) == research_space_id
        ]
        claim_status = kwargs.get("claim_status")
        persistability = kwargs.get("persistability")
        polarity = kwargs.get("polarity")
        if isinstance(claim_status, str):
            filtered = [
                claim for claim in filtered if claim.claim_status == claim_status
            ]
        if isinstance(persistability, str):
            filtered = [
                claim for claim in filtered if claim.persistability == persistability
            ]
        if isinstance(polarity, str):
            filtered = [claim for claim in filtered if claim.polarity == polarity]
        return filtered

    def list_claims_by_ids(self, claim_ids: list[str]) -> list[KernelRelationClaim]:
        wanted = set(claim_ids)
        return [claim for claim in self.claims if str(claim.id) in wanted]


@dataclass
class StubClaimParticipantService:
    participants_by_claim: dict[str, list[KernelClaimParticipant]]

    def list_for_claim_ids(
        self,
        claim_ids: list[str],
    ) -> dict[str, list[KernelClaimParticipant]]:
        return {
            claim_id: list(self.participants_by_claim.get(claim_id, []))
            for claim_id in claim_ids
        }


@dataclass
class StubClaimEvidenceService:
    evidence_by_claim: dict[str, list[KernelClaimEvidence]]

    def list_for_claim_ids(
        self,
        claim_ids: list[str],
    ) -> dict[str, list[KernelClaimEvidence]]:
        return {
            claim_id: list(self.evidence_by_claim.get(claim_id, []))
            for claim_id in claim_ids
        }


@dataclass
class StubClaimRelationService:
    claim_relations: list[KernelClaimRelation]

    def list_by_research_space(
        self,
        research_space_id: str,
        **kwargs: object,
    ) -> list[KernelClaimRelation]:
        review_status = kwargs.get("review_status")
        filtered = [
            relation
            for relation in self.claim_relations
            if str(relation.research_space_id) == research_space_id
        ]
        if isinstance(review_status, str):
            filtered = [
                relation
                for relation in filtered
                if relation.review_status == review_status
            ]
        return filtered

    def get_claim_relation(self, relation_id: str) -> KernelClaimRelation | None:
        for relation in self.claim_relations:
            if str(relation.id) == relation_id:
                return relation
        return None


@dataclass
class StubRelationService:
    relations_by_id: dict[str, KernelRelation]

    def get_relation(
        self,
        relation_id: str,
        *,
        claim_backed_only: bool = True,
    ) -> KernelRelation | None:
        del claim_backed_only
        return self.relations_by_id.get(relation_id)


def test_rebuild_creates_grounded_paths_and_detail() -> None:
    space_id = uuid4()
    claim_a_id = uuid4()
    claim_b_id = uuid4()
    relation_id = uuid4()
    canonical_relation_id = uuid4()
    start_entity_id = uuid4()
    mid_entity_id = uuid4()
    end_entity_id = uuid4()

    claim_a = _build_claim(
        claim_id=claim_a_id,
        research_space_id=space_id,
        relation_type="PART_OF",
        linked_relation_id=canonical_relation_id,
    )
    claim_b = _build_claim(
        claim_id=claim_b_id,
        research_space_id=space_id,
        relation_type="ASSOCIATED_WITH",
    )
    repo = StubReasoningPathRepository()
    service = KernelReasoningPathService(
        reasoning_path_repo=repo,
        relation_claim_service=StubRelationClaimService([claim_a, claim_b]),
        claim_participant_service=StubClaimParticipantService(
            {
                str(claim_a_id): [
                    _build_participant(
                        claim_id=claim_a_id,
                        research_space_id=space_id,
                        role="SUBJECT",
                        entity_id=start_entity_id,
                        position=0,
                    ),
                    _build_participant(
                        claim_id=claim_a_id,
                        research_space_id=space_id,
                        role="OBJECT",
                        entity_id=mid_entity_id,
                        position=1,
                    ),
                ],
                str(claim_b_id): [
                    _build_participant(
                        claim_id=claim_b_id,
                        research_space_id=space_id,
                        role="SUBJECT",
                        entity_id=mid_entity_id,
                        position=0,
                    ),
                    _build_participant(
                        claim_id=claim_b_id,
                        research_space_id=space_id,
                        role="OBJECT",
                        entity_id=end_entity_id,
                        position=1,
                    ),
                ],
            },
        ),
        claim_evidence_service=StubClaimEvidenceService(
            {
                str(claim_a_id): [_build_evidence(claim_id=claim_a_id)],
                str(claim_b_id): [_build_evidence(claim_id=claim_b_id)],
            },
        ),
        claim_relation_service=StubClaimRelationService(
            [
                _build_claim_relation(
                    relation_id=relation_id,
                    research_space_id=space_id,
                    source_claim_id=claim_a_id,
                    target_claim_id=claim_b_id,
                    confidence=0.66,
                ),
            ],
        ),
        relation_service=StubRelationService(
            {
                str(canonical_relation_id): _build_relation(
                    relation_id=canonical_relation_id,
                    research_space_id=space_id,
                ),
            },
        ),
    )

    summary = service.rebuild_for_space(
        str(space_id),
        max_depth=4,
        replace_existing=True,
    )

    assert summary.eligible_claims == 2
    assert summary.accepted_claim_relations == 1
    assert summary.rebuilt_paths == 1

    list_result = service.list_paths(research_space_id=str(space_id))
    assert list_result.total == 1
    path = list_result.paths[0]
    assert str(path.start_entity_id) == str(start_entity_id)
    assert str(path.end_entity_id) == str(end_entity_id)
    assert path.path_length == 1
    assert path.status == "ACTIVE"

    detail = service.get_path(str(path.id), str(space_id))
    assert detail is not None
    assert len(detail.steps) == 1
    assert len(detail.claims) == 2
    assert len(detail.claim_relations) == 1
    assert len(detail.evidence) == 2
    assert len(detail.canonical_relations) == 1


def test_rebuild_excludes_claims_missing_evidence_and_marks_paths_stale() -> None:
    space_id = uuid4()
    claim_a_id = uuid4()
    claim_b_id = uuid4()
    relation_id = uuid4()
    start_entity_id = uuid4()
    mid_entity_id = uuid4()
    end_entity_id = uuid4()

    claim_a = _build_claim(
        claim_id=claim_a_id,
        research_space_id=space_id,
        relation_type="PART_OF",
    )
    claim_b = _build_claim(
        claim_id=claim_b_id,
        research_space_id=space_id,
        relation_type="ASSOCIATED_WITH",
    )
    repo = StubReasoningPathRepository()
    service = KernelReasoningPathService(
        reasoning_path_repo=repo,
        relation_claim_service=StubRelationClaimService([claim_a, claim_b]),
        claim_participant_service=StubClaimParticipantService(
            {
                str(claim_a_id): [
                    _build_participant(
                        claim_id=claim_a_id,
                        research_space_id=space_id,
                        role="SUBJECT",
                        entity_id=start_entity_id,
                        position=0,
                    ),
                    _build_participant(
                        claim_id=claim_a_id,
                        research_space_id=space_id,
                        role="OBJECT",
                        entity_id=mid_entity_id,
                        position=1,
                    ),
                ],
                str(claim_b_id): [
                    _build_participant(
                        claim_id=claim_b_id,
                        research_space_id=space_id,
                        role="SUBJECT",
                        entity_id=mid_entity_id,
                        position=0,
                    ),
                    _build_participant(
                        claim_id=claim_b_id,
                        research_space_id=space_id,
                        role="OBJECT",
                        entity_id=end_entity_id,
                        position=1,
                    ),
                ],
            },
        ),
        claim_evidence_service=StubClaimEvidenceService(
            {
                str(claim_a_id): [_build_evidence(claim_id=claim_a_id)],
                str(claim_b_id): [],
            },
        ),
        claim_relation_service=StubClaimRelationService(
            [
                _build_claim_relation(
                    relation_id=relation_id,
                    research_space_id=space_id,
                    source_claim_id=claim_a_id,
                    target_claim_id=claim_b_id,
                ),
            ],
        ),
        relation_service=StubRelationService({}),
    )

    summary = service.rebuild_for_space(str(space_id), replace_existing=True)
    assert summary.eligible_claims == 1
    assert summary.rebuilt_paths == 0

    repo.replace_for_space(
        research_space_id=str(space_id),
        bundles=[
            ReasoningPathWriteBundle(
                path=ReasoningPathWrite(
                    research_space_id=str(space_id),
                    path_kind="MECHANISM",
                    status="ACTIVE",
                    start_entity_id=str(start_entity_id),
                    end_entity_id=str(end_entity_id),
                    root_claim_id=str(claim_a_id),
                    path_length=1,
                    confidence=0.7,
                    path_signature_hash="0123456789abcdef0123456789abcdef",
                    generated_by="test",
                    metadata={},
                ),
                steps=(
                    ReasoningPathStepWrite(
                        step_index=0,
                        source_claim_id=str(claim_a_id),
                        target_claim_id=str(claim_b_id),
                        claim_relation_id=str(relation_id),
                        canonical_relation_id=None,
                        metadata={},
                    ),
                ),
            ),
        ],
        replace_existing=True,
    )
    stale_count = service.mark_stale_for_claim_relation_ids(
        [str(relation_id)],
        str(space_id),
    )
    assert stale_count == 1
    listed = service.list_paths(research_space_id=str(space_id), status="STALE")
    assert listed.total == 1

    stale_by_claim_count = service.mark_stale_for_claim_ids(
        [str(claim_a_id)],
        str(space_id),
    )
    assert stale_by_claim_count == 1

    evidence_by_claim = service._evidence.evidence_by_claim
    evidence_by_claim[str(claim_b_id)] = [_build_evidence(claim_id=claim_b_id)]
    rebuild_summary = service.rebuild_for_space(str(space_id), replace_existing=True)
    assert rebuild_summary.rebuilt_paths == 1
    active_paths = service.list_paths(research_space_id=str(space_id), status="ACTIVE")
    assert active_paths.total == 1
