"""Service-local approval and intent storage for harness runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID  # noqa: TC003

from src.type_definitions.common import JSONObject  # noqa: TC001


@dataclass(frozen=True, slots=True)
class HarnessApprovalAction:
    """One proposed action in a run intent plan."""

    approval_key: str
    title: str
    risk_level: str
    target_type: str
    target_id: str | None
    requires_approval: bool
    metadata: JSONObject


@dataclass(frozen=True, slots=True)
class HarnessRunIntentRecord:
    """Intent plan stored for one harness run."""

    space_id: str
    run_id: str
    summary: str
    proposed_actions: tuple[HarnessApprovalAction, ...]
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class HarnessApprovalRecord:
    """Approval decision record for one gated run action."""

    space_id: str
    run_id: str
    approval_key: str
    title: str
    risk_level: str
    target_type: str
    target_id: str | None
    status: str
    decision_reason: str | None
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime


class HarnessApprovalStore:
    """Store run intent plans and approval decisions."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._intents: dict[tuple[str, str], HarnessRunIntentRecord] = {}
        self._approvals: dict[tuple[str, str], dict[str, HarnessApprovalRecord]] = {}

    def upsert_intent(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        summary: str,
        proposed_actions: tuple[HarnessApprovalAction, ...],
        metadata: JSONObject,
    ) -> HarnessRunIntentRecord:
        """Create or replace the intent plan for one run."""
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        now = datetime.now(UTC)
        intent = HarnessRunIntentRecord(
            space_id=normalized_space_id,
            run_id=normalized_run_id,
            summary=summary,
            proposed_actions=proposed_actions,
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )
        approval_records: dict[str, HarnessApprovalRecord] = {}
        for action in proposed_actions:
            if not action.requires_approval:
                continue
            approval_records[action.approval_key] = HarnessApprovalRecord(
                space_id=normalized_space_id,
                run_id=normalized_run_id,
                approval_key=action.approval_key,
                title=action.title,
                risk_level=action.risk_level,
                target_type=action.target_type,
                target_id=action.target_id,
                status="pending",
                decision_reason=None,
                metadata=action.metadata,
                created_at=now,
                updated_at=now,
            )
        with self._lock:
            self._intents[(normalized_space_id, normalized_run_id)] = intent
            self._approvals[(normalized_space_id, normalized_run_id)] = approval_records
        return intent

    def get_intent(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunIntentRecord | None:
        """Return the stored intent plan for one run."""
        key = (str(space_id), str(run_id))
        with self._lock:
            return self._intents.get(key)

    def list_approvals(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> list[HarnessApprovalRecord]:
        """Return approvals for one run."""
        key = (str(space_id), str(run_id))
        with self._lock:
            approvals = self._approvals.get(key, {})
            return list(approvals.values())

    def decide_approval(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        approval_key: str,
        status: str,
        decision_reason: str | None,
    ) -> HarnessApprovalRecord | None:
        """Set the decision for one approval record."""
        normalized_status = status.strip().lower()
        if normalized_status not in {"approved", "rejected"}:
            msg = f"Unsupported approval status '{status}'"
            raise ValueError(msg)
        normalized_reason = (
            decision_reason.strip() if isinstance(decision_reason, str) else None
        )
        key = (str(space_id), str(run_id))
        with self._lock:
            approvals = self._approvals.get(key, {})
            existing = approvals.get(approval_key)
            if existing is None:
                return None
            updated = HarnessApprovalRecord(
                space_id=existing.space_id,
                run_id=existing.run_id,
                approval_key=existing.approval_key,
                title=existing.title,
                risk_level=existing.risk_level,
                target_type=existing.target_type,
                target_id=existing.target_id,
                status=normalized_status,
                decision_reason=normalized_reason,
                metadata=existing.metadata,
                created_at=existing.created_at,
                updated_at=datetime.now(UTC),
            )
            approvals[approval_key] = updated
            return updated


__all__ = [
    "HarnessApprovalAction",
    "HarnessApprovalRecord",
    "HarnessApprovalStore",
    "HarnessRunIntentRecord",
]
