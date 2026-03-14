"""SQLAlchemy-backed durable stores for graph-harness runtime state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from src.models.database import (
    HarnessApprovalModel,
    HarnessChatMessageModel,
    HarnessChatSessionModel,
    HarnessGraphSnapshotModel,
    HarnessIntentModel,
    HarnessProposalModel,
    HarnessResearchStateModel,
    HarnessScheduleModel,
)

from .approval_store import (
    HarnessApprovalAction,
    HarnessApprovalRecord,
    HarnessApprovalStore,
    HarnessRunIntentRecord,
)
from .chat_sessions import (
    HarnessChatMessageRecord,
    HarnessChatSessionRecord,
    HarnessChatSessionStore,
)
from .graph_snapshot import (
    HarnessGraphSnapshotRecord,
    HarnessGraphSnapshotStore,
)
from .proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,
    HarnessProposalStore,
)
from .research_state import (
    HarnessResearchStateRecord,
    HarnessResearchStateStore,
)
from .schedule_policy import normalize_schedule_cadence
from .schedule_store import (
    HarnessScheduleRecord,
    HarnessScheduleStore,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject


def _json_object(value: object) -> JSONObject:
    return value if isinstance(value, dict) else {}


def _json_object_list(value: object) -> list[JSONObject]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _json_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized_values: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized == "":
            continue
        normalized_values.append(normalized)
    return normalized_values


def _action_payload(action: HarnessApprovalAction) -> JSONObject:
    return {
        "approval_key": action.approval_key,
        "title": action.title,
        "risk_level": action.risk_level,
        "target_type": action.target_type,
        "target_id": action.target_id,
        "requires_approval": action.requires_approval,
        "metadata": action.metadata,
    }


def _action_from_payload(payload: object) -> HarnessApprovalAction | None:
    if not isinstance(payload, dict):
        return None
    approval_key = payload.get("approval_key")
    title = payload.get("title")
    risk_level = payload.get("risk_level")
    target_type = payload.get("target_type")
    requires_approval = payload.get("requires_approval")
    if not (
        isinstance(approval_key, str)
        and isinstance(title, str)
        and isinstance(risk_level, str)
        and isinstance(target_type, str)
        and isinstance(requires_approval, bool)
    ):
        return None
    target_id = payload.get("target_id")
    normalized_target_id = target_id if isinstance(target_id, str) else None
    metadata = payload.get("metadata")
    return HarnessApprovalAction(
        approval_key=approval_key,
        title=title,
        risk_level=risk_level,
        target_type=target_type,
        target_id=normalized_target_id,
        requires_approval=requires_approval,
        metadata=_json_object(metadata),
    )


def _intent_record_from_model(model: HarnessIntentModel) -> HarnessRunIntentRecord:
    actions = tuple(
        action
        for action in (
            _action_from_payload(payload)
            for payload in _json_object_list(model.proposed_actions_payload)
        )
        if action is not None
    )
    return HarnessRunIntentRecord(
        space_id=model.space_id,
        run_id=model.run_id,
        summary=model.summary,
        proposed_actions=actions,
        metadata=_json_object(model.metadata_payload),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _approval_record_from_model(model: HarnessApprovalModel) -> HarnessApprovalRecord:
    return HarnessApprovalRecord(
        space_id=model.space_id,
        run_id=model.run_id,
        approval_key=model.approval_key,
        title=model.title,
        risk_level=model.risk_level,
        target_type=model.target_type,
        target_id=model.target_id,
        status=model.status,
        decision_reason=model.decision_reason,
        metadata=_json_object(model.metadata_payload),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _chat_session_record_from_model(
    model: HarnessChatSessionModel,
) -> HarnessChatSessionRecord:
    return HarnessChatSessionRecord(
        id=model.id,
        space_id=model.space_id,
        title=model.title,
        created_by=model.created_by,
        last_run_id=model.last_run_id,
        status=model.status,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _chat_message_record_from_model(
    model: HarnessChatMessageModel,
) -> HarnessChatMessageRecord:
    return HarnessChatMessageRecord(
        id=model.id,
        session_id=model.session_id,
        space_id=model.space_id,
        role=model.role,
        content=model.content,
        run_id=model.run_id,
        metadata=_json_object(model.metadata_payload),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _proposal_record_from_model(model: HarnessProposalModel) -> HarnessProposalRecord:
    return HarnessProposalRecord(
        id=model.id,
        space_id=model.space_id,
        run_id=model.run_id,
        proposal_type=model.proposal_type,
        source_kind=model.source_kind,
        source_key=model.source_key,
        title=model.title,
        summary=model.summary,
        status=model.status,
        confidence=model.confidence,
        ranking_score=model.ranking_score,
        reasoning_path=_json_object(model.reasoning_path),
        evidence_bundle=_json_object_list(model.evidence_bundle_payload),
        payload=_json_object(model.payload),
        metadata=_json_object(model.metadata_payload),
        decision_reason=model.decision_reason,
        decided_at=model.decided_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _schedule_record_from_model(model: HarnessScheduleModel) -> HarnessScheduleRecord:
    return HarnessScheduleRecord(
        id=model.id,
        space_id=model.space_id,
        harness_id=model.harness_id,
        title=model.title,
        cadence=model.cadence,
        status=model.status,
        created_by=model.created_by,
        configuration=_json_object(model.configuration_payload),
        metadata=_json_object(model.metadata_payload),
        last_run_id=model.last_run_id,
        last_run_at=model.last_run_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _research_state_record_from_model(
    model: HarnessResearchStateModel,
) -> HarnessResearchStateRecord:
    return HarnessResearchStateRecord(
        space_id=model.space_id,
        objective=model.objective,
        current_hypotheses=_json_string_list(model.current_hypotheses_payload),
        explored_questions=_json_string_list(model.explored_questions_payload),
        pending_questions=_json_string_list(model.pending_questions_payload),
        last_graph_snapshot_id=model.last_graph_snapshot_id,
        last_learning_cycle_at=model.last_learning_cycle_at,
        active_schedules=_json_string_list(model.active_schedules_payload),
        confidence_model=_json_object(model.confidence_model_payload),
        budget_policy=_json_object(model.budget_policy_payload),
        metadata=_json_object(model.metadata_payload),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _graph_snapshot_record_from_model(
    model: HarnessGraphSnapshotModel,
) -> HarnessGraphSnapshotRecord:
    return HarnessGraphSnapshotRecord(
        id=model.id,
        space_id=model.space_id,
        source_run_id=model.source_run_id,
        claim_ids=_json_string_list(model.claim_ids_payload),
        relation_ids=_json_string_list(model.relation_ids_payload),
        graph_document_hash=model.graph_document_hash,
        summary=_json_object(model.summary_payload),
        metadata=_json_object(model.metadata_payload),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class _SessionBackedStore:
    """Common session accessor for durable harness stores."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            message = "Session not provided"
            raise ValueError(message)
        return self._session


