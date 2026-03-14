"""Unit tests for the remaining graph-harness SQLAlchemy domain stores."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from services.graph_harness_api.approval_store import HarnessApprovalAction
from services.graph_harness_api.proposal_store import HarnessProposalDraft
from services.graph_harness_api.sqlalchemy_stores import (
    SqlAlchemyHarnessApprovalStore,
    SqlAlchemyHarnessChatSessionStore,
    SqlAlchemyHarnessGraphSnapshotStore,
    SqlAlchemyHarnessProposalStore,
    SqlAlchemyHarnessResearchStateStore,
    SqlAlchemyHarnessScheduleStore,
)
from src.models.database import Base, HarnessRunModel

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()


def _create_run_catalog_entry(
    session: Session,
    *,
    space_id: str,
    harness_id: str,
    title: str,
    input_payload: dict[str, object],
) -> HarnessRunModel:
    model = HarnessRunModel(
        space_id=space_id,
        harness_id=harness_id,
        title=title,
        status="queued",
        input_payload=input_payload,
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )
    session.add(model)
    session.commit()
    session.refresh(model)
    return model


def test_sqlalchemy_harness_approval_store_persists_intents_and_decisions(
    session: Session,
) -> None:
    approval_store = SqlAlchemyHarnessApprovalStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="claim-curation",
        title="Curation run",
        input_payload={"proposal_id": "proposal-1"},
    )

    intent = approval_store.upsert_intent(
        space_id=space_id,
        run_id=run.id,
        summary="Review proposed graph updates",
        proposed_actions=(
            HarnessApprovalAction(
                approval_key="promote-claim-1",
                title="Promote candidate claim",
                risk_level="high",
                target_type="claim",
                target_id="claim-1",
                requires_approval=True,
                metadata={"origin": "chat"},
            ),
            HarnessApprovalAction(
                approval_key="save-summary",
                title="Persist curation summary",
                risk_level="low",
                target_type="artifact",
                target_id="summary-1",
                requires_approval=False,
                metadata={"origin": "run"},
            ),
        ),
        metadata={"stage": "review"},
    )
    assert intent.summary == "Review proposed graph updates"
    assert len(intent.proposed_actions) == 2

    fetched_intent = approval_store.get_intent(space_id=space_id, run_id=run.id)
    assert fetched_intent is not None
    assert fetched_intent.metadata["stage"] == "review"

    approvals = approval_store.list_approvals(space_id=space_id, run_id=run.id)
    assert len(approvals) == 1
    assert approvals[0].approval_key == "promote-claim-1"
    assert approvals[0].status == "pending"

    decided = approval_store.decide_approval(
        space_id=space_id,
        run_id=run.id,
        approval_key="promote-claim-1",
        status="approved",
        decision_reason="Evidence is sufficient",
    )
    assert decided is not None
    assert decided.status == "approved"
    assert decided.decision_reason == "Evidence is sufficient"


def test_sqlalchemy_harness_chat_session_store_persists_sessions_and_messages(
    session: Session,
) -> None:
    chat_store = SqlAlchemyHarnessChatSessionStore(session)
    space_id = str(uuid4())
    user_id = str(uuid4())
    run_id = str(uuid4())

    created_session = chat_store.create_session(
        space_id=space_id,
        title="New Graph Chat",
        created_by=user_id,
    )
    assert created_session.created_by == user_id
    assert created_session.last_run_id is None

    fetched_session = chat_store.get_session(
        space_id=space_id,
        session_id=created_session.id,
    )
    assert fetched_session is not None
    assert fetched_session.title == "New Graph Chat"

    user_message = chat_store.add_message(
        space_id=space_id,
        session_id=created_session.id,
        role="user",
        content="What does MED13 do?",
        run_id=run_id,
        metadata={"message_kind": "question"},
    )
    assert user_message is not None
    assert user_message.run_id == run_id

    assistant_message = chat_store.add_message(
        space_id=space_id,
        session_id=created_session.id,
        role="assistant",
        content="Synthetic grounded answer.",
        run_id=run_id,
        metadata={"message_kind": "answer"},
    )
    assert assistant_message is not None

    updated_session = chat_store.update_session(
        space_id=space_id,
        session_id=created_session.id,
        title="What does MED13 do?",
        last_run_id=run_id,
        status="active",
    )
    assert updated_session is not None
    assert updated_session.title == "What does MED13 do?"
    assert updated_session.last_run_id == run_id
    assert updated_session.status == "active"

    listed_sessions = chat_store.list_sessions(space_id=space_id)
    assert [record.id for record in listed_sessions] == [created_session.id]

    messages = chat_store.list_messages(
        space_id=space_id,
        session_id=created_session.id,
    )
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].metadata["message_kind"] == "question"


def test_sqlalchemy_harness_proposal_store_persists_and_decides_proposals(
    session: Session,
) -> None:
    proposal_store = SqlAlchemyHarnessProposalStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="hypotheses",
        title="Hypothesis run",
        input_payload={"seed_entity_ids": ["entity-1"]},
    )

    created = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="hypothesis_run",
                source_key="entity-1:entity-1:SUGGESTS:target-1",
                title="Candidate claim A",
                summary="First ranked candidate.",
                confidence=0.81,
                ranking_score=0.91,
                reasoning_path={"seed_entity_id": "entity-1"},
                evidence_bundle=[{"source_type": "db", "locator": "entity-1"}],
                payload={"proposed_claim_type": "SUGGESTS"},
                metadata={"source_type": "pubmed"},
            ),
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="hypothesis_run",
                source_key="entity-1:entity-1:SUGGESTS:target-2",
                title="Candidate claim B",
                summary="Second ranked candidate.",
                confidence=0.72,
                ranking_score=0.65,
                reasoning_path={"seed_entity_id": "entity-1"},
                evidence_bundle=[{"source_type": "db", "locator": "entity-2"}],
                payload={"proposed_claim_type": "SUGGESTS"},
                metadata={"source_type": "pubmed"},
            ),
        ),
    )

    assert [proposal.title for proposal in created] == [
        "Candidate claim A",
        "Candidate claim B",
    ]

    listed = proposal_store.list_proposals(space_id=space_id, run_id=run.id)
    assert [proposal.id for proposal in listed] == [created[0].id, created[1].id]

    fetched = proposal_store.get_proposal(
        space_id=space_id,
        proposal_id=created[0].id,
    )
    assert fetched is not None
    assert fetched.status == "pending_review"

    promoted = proposal_store.decide_proposal(
        space_id=space_id,
        proposal_id=created[0].id,
        status="promoted",
        decision_reason="Evidence is strong",
        metadata={"reviewed_by": "tester"},
    )
    assert promoted is not None
    assert promoted.status == "promoted"
    assert promoted.decision_reason == "Evidence is strong"
    assert promoted.metadata["reviewed_by"] == "tester"

    rejected = proposal_store.decide_proposal(
        space_id=space_id,
        proposal_id=created[1].id,
        status="rejected",
        decision_reason="Needs more support",
        metadata={"reviewed_by": "tester"},
    )
    assert rejected is not None
    assert rejected.status == "rejected"

    promoted_only = proposal_store.list_proposals(
        space_id=space_id,
        status="promoted",
        run_id=run.id,
    )
    assert [proposal.id for proposal in promoted_only] == [created[0].id]


def test_sqlalchemy_harness_schedule_store_persists_and_updates_schedules(
    session: Session,
) -> None:
    schedule_store = SqlAlchemyHarnessScheduleStore(session)
    space_id = str(uuid4())
    created_by = str(uuid4())

    created = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Daily refresh",
        cadence="daily",
        created_by=created_by,
        configuration={
            "seed_entity_ids": ["entity-1"],
            "source_type": "pubmed",
            "run_budget": {
                "max_tool_calls": 100,
                "max_external_queries": 101,
                "max_new_proposals": 20,
                "max_runtime_seconds": 300,
                "max_cost_usd": 5.0,
            },
        },
        metadata={"owner": "tester"},
    )
    assert created.harness_id == "continuous-learning"
    assert created.last_run_id is None

    listed = schedule_store.list_schedules(space_id=space_id)
    assert [schedule.id for schedule in listed] == [created.id]
    assert schedule_store.list_all_schedules(status="active")[0].id == created.id

    fetched = schedule_store.get_schedule(space_id=space_id, schedule_id=created.id)
    assert fetched is not None
    assert fetched.configuration["seed_entity_ids"] == ["entity-1"]
    assert fetched.configuration["run_budget"]["max_tool_calls"] == 100

    updated = schedule_store.update_schedule(
        space_id=space_id,
        schedule_id=created.id,
        title="Weekday refresh",
        cadence="weekday",
        status="paused",
        last_run_id=str(uuid4()),
    )
    assert updated is not None
    assert updated.title == "Weekday refresh"
    assert updated.cadence == "weekday"
    assert updated.status == "paused"
    assert updated.last_run_id is not None
    assert schedule_store.list_all_schedules(status="paused")[0].id == created.id


def test_sqlalchemy_research_memory_stores_persist_state_and_snapshots(
    session: Session,
) -> None:
    research_state_store = SqlAlchemyHarnessResearchStateStore(session)
    graph_snapshot_store = SqlAlchemyHarnessGraphSnapshotStore(session)
    space_id = str(uuid4())
    run = _create_run_catalog_entry(
        session,
        space_id=space_id,
        harness_id="research-bootstrap",
        title="Bootstrap run",
        input_payload={"objective": "Map MED13"},
    )

    snapshot = graph_snapshot_store.create_snapshot(
        space_id=space_id,
        source_run_id=run.id,
        claim_ids=["claim-1", "claim-2"],
        relation_ids=["relation-1"],
        graph_document_hash="abc123",
        summary={"claim_count": 2, "mode": "seeded"},
        metadata={"seed_entity_ids": ["entity-1"]},
    )
    assert snapshot.source_run_id == run.id
    assert snapshot.graph_document_hash == "abc123"

    listed_snapshots = graph_snapshot_store.list_snapshots(space_id=space_id)
    assert [record.id for record in listed_snapshots] == [snapshot.id]

    state = research_state_store.upsert_state(
        space_id=space_id,
        objective="Map MED13",
        current_hypotheses=["MED13 may regulate transcription."],
        explored_questions=["Map MED13"],
        pending_questions=["What supports MED13 activation?"],
        last_graph_snapshot_id=snapshot.id,
        active_schedules=["schedule-1"],
        confidence_model={"proposal_ranking_model": "candidate_claim_v1"},
        budget_policy={"max_runtime_seconds": 300},
        metadata={"last_bootstrap_run_id": run.id},
    )
    assert state.objective == "Map MED13"
    assert state.last_graph_snapshot_id == snapshot.id
    assert state.active_schedules == ["schedule-1"]

    fetched_state = research_state_store.get_state(space_id=space_id)
    assert fetched_state is not None
    assert fetched_state.current_hypotheses == ["MED13 may regulate transcription."]
    assert fetched_state.metadata["last_bootstrap_run_id"] == run.id
