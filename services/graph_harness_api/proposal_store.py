"""Service-local proposal storage contracts for graph-harness workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID, uuid4

from src.type_definitions.common import JSONObject  # noqa: TC001

_PENDING_REVIEW_STATUS = "pending_review"
_DECISION_STATUSES = frozenset({"promoted", "rejected"})


@dataclass(frozen=True, slots=True)
class HarnessProposalDraft:
    """One proposal ready to be persisted by the harness layer."""

    proposal_type: str
    source_kind: str
    source_key: str
    title: str
    summary: str
    confidence: float
    ranking_score: float
    reasoning_path: JSONObject
    evidence_bundle: list[JSONObject]
    payload: JSONObject
    metadata: JSONObject


@dataclass(frozen=True, slots=True)
class HarnessProposalRecord:
    """One persisted proposal in the harness proposal store."""

    id: str
    space_id: str
    run_id: str
    proposal_type: str
    source_kind: str
    source_key: str
    title: str
    summary: str
    status: str
    confidence: float
    ranking_score: float
    reasoning_path: JSONObject
    evidence_bundle: list[JSONObject]
    payload: JSONObject
    metadata: JSONObject
    decision_reason: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class HarnessProposalStore:
    """Store and retrieve candidate proposals for graph-harness flows."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._proposals: dict[str, HarnessProposalRecord] = {}
        self._proposal_ids_by_space: dict[str, list[str]] = {}

    def create_proposals(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        proposals: tuple[HarnessProposalDraft, ...],
    ) -> list[HarnessProposalRecord]:
        """Persist a batch of proposals for one run."""
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        created_records: list[HarnessProposalRecord] = []
        now = datetime.now(UTC)
        with self._lock:
            for proposal in proposals:
                record = HarnessProposalRecord(
                    id=str(uuid4()),
                    space_id=normalized_space_id,
                    run_id=normalized_run_id,
                    proposal_type=proposal.proposal_type,
                    source_kind=proposal.source_kind,
                    source_key=proposal.source_key,
                    title=proposal.title,
                    summary=proposal.summary,
                    status=_PENDING_REVIEW_STATUS,
                    confidence=proposal.confidence,
                    ranking_score=proposal.ranking_score,
                    reasoning_path=proposal.reasoning_path,
                    evidence_bundle=list(proposal.evidence_bundle),
                    payload=proposal.payload,
                    metadata=proposal.metadata,
                    decision_reason=None,
                    decided_at=None,
                    created_at=now,
                    updated_at=now,
                )
                self._proposals[record.id] = record
                self._proposal_ids_by_space.setdefault(normalized_space_id, []).append(
                    record.id,
                )
                created_records.append(record)
        return sorted(
            created_records,
            key=lambda record: (-record.ranking_score, record.created_at),
        )

    def list_proposals(
        self,
        *,
        space_id: UUID | str,
        status: str | None = None,
        proposal_type: str | None = None,
        run_id: UUID | str | None = None,
    ) -> list[HarnessProposalRecord]:
        """List proposals for one space ordered by ranking."""
        normalized_space_id = str(space_id)
        normalized_status = status.strip() if isinstance(status, str) else None
        normalized_type = (
            proposal_type.strip() if isinstance(proposal_type, str) else None
        )
        normalized_run_id = str(run_id) if run_id is not None else None
        with self._lock:
            proposals = [
                self._proposals[proposal_id]
                for proposal_id in self._proposal_ids_by_space.get(
                    normalized_space_id,
                    [],
                )
            ]
        filtered = [
            proposal
            for proposal in proposals
            if (
                (normalized_status is None or proposal.status == normalized_status)
                and (
                    normalized_type is None or proposal.proposal_type == normalized_type
                )
                and (normalized_run_id is None or proposal.run_id == normalized_run_id)
            )
        ]
        return sorted(
            filtered,
            key=lambda proposal: (-proposal.ranking_score, proposal.updated_at),
        )

    def get_proposal(
        self,
        *,
        space_id: UUID | str,
        proposal_id: UUID | str,
    ) -> HarnessProposalRecord | None:
        """Return one proposal from the store."""
        with self._lock:
            proposal = self._proposals.get(str(proposal_id))
        if proposal is None or proposal.space_id != str(space_id):
            return None
        return proposal

    def decide_proposal(
        self,
        *,
        space_id: UUID | str,
        proposal_id: UUID | str,
        status: str,
        decision_reason: str | None,
        metadata: JSONObject | None = None,
    ) -> HarnessProposalRecord | None:
        """Promote or reject one proposal."""
        normalized_status = status.strip().lower()
        if normalized_status not in _DECISION_STATUSES:
            message = f"Unsupported proposal status '{status}'"
            raise ValueError(message)
        proposal = self.get_proposal(space_id=space_id, proposal_id=proposal_id)
        if proposal is None:
            return None
        if proposal.status != _PENDING_REVIEW_STATUS:
            message = f"Proposal '{proposal_id}' is already decided with status '{proposal.status}'"
            raise ValueError(message)
        updated = HarnessProposalRecord(
            id=proposal.id,
            space_id=proposal.space_id,
            run_id=proposal.run_id,
            proposal_type=proposal.proposal_type,
            source_kind=proposal.source_kind,
            source_key=proposal.source_key,
            title=proposal.title,
            summary=proposal.summary,
            status=normalized_status,
            confidence=proposal.confidence,
            ranking_score=proposal.ranking_score,
            reasoning_path=proposal.reasoning_path,
            evidence_bundle=proposal.evidence_bundle,
            payload=proposal.payload,
            metadata={**proposal.metadata, **(metadata or {})},
            decision_reason=(
                decision_reason.strip()
                if isinstance(decision_reason, str) and decision_reason.strip() != ""
                else None
            ),
            decided_at=datetime.now(UTC),
            created_at=proposal.created_at,
            updated_at=datetime.now(UTC),
        )
        with self._lock:
            self._proposals[proposal.id] = updated
        return updated


__all__ = [
    "HarnessProposalDraft",
    "HarnessProposalRecord",
    "HarnessProposalStore",
]