class SqlAlchemyHarnessApprovalStore(HarnessApprovalStore, _SessionBackedStore):
    """Persist harness intent plans and approval decisions in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def upsert_intent(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        summary: str,
        proposed_actions: tuple[HarnessApprovalAction, ...],
        metadata: JSONObject,
    ) -> HarnessRunIntentRecord:
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        model = self.session.get(HarnessIntentModel, normalized_run_id)
        if model is None:
            model = HarnessIntentModel(
                run_id=normalized_run_id,
                space_id=normalized_space_id,
                summary=summary,
                proposed_actions_payload=[
                    _action_payload(action) for action in proposed_actions
                ],
                metadata_payload=metadata,
            )
            self.session.add(model)
        else:
            model.space_id = normalized_space_id
            model.summary = summary
            model.proposed_actions_payload = [
                _action_payload(action) for action in proposed_actions
            ]
            model.metadata_payload = metadata

        self.session.execute(
            delete(HarnessApprovalModel).where(
                HarnessApprovalModel.run_id == normalized_run_id,
            ),
        )
        for action in proposed_actions:
            if not action.requires_approval:
                continue
            self.session.add(
                HarnessApprovalModel(
                    run_id=normalized_run_id,
                    space_id=normalized_space_id,
                    approval_key=action.approval_key,
                    title=action.title,
                    risk_level=action.risk_level,
                    target_type=action.target_type,
                    target_id=action.target_id,
                    status="pending",
                    decision_reason=None,
                    metadata_payload=action.metadata,
                ),
            )

        self.session.commit()
        self.session.refresh(model)
        return _intent_record_from_model(model)

    def get_intent(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunIntentRecord | None:
        model = self.session.get(HarnessIntentModel, str(run_id))
        if model is None or model.space_id != str(space_id):
            return None
        return _intent_record_from_model(model)

    def list_approvals(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> list[HarnessApprovalRecord]:
        stmt = (
            select(HarnessApprovalModel)
            .where(
                HarnessApprovalModel.space_id == str(space_id),
                HarnessApprovalModel.run_id == str(run_id),
            )
            .order_by(HarnessApprovalModel.created_at.asc())
        )
        models = self.session.execute(stmt).scalars().all()
        return [_approval_record_from_model(model) for model in models]

    def decide_approval(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        approval_key: str,
        status: str,
        decision_reason: str | None,
    ) -> HarnessApprovalRecord | None:
        normalized_status = status.strip().lower()
        if normalized_status not in {"approved", "rejected"}:
            message = f"Unsupported approval status '{status}'"
            raise ValueError(message)
        stmt = select(HarnessApprovalModel).where(
            HarnessApprovalModel.space_id == str(space_id),
            HarnessApprovalModel.run_id == str(run_id),
            HarnessApprovalModel.approval_key == approval_key,
        )
        model = self.session.execute(stmt).scalars().first()
        if model is None:
            return None
        model.status = normalized_status
        model.decision_reason = (
            decision_reason.strip()
            if isinstance(decision_reason, str) and decision_reason.strip() != ""
            else None
        )
        self.session.commit()
        self.session.refresh(model)
        return _approval_record_from_model(model)


class SqlAlchemyHarnessProposalStore(HarnessProposalStore, _SessionBackedStore):
    """Persist harness proposals in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def create_proposals(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        proposals: tuple[HarnessProposalDraft, ...],
    ) -> list[HarnessProposalRecord]:
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        created_models: list[HarnessProposalModel] = []
        for proposal in proposals:
            model = HarnessProposalModel(
                space_id=normalized_space_id,
                run_id=normalized_run_id,
                proposal_type=proposal.proposal_type,
                source_kind=proposal.source_kind,
                source_key=proposal.source_key,
                title=proposal.title,
                summary=proposal.summary,
                status="pending_review",
                confidence=proposal.confidence,
                ranking_score=proposal.ranking_score,
                reasoning_path=proposal.reasoning_path,
                evidence_bundle_payload=proposal.evidence_bundle,
                payload=proposal.payload,
                metadata_payload=proposal.metadata,
                decision_reason=None,
                decided_at=None,
            )
            self.session.add(model)
            created_models.append(model)
        self.session.commit()
        for model in created_models:
            self.session.refresh(model)
        return sorted(
            [_proposal_record_from_model(model) for model in created_models],
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
        stmt = select(HarnessProposalModel).where(
            HarnessProposalModel.space_id == str(space_id),
        )
        if isinstance(status, str) and status.strip() != "":
            stmt = stmt.where(HarnessProposalModel.status == status.strip())
        if isinstance(proposal_type, str) and proposal_type.strip() != "":
            stmt = stmt.where(
                HarnessProposalModel.proposal_type == proposal_type.strip(),
            )
        if run_id is not None:
            stmt = stmt.where(HarnessProposalModel.run_id == str(run_id))
        stmt = stmt.order_by(
            HarnessProposalModel.ranking_score.desc(),
            HarnessProposalModel.updated_at.desc(),
        )
        models = self.session.execute(stmt).scalars().all()
        return [_proposal_record_from_model(model) for model in models]

    def get_proposal(
        self,
        *,
        space_id: UUID | str,
        proposal_id: UUID | str,
    ) -> HarnessProposalRecord | None:
        model = self.session.get(HarnessProposalModel, str(proposal_id))
        if model is None or model.space_id != str(space_id):
            return None
        return _proposal_record_from_model(model)

    def decide_proposal(
        self,
        *,
        space_id: UUID | str,
        proposal_id: UUID | str,
        status: str,
        decision_reason: str | None,
        metadata: JSONObject | None = None,
    ) -> HarnessProposalRecord | None:
        normalized_status = status.strip().lower()
        if normalized_status not in {"promoted", "rejected"}:
            message = f"Unsupported proposal status '{status}'"
            raise ValueError(message)
        model = self.session.get(HarnessProposalModel, str(proposal_id))
        if model is None or model.space_id != str(space_id):
            return None
        if model.status != "pending_review":
            message = f"Proposal '{proposal_id}' is already decided with status '{model.status}'"
            raise ValueError(message)
        model.status = normalized_status
        model.decision_reason = (
            decision_reason.strip()
            if isinstance(decision_reason, str) and decision_reason.strip() != ""
            else None
        )
        model.decided_at = datetime.now(UTC).replace(tzinfo=None)
        model.metadata_payload = {
            **_json_object(model.metadata_payload),
            **(metadata or {}),
        }
        self.session.commit()
        self.session.refresh(model)
        return _proposal_record_from_model(model)


class SqlAlchemyHarnessScheduleStore(HarnessScheduleStore, _SessionBackedStore):
    """Persist harness schedule definitions in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def create_schedule(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        harness_id: str,
        title: str,
        cadence: str,
        created_by: UUID | str,
        configuration: JSONObject,
        metadata: JSONObject,
        status: str = "active",
    ) -> HarnessScheduleRecord:
        normalized_cadence = normalize_schedule_cadence(cadence)
        model = HarnessScheduleModel(
            space_id=str(space_id),
            harness_id=harness_id,
            title=title,
            cadence=normalized_cadence,
            status=status,
            created_by=str(created_by),
            configuration_payload=configuration,
            metadata_payload=metadata,
            last_run_id=None,
            last_run_at=None,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return _schedule_record_from_model(model)

    def list_schedules(
        self,
        *,
        space_id: UUID | str,
    ) -> list[HarnessScheduleRecord]:
        stmt = (
            select(HarnessScheduleModel)
            .where(HarnessScheduleModel.space_id == str(space_id))
            .order_by(HarnessScheduleModel.updated_at.desc())
        )
        models = self.session.execute(stmt).scalars().all()
        return [_schedule_record_from_model(model) for model in models]

    def list_all_schedules(
        self,
        *,
        status: str | None = None,
    ) -> list[HarnessScheduleRecord]:
        stmt = select(HarnessScheduleModel).order_by(
            HarnessScheduleModel.updated_at.desc(),
        )
        if isinstance(status, str) and status.strip() != "":
            stmt = stmt.where(HarnessScheduleModel.status == status.strip())
        models = self.session.execute(stmt).scalars().all()
        return [_schedule_record_from_model(model) for model in models]

    def get_schedule(
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
    ) -> HarnessScheduleRecord | None:
        model = self.session.get(HarnessScheduleModel, str(schedule_id))
        if model is None or model.space_id != str(space_id):
            return None
        return _schedule_record_from_model(model)

    def update_schedule(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
        title: str | None = None,
        cadence: str | None = None,
        status: str | None = None,
        configuration: JSONObject | None = None,
        metadata: JSONObject | None = None,
        last_run_id: UUID | str | None = None,
        last_run_at: datetime | None = None,
    ) -> HarnessScheduleRecord | None:
        model = self.session.get(HarnessScheduleModel, str(schedule_id))
        if model is None or model.space_id != str(space_id):
            return None
        if isinstance(title, str) and title.strip() != "":
            model.title = title
        if isinstance(cadence, str) and cadence.strip() != "":
            model.cadence = normalize_schedule_cadence(cadence)
        if isinstance(status, str) and status.strip() != "":
            model.status = status
        if configuration is not None:
            model.configuration_payload = configuration
        if metadata is not None:
            model.metadata_payload = metadata
        if last_run_id is not None:
            model.last_run_id = str(last_run_id)
        if last_run_at is not None:
            model.last_run_at = last_run_at
        self.session.commit()
        self.session.refresh(model)
        return _schedule_record_from_model(model)


class SqlAlchemyHarnessResearchStateStore(
    HarnessResearchStateStore,
    _SessionBackedStore,
):
    """Persist structured research state in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def get_state(
        self,
        *,
        space_id: UUID | str,
    ) -> HarnessResearchStateRecord | None:
        model = self.session.get(HarnessResearchStateModel, str(space_id))
        if model is None:
            return None
        return _research_state_record_from_model(model)

    def upsert_state(  # noqa: C901, PLR0912, PLR0913
        self,
        *,
        space_id: UUID | str,
        objective: str | None = None,
        current_hypotheses: list[str] | None = None,
        explored_questions: list[str] | None = None,
        pending_questions: list[str] | None = None,
        last_graph_snapshot_id: UUID | str | None = None,
        last_learning_cycle_at: datetime | None = None,
        active_schedules: list[str] | None = None,
        confidence_model: JSONObject | None = None,
        budget_policy: JSONObject | None = None,
        metadata: JSONObject | None = None,
    ) -> HarnessResearchStateRecord:
        normalized_objective = objective.strip() if isinstance(objective, str) else None
        if isinstance(normalized_objective, str) and normalized_objective == "":
            normalized_objective = None
        model = self.session.get(HarnessResearchStateModel, str(space_id))
        if model is None:
            model = HarnessResearchStateModel(
                space_id=str(space_id),
                objective=normalized_objective,
                current_hypotheses_payload=_json_string_list(current_hypotheses or []),
                explored_questions_payload=_json_string_list(explored_questions or []),
                pending_questions_payload=_json_string_list(pending_questions or []),
                last_graph_snapshot_id=(
                    str(last_graph_snapshot_id)
                    if last_graph_snapshot_id is not None
                    else None
                ),
                last_learning_cycle_at=last_learning_cycle_at,
                active_schedules_payload=_json_string_list(active_schedules or []),
                confidence_model_payload=confidence_model or {},
                budget_policy_payload=budget_policy or {},
                metadata_payload=metadata or {},
            )
            self.session.add(model)
        else:
            if objective is not None:
                model.objective = normalized_objective or None
            if current_hypotheses is not None:
                model.current_hypotheses_payload = _json_string_list(current_hypotheses)
            if explored_questions is not None:
                model.explored_questions_payload = _json_string_list(explored_questions)
            if pending_questions is not None:
                model.pending_questions_payload = _json_string_list(pending_questions)
            if last_graph_snapshot_id is not None:
                model.last_graph_snapshot_id = str(last_graph_snapshot_id)
            if last_learning_cycle_at is not None:
                model.last_learning_cycle_at = last_learning_cycle_at
            if active_schedules is not None:
                model.active_schedules_payload = _json_string_list(active_schedules)
            if confidence_model is not None:
                model.confidence_model_payload = confidence_model
            if budget_policy is not None:
                model.budget_policy_payload = budget_policy
            if metadata is not None:
                model.metadata_payload = {
                    **_json_object(model.metadata_payload),
                    **metadata,
                }
        self.session.commit()
        self.session.refresh(model)
        return _research_state_record_from_model(model)


class SqlAlchemyHarnessGraphSnapshotStore(
    HarnessGraphSnapshotStore,
    _SessionBackedStore,
):
    """Persist run-scoped graph snapshots in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def create_snapshot(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        source_run_id: UUID | str,
        claim_ids: list[str],
        relation_ids: list[str],
        graph_document_hash: str,
        summary: JSONObject,
        metadata: JSONObject | None = None,
    ) -> HarnessGraphSnapshotRecord:
        model = HarnessGraphSnapshotModel(
            space_id=str(space_id),
            source_run_id=str(source_run_id),
            claim_ids_payload=_json_string_list(claim_ids),
            relation_ids_payload=_json_string_list(relation_ids),
            graph_document_hash=graph_document_hash.strip(),
            summary_payload=summary,
            metadata_payload=metadata or {},
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return _graph_snapshot_record_from_model(model)

    def get_snapshot(
        self,
        *,
        space_id: UUID | str,
        snapshot_id: UUID | str,
    ) -> HarnessGraphSnapshotRecord | None:
        model = self.session.get(HarnessGraphSnapshotModel, str(snapshot_id))
        if model is None or model.space_id != str(space_id):
            return None
        return _graph_snapshot_record_from_model(model)

    def list_snapshots(
        self,
        *,
        space_id: UUID | str,
        limit: int = 20,
    ) -> list[HarnessGraphSnapshotRecord]:
        stmt = (
            select(HarnessGraphSnapshotModel)
            .where(HarnessGraphSnapshotModel.space_id == str(space_id))
            .order_by(HarnessGraphSnapshotModel.created_at.desc())
            .limit(max(limit, 0))
        )
        models = self.session.execute(stmt).scalars().all()
        return [_graph_snapshot_record_from_model(model) for model in models]


class SqlAlchemyHarnessChatSessionStore(HarnessChatSessionStore, _SessionBackedStore):
    """Persist chat sessions and messages in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def create_session(
        self,
        *,
        space_id: UUID | str,
        title: str,
        created_by: UUID | str,
        status: str = "active",
    ) -> HarnessChatSessionRecord:
        model = HarnessChatSessionModel(
            space_id=str(space_id),
            title=title,
            created_by=str(created_by),
            last_run_id=None,
            status=status,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return _chat_session_record_from_model(model)

    def list_sessions(self, *, space_id: UUID | str) -> list[HarnessChatSessionRecord]:
        stmt = (
            select(HarnessChatSessionModel)
            .where(HarnessChatSessionModel.space_id == str(space_id))
            .order_by(HarnessChatSessionModel.updated_at.desc())
        )
        models = self.session.execute(stmt).scalars().all()
        return [_chat_session_record_from_model(model) for model in models]

    def get_session(
        self,
        *,
        space_id: UUID | str,
        session_id: UUID | str,
    ) -> HarnessChatSessionRecord | None:
        model = self.session.get(HarnessChatSessionModel, str(session_id))
        if model is None or model.space_id != str(space_id):
            return None
        return _chat_session_record_from_model(model)

    def list_messages(
        self,
        *,
        space_id: UUID | str,
        session_id: UUID | str,
    ) -> list[HarnessChatMessageRecord]:
        stmt = (
            select(HarnessChatMessageModel)
            .where(
                HarnessChatMessageModel.space_id == str(space_id),
                HarnessChatMessageModel.session_id == str(session_id),
            )
            .order_by(HarnessChatMessageModel.created_at.asc())
        )
        models = self.session.execute(stmt).scalars().all()
        return [_chat_message_record_from_model(model) for model in models]

    def add_message(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        session_id: UUID | str,
        role: str,
        content: str,
        run_id: UUID | str | None = None,
        metadata: JSONObject | None = None,
    ) -> HarnessChatMessageRecord | None:
        session_model = self.session.get(HarnessChatSessionModel, str(session_id))
        if session_model is None or session_model.space_id != str(space_id):
            return None
        message_model = HarnessChatMessageModel(
            session_id=str(session_id),
            space_id=str(space_id),
            role=role,
            content=content,
            run_id=str(run_id) if run_id is not None else None,
            metadata_payload=metadata or {},
        )
        self.session.add(message_model)
        if run_id is not None:
            session_model.last_run_id = str(run_id)
        self.session.commit()
        self.session.refresh(message_model)
        return _chat_message_record_from_model(message_model)

    def update_session(
        self,
        *,
        space_id: UUID | str,
        session_id: UUID | str,
        title: str | None = None,
        last_run_id: UUID | str | None = None,
        status: str | None = None,
    ) -> HarnessChatSessionRecord | None:
        model = self.session.get(HarnessChatSessionModel, str(session_id))
        if model is None or model.space_id != str(space_id):
            return None
        if isinstance(title, str) and title.strip() != "":
            model.title = title
        if last_run_id is not None:
            model.last_run_id = str(last_run_id)
        if isinstance(status, str) and status.strip() != "":
            model.status = status
        self.session.commit()
        self.session.refresh(model)
        return _chat_session_record_from_model(model)


__all__ = [
    "SqlAlchemyHarnessApprovalStore",
    "SqlAlchemyHarnessChatSessionStore",
    "SqlAlchemyHarnessGraphSnapshotStore",
    "SqlAlchemyHarnessProposalStore",
    "SqlAlchemyHarnessResearchStateStore",
    "SqlAlchemyHarnessScheduleStore",
]
