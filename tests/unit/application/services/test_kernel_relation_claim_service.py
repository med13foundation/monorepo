"""Unit tests for relation-claim service read-model update hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from src.application.services.kernel.kernel_relation_claim_service import (
    KernelRelationClaimService,
)
from src.domain.entities.kernel.relation_claims import KernelRelationClaim
from src.graph.core.read_model import (
    GraphReadModelUpdate,
    NullGraphReadModelUpdateDispatcher,
)
from src.type_definitions.common import JSONObject


@dataclass
class _RecordingReadModelDispatcher(NullGraphReadModelUpdateDispatcher):
    updates: list[GraphReadModelUpdate] = field(default_factory=list)

    def dispatch(self, update: GraphReadModelUpdate) -> int:
        self.updates.append(update)
        return 1


@dataclass
class _FakeRelationClaimRepository:
    claim: KernelRelationClaim

    def create(self, **_: object) -> KernelRelationClaim:
        return self.claim

    def update_triage_status(
        self,
        claim_id: str,
        *,
        claim_status: str,
        triaged_by: str,
    ) -> KernelRelationClaim:
        del claim_id, claim_status, triaged_by
        return self.claim

    def link_relation(
        self,
        claim_id: str,
        *,
        linked_relation_id: str,
    ) -> KernelRelationClaim:
        del claim_id, linked_relation_id
        return self.claim

    def clear_relation_link(self, claim_id: str) -> KernelRelationClaim:
        del claim_id
        return self.claim

    def set_system_status(
        self,
        claim_id: str,
        *,
        claim_status: str,
    ) -> KernelRelationClaim:
        del claim_id, claim_status
        return self.claim


def _build_claim(
    *,
    linked_relation_id: UUID | None = None,
) -> KernelRelationClaim:
    timestamp = datetime.now(UTC)
    metadata_payload: JSONObject = {}
    return KernelRelationClaim(
        id=uuid4(),
        research_space_id=uuid4(),
        source_document_id=None,
        source_document_ref=None,
        agent_run_id="claim-test-run",
        source_type="pubmed",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Cardiomyopathy",
        confidence=0.8,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="OPEN",
        polarity="SUPPORT",
        claim_text="MED13 is associated with cardiomyopathy.",
        claim_section="results",
        linked_relation_id=linked_relation_id,
        metadata_payload=metadata_payload,
        triaged_by=None,
        triaged_at=None,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_create_claim_dispatches_entity_claim_summary_update() -> None:
    claim = _build_claim()
    dispatcher = _RecordingReadModelDispatcher()
    service = KernelRelationClaimService(
        relation_claim_repo=_FakeRelationClaimRepository(claim=claim),
        read_model_update_dispatcher=dispatcher,
    )

    created = service.create_claim(
        research_space_id=str(claim.research_space_id),
        source_document_id=None,
        agent_run_id=claim.agent_run_id,
        source_type=claim.source_type,
        relation_type=claim.relation_type,
        target_type=claim.target_type,
        source_label=claim.source_label,
        target_label=claim.target_label,
        confidence=claim.confidence,
        validation_state=claim.validation_state,
        validation_reason=claim.validation_reason,
        persistability=claim.persistability,
        claim_status=claim.claim_status,
        polarity=claim.polarity,
        claim_text=claim.claim_text,
        claim_section=claim.claim_section,
        source_document_ref=claim.source_document_ref,
        metadata={},
    )

    assert created == claim
    assert len(dispatcher.updates) == 1
    update = dispatcher.updates[0]
    assert update.model_name == "entity_claim_summary"
    assert update.trigger == "claim_change"
    assert update.claim_ids == (str(claim.id),)
    assert update.relation_ids == ()
    assert update.space_id == str(claim.research_space_id)


def test_update_claim_status_dispatches_entity_claim_summary_update() -> None:
    linked_relation_id = uuid4()
    claim = _build_claim(linked_relation_id=linked_relation_id)
    dispatcher = _RecordingReadModelDispatcher()
    service = KernelRelationClaimService(
        relation_claim_repo=_FakeRelationClaimRepository(claim=claim),
        read_model_update_dispatcher=dispatcher,
    )

    updated = service.update_claim_status(
        str(claim.id),
        claim_status="RESOLVED",
        triaged_by=str(uuid4()),
    )

    assert updated == claim
    assert len(dispatcher.updates) == 1
    update = dispatcher.updates[0]
    assert update.model_name == "entity_claim_summary"
    assert update.trigger == "claim_change"
    assert update.claim_ids == (str(claim.id),)
    assert update.relation_ids == (str(linked_relation_id),)
    assert update.space_id == str(claim.research_space_id)
