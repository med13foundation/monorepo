"""Unit tests for ConceptManagementService."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest

from src.application.services.kernel.concept_management_service import (
    ConceptManagementService,
)
from src.domain.entities.kernel.concepts import (
    ConceptDecision,
    ConceptHarnessCheck,
    ConceptHarnessVerdict,
    ConceptMember,
    ConceptPolicy,
    ConceptSet,
)
from src.domain.ports.concept_decision_harness_port import ConceptDecisionHarnessPort
from src.domain.repositories.kernel.concept_repository import ConceptRepository


def _build_concept_set() -> ConceptSet:
    now = datetime.now(UTC)
    return ConceptSet(
        id=str(uuid4()),
        research_space_id=str(uuid4()),
        name="Focus",
        slug="focus",
        description="Test set",
        domain_context="general",
        created_by="seed",
        source_ref=None,
        review_status="ACTIVE",
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        is_active=True,
        valid_from=now,
        valid_to=None,
        superseded_by=None,
        created_at=now,
        updated_at=now,
    )


def _build_member(
    *,
    review_status: str = "ACTIVE",
    is_provisional: bool = False,
    dictionary_entry_id: str | None = "GENE",
) -> ConceptMember:
    now = datetime.now(UTC)
    return ConceptMember(
        id=str(uuid4()),
        concept_set_id=str(uuid4()),
        research_space_id=str(uuid4()),
        domain_context="general",
        dictionary_dimension=(
            "entity_types" if dictionary_entry_id is not None else None
        ),
        dictionary_entry_id=dictionary_entry_id,
        canonical_label="MED13",
        normalized_label="med13",
        sense_key="",
        is_provisional=is_provisional,
        metadata_payload={},
        created_by="seed",
        source_ref=None,
        review_status=review_status,  # type: ignore[arg-type]
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        is_active=True,
        valid_from=now,
        valid_to=None,
        superseded_by=None,
        created_at=now,
        updated_at=now,
    )


def _build_decision(
    *,
    decision_status: str = "PROPOSED",
    harness_outcome: str | None = None,
) -> ConceptDecision:
    now = datetime.now(UTC)
    return ConceptDecision(
        id=str(uuid4()),
        research_space_id=str(uuid4()),
        concept_set_id=None,
        concept_member_id=None,
        concept_link_id=None,
        decision_type="CREATE",
        decision_status=decision_status,  # type: ignore[arg-type]
        proposed_by="agent:run-1",
        decided_by=None,
        confidence=0.9,
        rationale="rationale",
        evidence_payload={},
        decision_payload={"op": "create"},
        harness_outcome=harness_outcome,  # type: ignore[arg-type]
        decided_at=None,
        created_at=now,
        updated_at=now,
    )


def _build_policy() -> ConceptPolicy:
    now = datetime.now(UTC)
    return ConceptPolicy(
        id=str(uuid4()),
        research_space_id=str(uuid4()),
        profile_name="default",
        mode="BALANCED",
        minimum_edge_confidence=0.6,
        minimum_distinct_documents=1,
        allow_generic_relations=True,
        max_edges_per_document=None,
        policy_payload={},
        created_by="seed",
        source_ref=None,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


class StubConceptHarness(ConceptDecisionHarnessPort):
    """Deterministic harness stub."""

    def __init__(self, verdict: ConceptHarnessVerdict) -> None:
        self._verdict = verdict
        self.calls = 0

    def evaluate(self, proposal):  # type: ignore[override]
        self.calls += 1
        return self._verdict


@pytest.fixture
def concept_repo() -> Mock:
    repo = Mock(spec=ConceptRepository)
    repo.create_concept_set.return_value = _build_concept_set()
    repo.find_concept_sets.return_value = [_build_concept_set()]
    repo.create_concept_member.return_value = _build_member()
    repo.create_concept_alias.return_value = Mock()
    repo.create_concept_policy.return_value = _build_policy()
    repo.get_active_policy.return_value = _build_policy()
    repo.create_decision.return_value = _build_decision(decision_status="PROPOSED")
    repo.set_decision_status.return_value = _build_decision(
        decision_status="NEEDS_REVIEW",
        harness_outcome="NEEDS_REVIEW",
    )
    return repo


def test_create_concept_member_uses_pending_review_policy_for_agent(
    concept_repo: Mock,
) -> None:
    service = ConceptManagementService(concept_repo=concept_repo, concept_harness=None)

    service.create_concept_member(
        concept_set_id=str(uuid4()),
        research_space_id=str(uuid4()),
        domain_context="general",
        canonical_label="MED13",
        normalized_label="MED13",
        dictionary_dimension="entity_types",
        dictionary_entry_id="GENE",
        created_by="agent:run-123",
        research_space_settings={"concept_agent_creation_policy": "PENDING_REVIEW"},
    )

    assert concept_repo.create_concept_member.call_args.kwargs["review_status"] == (
        "PENDING_REVIEW"
    )


def test_create_concept_member_requires_provisional_for_unmapped_entries(
    concept_repo: Mock,
) -> None:
    service = ConceptManagementService(concept_repo=concept_repo, concept_harness=None)

    with pytest.raises(
        ValueError,
        match="without dictionary mapping must be created as provisional",
    ):
        service.create_concept_member(
            concept_set_id=str(uuid4()),
            research_space_id=str(uuid4()),
            domain_context="general",
            canonical_label="Unknown concept",
            normalized_label="unknown concept",
            dictionary_dimension=None,
            dictionary_entry_id=None,
            is_provisional=False,
            created_by="manual:user-1",
        )

    concept_repo.create_concept_member.assert_not_called()


def test_create_concept_member_forces_pending_review_for_provisional(
    concept_repo: Mock,
) -> None:
    concept_repo.create_concept_member.return_value = _build_member(
        review_status="PENDING_REVIEW",
        is_provisional=True,
        dictionary_entry_id=None,
    )
    service = ConceptManagementService(concept_repo=concept_repo, concept_harness=None)

    service.create_concept_member(
        concept_set_id=str(uuid4()),
        research_space_id=str(uuid4()),
        domain_context="general",
        canonical_label="Unknown concept",
        normalized_label="unknown concept",
        is_provisional=True,
        created_by="agent:run-456",
        research_space_settings={"concept_agent_creation_policy": "ACTIVE"},
    )

    assert concept_repo.create_concept_member.call_args.kwargs["review_status"] == (
        "PENDING_REVIEW"
    )


def test_list_concept_members_normalizes_pagination_and_ids(
    concept_repo: Mock,
) -> None:
    service = ConceptManagementService(concept_repo=concept_repo, concept_harness=None)
    research_space_id = str(uuid4())
    concept_set_id = str(uuid4())

    service.list_concept_members(
        research_space_id=f"  {research_space_id}  ",
        concept_set_id=f" {concept_set_id} ",
        include_inactive=True,
        offset=-10,
        limit=1000,
    )

    concept_repo.find_concept_members.assert_called_once_with(
        research_space_id=research_space_id,
        concept_set_id=concept_set_id,
        include_inactive=True,
        offset=0,
        limit=500,
    )


def test_list_decisions_clamps_limit(
    concept_repo: Mock,
) -> None:
    service = ConceptManagementService(concept_repo=concept_repo, concept_harness=None)
    research_space_id = str(uuid4())

    service.list_decisions(
        research_space_id=research_space_id,
        decision_status="NEEDS_REVIEW",
        offset=5,
        limit=0,
    )

    concept_repo.find_decisions.assert_called_once_with(
        research_space_id=research_space_id,
        decision_status="NEEDS_REVIEW",
        offset=5,
        limit=1,
    )


def test_propose_decision_agent_active_policy_auto_applies_on_pass(
    concept_repo: Mock,
) -> None:
    concept_repo.set_decision_status.return_value = _build_decision(
        decision_status="APPLIED",
        harness_outcome="PASS",
    )
    harness = StubConceptHarness(
        ConceptHarnessVerdict(
            outcome="PASS",
            rationale="ok",
            checks=[
                ConceptHarnessCheck(
                    check_id="check",
                    passed=True,
                    detail="ok",
                ),
            ],
            errors=[],
            metadata={},
        ),
    )
    service = ConceptManagementService(
        concept_repo=concept_repo,
        concept_harness=harness,
    )

    decision = service.propose_decision(
        research_space_id=str(uuid4()),
        decision_type="CREATE",
        proposed_by="agent:run-1",
        decision_payload={"op": "create"},
        confidence=0.9,
        rationale="high confidence",
        research_space_settings={"concept_agent_creation_policy": "ACTIVE"},
    )

    assert harness.calls == 1
    assert decision.decision_status == "APPLIED"
    assert (
        concept_repo.set_decision_status.call_args.kwargs["decision_status"]
        == "APPLIED"
    )
    concept_repo.create_harness_result.assert_called_once()


def test_propose_decision_agent_pending_policy_requires_review_on_pass(
    concept_repo: Mock,
) -> None:
    concept_repo.set_decision_status.return_value = _build_decision(
        decision_status="NEEDS_REVIEW",
        harness_outcome="PASS",
    )
    harness = StubConceptHarness(
        ConceptHarnessVerdict(
            outcome="PASS",
            rationale="ok",
            checks=[],
            errors=[],
            metadata={},
        ),
    )
    service = ConceptManagementService(
        concept_repo=concept_repo,
        concept_harness=harness,
    )

    decision = service.propose_decision(
        research_space_id=str(uuid4()),
        decision_type="CREATE",
        proposed_by="agent:run-1",
        decision_payload={"op": "create"},
        confidence=0.9,
        rationale="high confidence",
        research_space_settings={"concept_agent_creation_policy": "PENDING_REVIEW"},
    )

    assert decision.decision_status == "NEEDS_REVIEW"
    assert concept_repo.set_decision_status.call_args.kwargs["decision_status"] == (
        "NEEDS_REVIEW"
    )


def test_propose_decision_agent_rejects_on_fail_verdict(
    concept_repo: Mock,
) -> None:
    concept_repo.set_decision_status.return_value = _build_decision(
        decision_status="REJECTED",
        harness_outcome="FAIL",
    )
    harness = StubConceptHarness(
        ConceptHarnessVerdict(
            outcome="FAIL",
            rationale="bad",
            checks=[],
            errors=["rule_failed"],
            metadata={},
        ),
    )
    service = ConceptManagementService(
        concept_repo=concept_repo,
        concept_harness=harness,
    )

    decision = service.propose_decision(
        research_space_id=str(uuid4()),
        decision_type="CREATE",
        proposed_by="agent:run-1",
        decision_payload={"op": "create"},
        confidence=0.4,
        rationale="low confidence",
        research_space_settings={"concept_agent_creation_policy": "ACTIVE"},
    )

    assert decision.decision_status == "REJECTED"
    assert (
        concept_repo.set_decision_status.call_args.kwargs["decision_status"]
        == "REJECTED"
    )


def test_propose_decision_non_agent_skips_harness(
    concept_repo: Mock,
) -> None:
    harness = StubConceptHarness(
        ConceptHarnessVerdict(
            outcome="PASS",
            rationale="ok",
            checks=[],
            errors=[],
            metadata={},
        ),
    )
    service = ConceptManagementService(
        concept_repo=concept_repo,
        concept_harness=harness,
    )

    decision = service.propose_decision(
        research_space_id=str(uuid4()),
        decision_type="CREATE",
        proposed_by="manual:user-1",
        decision_payload={"op": "create"},
        confidence=0.9,
        rationale="manual decision",
    )

    assert decision.decision_status == "PROPOSED"
    assert harness.calls == 0
    concept_repo.set_decision_status.assert_not_called()
