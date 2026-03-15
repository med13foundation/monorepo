"""Artana harness wrappers for graph-harness workflow execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast
from uuid import UUID

from artana.harness import BaseHarness, HarnessContext, SupervisorHarness

from services.graph_harness_api.chat_workflow import (
    GraphChatMessageExecution,
    execute_graph_chat_message,
)
from services.graph_harness_api.claim_curation_runtime import (
    load_curatable_proposals,
    resume_claim_curation_run,
)
from services.graph_harness_api.claim_curation_workflow import (
    ClaimCurationRunExecution,
    execute_claim_curation_run_for_proposals,
)
from services.graph_harness_api.continuous_learning_runtime import (
    ContinuousLearningExecutionResult,
    execute_continuous_learning_run,
    normalize_seed_entity_ids,
)
from services.graph_harness_api.mechanism_discovery_runtime import (
    MechanismDiscoveryRunExecutionResult,
    execute_mechanism_discovery_run,
)
from services.graph_harness_api.research_bootstrap_runtime import (
    ResearchBootstrapExecutionResult,
    execute_research_bootstrap_run,
)
from services.graph_harness_api.run_budget import (
    budget_from_json,
    resolve_continuous_learning_run_budget,
)
from services.graph_harness_api.run_registry import HarnessRunRecord
from services.graph_harness_api.supervisor_runtime import (
    SupervisorExecutionResult,
    execute_supervisor_run,
    resume_supervisor_run,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from contextlib import AbstractContextManager

    from src.application.services.pubmed_discovery_service import PubMedDiscoveryService
    from src.type_definitions.common import JSONObject

    from .approval_store import HarnessApprovalStore
    from .artifact_store import HarnessArtifactStore
    from .chat_sessions import HarnessChatSessionStore
    from .composition import GraphHarnessKernelRuntime
    from .graph_chat_runtime import HarnessGraphChatRunner
    from .graph_client import GraphApiGateway
    from .graph_connection_runtime import HarnessGraphConnectionRunner
    from .graph_snapshot import HarnessGraphSnapshotStore
    from .proposal_store import HarnessProposalStore
    from .research_state import HarnessResearchStateStore
    from .run_registry import HarnessRunRegistry
    from .schedule_store import HarnessScheduleStore

HarnessExecutionResult = (
    ResearchBootstrapExecutionResult
    | ContinuousLearningExecutionResult
    | MechanismDiscoveryRunExecutionResult
    | ClaimCurationRunExecution
    | GraphChatMessageExecution
    | SupervisorExecutionResult
    | HarnessRunRecord
)


@dataclass(frozen=True, slots=True)
class HarnessExecutionServices:
    """Shared services required to execute one harness run."""

    runtime: GraphHarnessKernelRuntime
    run_registry: HarnessRunRegistry
    artifact_store: HarnessArtifactStore
    chat_session_store: HarnessChatSessionStore
    proposal_store: HarnessProposalStore
    approval_store: HarnessApprovalStore
    research_state_store: HarnessResearchStateStore
    graph_snapshot_store: HarnessGraphSnapshotStore
    schedule_store: HarnessScheduleStore
    graph_connection_runner: HarnessGraphConnectionRunner
    graph_chat_runner: HarnessGraphChatRunner
    graph_api_gateway_factory: Callable[[], GraphApiGateway]
    pubmed_discovery_service_factory: Callable[
        [],
        AbstractContextManager[PubMedDiscoveryService],
    ]
    execution_override: (
        Callable[
            [HarnessRunRecord, HarnessExecutionServices],
            Awaitable[HarnessExecutionResult],
        ]
        | None
    ) = None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        trimmed = item.strip()
        if trimmed == "":
            continue
        normalized.append(trimmed)
    return normalized


def _string_value(payload: JSONObject, key: str, *, default: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) and value.strip() != "" else default


def _optional_string(payload: JSONObject, key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _bool_value(payload: JSONObject, key: str, *, default: bool) -> bool:
    value = payload.get(key)
    return value if isinstance(value, bool) else default


def _int_value(payload: JSONObject, key: str, *, default: int) -> int:
    value = payload.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _float_value(payload: JSONObject, key: str, *, default: float) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    return float(value)


def _uuid(value: str, *, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:  # pragma: no cover - defensive validation
        msg = f"Run payload field '{field_name}' must be a UUID."
        raise RuntimeError(msg) from exc


def _require_run(
    *,
    services: HarnessExecutionServices,
    context: HarnessContext,
) -> HarnessRunRecord:
    run = services.run_registry.get_run(
        space_id=context.tenant.tenant_id,
        run_id=context.run_id,
    )
    if run is None:
        msg = f"Harness run '{context.run_id}' was not found."
        raise RuntimeError(msg)
    return run


class ResearchBootstrapHarness(BaseHarness[ResearchBootstrapExecutionResult]):
    """Artana harness wrapper for research-bootstrap execution."""

    def __init__(self, *, services: HarnessExecutionServices) -> None:
        super().__init__(kernel=services.runtime.kernel)
        self._services = services

    async def step(
        self,
        *,
        context: HarnessContext,
    ) -> ResearchBootstrapExecutionResult:
        run = _require_run(services=self._services, context=context)
        payload = run.input_payload
        return await execute_research_bootstrap_run(
            space_id=UUID(run.space_id),
            title=run.title,
            objective=_optional_string(payload, "objective"),
            seed_entity_ids=_string_list(payload.get("seed_entity_ids")),
            source_type=_string_value(payload, "source_type", default="pubmed"),
            relation_types=_string_list(payload.get("relation_types")) or None,
            max_depth=_int_value(payload, "max_depth", default=2),
            max_hypotheses=_int_value(payload, "max_hypotheses", default=20),
            model_id=_optional_string(payload, "model_id"),
            run_registry=self._services.run_registry,
            artifact_store=self._services.artifact_store,
            graph_api_gateway=self._services.graph_api_gateway_factory(),
            graph_connection_runner=self._services.graph_connection_runner,
            proposal_store=self._services.proposal_store,
            research_state_store=self._services.research_state_store,
            graph_snapshot_store=self._services.graph_snapshot_store,
            schedule_store=self._services.schedule_store,
            runtime=self._services.runtime,
            existing_run=run,
        )


class ContinuousLearningHarness(BaseHarness[ContinuousLearningExecutionResult]):
    """Artana harness wrapper for continuous-learning execution."""

    def __init__(self, *, services: HarnessExecutionServices) -> None:
        super().__init__(kernel=services.runtime.kernel)
        self._services = services

    async def step(
        self,
        *,
        context: HarnessContext,
    ) -> ContinuousLearningExecutionResult:
        run = _require_run(services=self._services, context=context)
        payload = run.input_payload
        seed_entity_ids = normalize_seed_entity_ids(
            _string_list(payload.get("seed_entity_ids")),
        )
        return await execute_continuous_learning_run(
            space_id=UUID(run.space_id),
            title=run.title,
            seed_entity_ids=seed_entity_ids,
            source_type=_string_value(payload, "source_type", default="pubmed"),
            relation_types=_string_list(payload.get("relation_types")) or None,
            max_depth=_int_value(payload, "max_depth", default=2),
            max_new_proposals=_int_value(payload, "max_new_proposals", default=20),
            max_next_questions=_int_value(payload, "max_next_questions", default=5),
            model_id=_optional_string(payload, "model_id"),
            schedule_id=_optional_string(payload, "schedule_id"),
            run_budget=resolve_continuous_learning_run_budget(
                budget_from_json(payload.get("run_budget")),
            ),
            run_registry=self._services.run_registry,
            artifact_store=self._services.artifact_store,
            graph_api_gateway=self._services.graph_api_gateway_factory(),
            graph_connection_runner=self._services.graph_connection_runner,
            proposal_store=self._services.proposal_store,
            research_state_store=self._services.research_state_store,
            graph_snapshot_store=self._services.graph_snapshot_store,
            runtime=self._services.runtime,
            existing_run=run,
        )


class MechanismDiscoveryHarness(BaseHarness[MechanismDiscoveryRunExecutionResult]):
    """Artana harness wrapper for mechanism-discovery execution."""

    def __init__(self, *, services: HarnessExecutionServices) -> None:
        super().__init__(kernel=services.runtime.kernel)
        self._services = services

    async def step(
        self,
        *,
        context: HarnessContext,
    ) -> MechanismDiscoveryRunExecutionResult:
        run = _require_run(services=self._services, context=context)
        payload = run.input_payload
        return execute_mechanism_discovery_run(
            space_id=UUID(run.space_id),
            title=run.title,
            seed_entity_ids=tuple(_string_list(payload.get("seed_entity_ids"))),
            max_candidates=_int_value(payload, "max_candidates", default=10),
            max_reasoning_paths=_int_value(payload, "max_reasoning_paths", default=50),
            max_path_depth=_int_value(payload, "max_path_depth", default=4),
            min_path_confidence=_float_value(
                payload,
                "min_path_confidence",
                default=0.0,
            ),
            run_registry=self._services.run_registry,
            artifact_store=self._services.artifact_store,
            graph_api_gateway=self._services.graph_api_gateway_factory(),
            proposal_store=self._services.proposal_store,
            runtime=self._services.runtime,
            existing_run=run,
        )


class ClaimCurationHarness(BaseHarness[ClaimCurationRunExecution | HarnessRunRecord]):
    """Artana harness wrapper for claim-curation execution and resume."""

    def __init__(self, *, services: HarnessExecutionServices) -> None:
        super().__init__(kernel=services.runtime.kernel)
        self._services = services

    async def step(
        self,
        *,
        context: HarnessContext,
    ) -> ClaimCurationRunExecution | HarnessRunRecord:
        run = _require_run(services=self._services, context=context)
        payload = run.input_payload
        if self._services.approval_store.list_approvals(
            space_id=UUID(run.space_id),
            run_id=run.id,
        ):
            updated_run, _ = resume_claim_curation_run(
                space_id=UUID(run.space_id),
                run=run,
                approval_store=self._services.approval_store,
                proposal_store=self._services.proposal_store,
                run_registry=self._services.run_registry,
                artifact_store=self._services.artifact_store,
                runtime=self._services.runtime,
                graph_api_gateway=self._services.graph_api_gateway_factory(),
                resume_reason="worker_resume",
                resume_metadata={"executor": "artana_worker"},
            )
            return updated_run
        proposal_ids = tuple(_string_list(payload.get("proposal_ids")))
        proposals = load_curatable_proposals(
            space_id=UUID(run.space_id),
            proposal_ids=proposal_ids,
            proposal_store=self._services.proposal_store,
        )
        return execute_claim_curation_run_for_proposals(
            space_id=UUID(run.space_id),
            proposals=proposals,
            title=run.title,
            run_registry=self._services.run_registry,
            artifact_store=self._services.artifact_store,
            proposal_store=self._services.proposal_store,
            approval_store=self._services.approval_store,
            graph_api_gateway=self._services.graph_api_gateway_factory(),
            runtime=self._services.runtime,
            existing_run=run,
        )


class GraphChatHarness(BaseHarness[GraphChatMessageExecution]):
    """Artana harness wrapper for graph-chat execution."""

    def __init__(self, *, services: HarnessExecutionServices) -> None:
        super().__init__(kernel=services.runtime.kernel)
        self._services = services

    async def step(
        self,
        *,
        context: HarnessContext,
    ) -> GraphChatMessageExecution:
        run = _require_run(services=self._services, context=context)
        payload = run.input_payload
        session_id = _uuid(
            _string_value(payload, "session_id", default=""),
            field_name="session_id",
        )
        session = self._services.chat_session_store.get_session(
            space_id=UUID(run.space_id),
            session_id=session_id,
        )
        if session is None:
            msg = f"Chat session '{session_id}' not found for run '{run.id}'."
            raise RuntimeError(msg)
        with (
            self._services.pubmed_discovery_service_factory() as pubmed_discovery_service
        ):
            return await execute_graph_chat_message(
                space_id=UUID(run.space_id),
                session=session,
                content=_string_value(payload, "question", default=""),
                model_id=_optional_string(payload, "model_id"),
                max_depth=_int_value(payload, "max_depth", default=2),
                top_k=_int_value(payload, "top_k", default=5),
                include_evidence_chains=_bool_value(
                    payload,
                    "include_evidence_chains",
                    default=False,
                ),
                current_user_id=_string_value(
                    payload,
                    "current_user_id",
                    default=run.space_id,
                ),
                chat_session_store=self._services.chat_session_store,
                run_registry=self._services.run_registry,
                artifact_store=self._services.artifact_store,
                runtime=self._services.runtime,
                graph_api_gateway=self._services.graph_api_gateway_factory(),
                graph_chat_runner=self._services.graph_chat_runner,
                graph_snapshot_store=self._services.graph_snapshot_store,
                pubmed_discovery_service=pubmed_discovery_service,
                research_state_store=self._services.research_state_store,
                existing_run=run,
            )


class ResearchSupervisorHarness(
    SupervisorHarness,
):
    """Artana supervisor harness wrapper for composed orchestration."""

    def __init__(self, *, services: HarnessExecutionServices) -> None:
        super().__init__(kernel=services.runtime.kernel)
        self._services = services

    async def step(
        self,
        *,
        context: HarnessContext,
    ) -> SupervisorExecutionResult | HarnessRunRecord:
        run = _require_run(services=self._services, context=context)
        workspace = self._services.artifact_store.get_workspace(
            space_id=UUID(run.space_id),
            run_id=run.id,
        )
        if workspace is not None:
            curation_run_id = workspace.snapshot.get("curation_run_id")
            if isinstance(curation_run_id, str) and curation_run_id.strip() != "":
                updated_run, _ = resume_supervisor_run(
                    space_id=UUID(run.space_id),
                    run=run,
                    approval_store=self._services.approval_store,
                    proposal_store=self._services.proposal_store,
                    run_registry=self._services.run_registry,
                    artifact_store=self._services.artifact_store,
                    runtime=self._services.runtime,
                    graph_api_gateway=self._services.graph_api_gateway_factory(),
                    resume_reason="worker_resume",
                    resume_metadata={"executor": "artana_worker"},
                )
                return updated_run
        payload = run.input_payload
        with (
            self._services.pubmed_discovery_service_factory() as pubmed_discovery_service
        ):
            return await execute_supervisor_run(
                space_id=UUID(run.space_id),
                title=run.title,
                objective=_optional_string(payload, "objective"),
                seed_entity_ids=_string_list(payload.get("seed_entity_ids")),
                source_type=_string_value(payload, "source_type", default="pubmed"),
                relation_types=_string_list(payload.get("relation_types")) or None,
                max_depth=_int_value(payload, "max_depth", default=2),
                max_hypotheses=_int_value(payload, "max_hypotheses", default=20),
                model_id=_optional_string(payload, "model_id"),
                include_chat=_bool_value(payload, "include_chat", default=True),
                include_curation=_bool_value(payload, "include_curation", default=True),
                curation_source=_string_value(
                    payload,
                    "curation_source",
                    default="bootstrap",
                ),
                briefing_question=_optional_string(payload, "briefing_question"),
                chat_max_depth=_int_value(payload, "chat_max_depth", default=2),
                chat_top_k=_int_value(payload, "chat_top_k", default=5),
                chat_include_evidence_chains=_bool_value(
                    payload,
                    "chat_include_evidence_chains",
                    default=False,
                ),
                curation_proposal_limit=_int_value(
                    payload,
                    "curation_proposal_limit",
                    default=5,
                ),
                current_user_id=_string_value(
                    payload,
                    "current_user_id",
                    default=run.space_id,
                ),
                run_registry=self._services.run_registry,
                artifact_store=self._services.artifact_store,
                chat_session_store=self._services.chat_session_store,
                proposal_store=self._services.proposal_store,
                approval_store=self._services.approval_store,
                research_state_store=self._services.research_state_store,
                graph_snapshot_store=self._services.graph_snapshot_store,
                schedule_store=self._services.schedule_store,
                graph_connection_runner=self._services.graph_connection_runner,
                graph_chat_runner=self._services.graph_chat_runner,
                _pubmed_discovery_service=pubmed_discovery_service,
                runtime=self._services.runtime,
                parent_graph_api_gateway=self._services.graph_api_gateway_factory(),
                bootstrap_graph_api_gateway=self._services.graph_api_gateway_factory(),
                chat_graph_api_gateway=self._services.graph_api_gateway_factory(),
                curation_graph_api_gateway=self._services.graph_api_gateway_factory(),
                existing_run=run,
            )


def build_harness_for_run(
    *,
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> BaseHarness[HarnessExecutionResult]:
    """Return the Artana harness wrapper bound to one queued run."""
    harness_id = run.harness_id
    if harness_id == "research-bootstrap":
        return cast(
            "BaseHarness[HarnessExecutionResult]",
            ResearchBootstrapHarness(services=services),
        )
    if harness_id == "graph-chat":
        return cast(
            "BaseHarness[HarnessExecutionResult]",
            GraphChatHarness(services=services),
        )
    if harness_id == "continuous-learning":
        return cast(
            "BaseHarness[HarnessExecutionResult]",
            ContinuousLearningHarness(services=services),
        )
    if harness_id == "mechanism-discovery":
        return cast(
            "BaseHarness[HarnessExecutionResult]",
            MechanismDiscoveryHarness(services=services),
        )
    if harness_id == "claim-curation":
        return cast(
            "BaseHarness[HarnessExecutionResult]",
            ClaimCurationHarness(services=services),
        )
    if harness_id == "supervisor":
        return cast(
            "BaseHarness[HarnessExecutionResult]",
            ResearchSupervisorHarness(services=services),
        )
    msg = f"Worker execution is not supported for harness '{harness_id}'."
    raise RuntimeError(msg)


async def execute_harness_run(
    *,
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    """Execute one harness run through the Artana harness wrapper."""
    harness = build_harness_for_run(run=run, services=services)
    return await harness.run(
        run_id=run.id,
        tenant=services.runtime.tenant_context(tenant_id=run.space_id),
    )


__all__ = [
    "HarnessExecutionResult",
    "HarnessExecutionServices",
    "build_harness_for_run",
    "execute_harness_run",
]
