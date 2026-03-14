"""Worker-driven execution for queued graph-harness runs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import HTTPException
from sqlalchemy import select

from services.graph_harness_api.artana_stores import (
    ArtanaBackedHarnessArtifactStore,
    ArtanaBackedHarnessRunRegistry,
)
from services.graph_harness_api.composition import (
    GraphHarnessKernelRuntime,
    get_graph_harness_kernel_runtime,
)
from services.graph_harness_api.config import get_settings
from services.graph_harness_api.graph_chat_runtime import HarnessGraphChatRunner
from services.graph_harness_api.graph_client import GraphApiGateway
from services.graph_harness_api.graph_connection_runtime import (
    HarnessGraphConnectionRunner,
)
from services.graph_harness_api.harness_runtime import (
    HarnessExecutionResult,
    HarnessExecutionServices,
    execute_harness_run,
)
from services.graph_harness_api.run_registry import HarnessRunRecord
from services.graph_harness_api.sqlalchemy_stores import (
    SqlAlchemyHarnessApprovalStore,
    SqlAlchemyHarnessChatSessionStore,
    SqlAlchemyHarnessGraphSnapshotStore,
    SqlAlchemyHarnessProposalStore,
    SqlAlchemyHarnessResearchStateStore,
    SqlAlchemyHarnessScheduleStore,
)
from src.database.session import SessionLocal, set_session_rls_context
from src.models.database import HarnessRunModel

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

    from services.graph_harness_api.run_registry import HarnessRunRegistry
    from src.application.services.pubmed_discovery_service import PubMedDiscoveryService

LOGGER = logging.getLogger(__name__)
_DEFAULT_WORKER_ID = "graph-harness-worker"
_DEFAULT_LEASE_TTL_SECONDS = 300
_INLINE_WORKER_ID = "graph-harness-inline-worker"
_WORKER_EXECUTABLE_HARNESSES = (
    "research-bootstrap",
    "graph-chat",
    "continuous-learning",
    "mechanism-discovery",
    "claim-curation",
    "supervisor",
)


@dataclass(frozen=True, slots=True)
class WorkerRunResult:
    """One run processed or skipped by the worker."""

    run_id: str
    space_id: str
    harness_id: str
    outcome: str
    message: str | None


@dataclass(frozen=True, slots=True)
class WorkerTickResult:
    """Summary of one worker tick."""

    started_at: datetime
    completed_at: datetime
    scanned_run_count: int
    leased_run_count: int
    executed_run_count: int
    completed_run_count: int
    failed_run_count: int
    skipped_run_count: int
    results: tuple[WorkerRunResult, ...]
    errors: tuple[str, ...]


WorkerExecutionCallable = Callable[
    [HarnessRunRecord, HarnessExecutionServices],
    Awaitable[HarnessExecutionResult],
]


def _worker_error_message(run: HarnessRunRecord, exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return f"run:{run.id}:{detail}"
    return f"run:{run.id}:{exc}"


def _run_result_message(*, exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return str(exc)


def _result_from_run(
    *,
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
    message: str | None = None,
) -> WorkerRunResult:
    refreshed = (
        services.run_registry.get_run(space_id=run.space_id, run_id=run.id) or run
    )
    return WorkerRunResult(
        run_id=refreshed.id,
        space_id=refreshed.space_id,
        harness_id=refreshed.harness_id,
        outcome=refreshed.status,
        message=message,
    )


async def _default_execute_run(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    return await execute_harness_run(run=run, services=services)


def list_queued_worker_runs(
    *,
    session: Session,
    run_registry: HarnessRunRegistry,
) -> list[HarnessRunRecord]:
    """Return queued runs eligible for worker execution."""
    stmt = (
        select(HarnessRunModel)
        .where(HarnessRunModel.harness_id.in_(_WORKER_EXECUTABLE_HARNESSES))
        .order_by(HarnessRunModel.created_at.asc())
    )
    models = session.execute(stmt).scalars().all()
    queued_runs: list[HarnessRunRecord] = []
    for model in models:
        run = run_registry.get_run(space_id=model.space_id, run_id=model.id)
        if run is None or run.status != "queued":
            continue
        queued_runs.append(run)
    return queued_runs


async def execute_worker_run(  # noqa: PLR0913
    *,
    run: HarnessRunRecord,
    runtime: GraphHarnessKernelRuntime,
    services: HarnessExecutionServices,
    worker_id: str = _DEFAULT_WORKER_ID,
    lease_ttl_seconds: int = _DEFAULT_LEASE_TTL_SECONDS,
    execute_run: WorkerExecutionCallable = _default_execute_run,
) -> HarnessExecutionResult:
    """Execute one queued run after acquiring the Artana worker lease."""
    resolved_execute_run = services.execution_override or execute_run
    acquired = runtime.acquire_run_lease(
        run_id=run.id,
        tenant_id=run.space_id,
        worker_id=worker_id,
        ttl_seconds=lease_ttl_seconds,
    )
    if not acquired:
        msg = f"Lease already held for run '{run.id}'."
        raise RuntimeError(msg)
    try:
        current_run = services.run_registry.get_run(
            space_id=run.space_id,
            run_id=run.id,
        )
        if current_run is None or current_run.status != "queued":
            msg = f"Run '{run.id}' is no longer queued."
            raise RuntimeError(msg)
        return await resolved_execute_run(current_run, services)
    finally:
        runtime.release_run_lease(
            run_id=run.id,
            tenant_id=run.space_id,
            worker_id=worker_id,
        )


async def execute_inline_worker_run(  # noqa: PLR0913
    *,
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
    worker_id: str = _INLINE_WORKER_ID,
    lease_ttl_seconds: int = _DEFAULT_LEASE_TTL_SECONDS,
) -> HarnessExecutionResult:
    """Execute one queued run synchronously through the worker path."""
    return await execute_worker_run(
        run=run,
        runtime=services.runtime,
        services=services,
        worker_id=worker_id,
        lease_ttl_seconds=lease_ttl_seconds,
    )


async def run_worker_tick(  # noqa: PLR0913
    *,
    candidate_runs: list[HarnessRunRecord],
    runtime: GraphHarnessKernelRuntime,
    services: HarnessExecutionServices,
    worker_id: str = _DEFAULT_WORKER_ID,
    lease_ttl_seconds: int = _DEFAULT_LEASE_TTL_SECONDS,
    execute_run: WorkerExecutionCallable = _default_execute_run,
) -> WorkerTickResult:
    """Execute queued runs after acquiring an Artana worker lease."""
    started_at = datetime.now(UTC)
    resolved_execute_run = services.execution_override or execute_run
    leased_run_count = 0
    executed_run_count = 0
    completed_run_count = 0
    failed_run_count = 0
    skipped_run_count = 0
    results: list[WorkerRunResult] = []
    errors: list[str] = []

    for run in candidate_runs:
        acquired = runtime.acquire_run_lease(
            run_id=run.id,
            tenant_id=run.space_id,
            worker_id=worker_id,
            ttl_seconds=lease_ttl_seconds,
        )
        if not acquired:
            skipped_run_count += 1
            results.append(
                WorkerRunResult(
                    run_id=run.id,
                    space_id=run.space_id,
                    harness_id=run.harness_id,
                    outcome="lease_skipped",
                    message="Lease already held by another worker.",
                ),
            )
            continue
        leased_run_count += 1
        try:
            current_run = services.run_registry.get_run(
                space_id=run.space_id,
                run_id=run.id,
            )
            if current_run is None or current_run.status != "queued":
                skipped_run_count += 1
                results.append(
                    WorkerRunResult(
                        run_id=run.id,
                        space_id=run.space_id,
                        harness_id=run.harness_id,
                        outcome="skipped",
                        message="Run is no longer queued.",
                    ),
                )
                continue
            executed_run_count += 1
            await resolved_execute_run(current_run, services)
            worker_result = _result_from_run(run=current_run, services=services)
            if worker_result.outcome == "completed":
                completed_run_count += 1
            elif worker_result.outcome == "failed":
                failed_run_count += 1
            results.append(worker_result)
        except Exception as exc:  # noqa: BLE001
            failed_run_count += 1
            errors.append(_worker_error_message(run, exc))
            results.append(
                _result_from_run(
                    run=run,
                    services=services,
                    message=_run_result_message(exc=exc),
                ),
            )
        finally:
            runtime.release_run_lease(
                run_id=run.id,
                tenant_id=run.space_id,
                worker_id=worker_id,
            )

    return WorkerTickResult(
        started_at=started_at,
        completed_at=datetime.now(UTC),
        scanned_run_count=len(candidate_runs),
        leased_run_count=leased_run_count,
        executed_run_count=executed_run_count,
        completed_run_count=completed_run_count,
        failed_run_count=failed_run_count,
        skipped_run_count=skipped_run_count,
        results=tuple(results),
        errors=tuple(errors),
    )


async def run_service_worker_tick(
    *,
    worker_id: str = _DEFAULT_WORKER_ID,
    lease_ttl_seconds: int = _DEFAULT_LEASE_TTL_SECONDS,
) -> WorkerTickResult:
    """Run one worker tick against the service's durable stores."""
    with SessionLocal() as session:
        set_session_rls_context(session, bypass_rls=False)
        runtime = get_graph_harness_kernel_runtime()
        run_registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
        artifact_store = ArtanaBackedHarnessArtifactStore(runtime=runtime)
        services = HarnessExecutionServices(
            runtime=runtime,
            run_registry=run_registry,
            artifact_store=artifact_store,
            chat_session_store=SqlAlchemyHarnessChatSessionStore(session),
            proposal_store=SqlAlchemyHarnessProposalStore(session),
            approval_store=SqlAlchemyHarnessApprovalStore(session),
            research_state_store=SqlAlchemyHarnessResearchStateStore(session),
            graph_snapshot_store=SqlAlchemyHarnessGraphSnapshotStore(session),
            schedule_store=SqlAlchemyHarnessScheduleStore(session),
            graph_connection_runner=HarnessGraphConnectionRunner(),
            graph_chat_runner=HarnessGraphChatRunner(),
            graph_api_gateway_factory=GraphApiGateway,
            pubmed_discovery_service_factory=lambda: _pubmed_discovery_service_context(),
        )
        candidate_runs = list_queued_worker_runs(
            session=session,
            run_registry=run_registry,
        )
        return await run_worker_tick(
            candidate_runs=candidate_runs,
            runtime=runtime,
            services=services,
            worker_id=worker_id,
            lease_ttl_seconds=lease_ttl_seconds,
        )


@contextmanager
def _pubmed_discovery_service_context() -> Iterator[PubMedDiscoveryService]:
    from services.graph_harness_api.dependencies import get_pubmed_discovery_service

    generator = get_pubmed_discovery_service()
    service = next(generator)
    try:
        yield service
    finally:
        generator.close()


async def run_worker_loop(
    *,
    poll_seconds: float,
    run_once: bool,
    worker_id: str = _DEFAULT_WORKER_ID,
    lease_ttl_seconds: int = _DEFAULT_LEASE_TTL_SECONDS,
) -> None:
    """Run the worker loop until stopped or after one tick."""
    if poll_seconds <= 0:
        msg = "poll_seconds must be greater than zero"
        raise ValueError(msg)
    while True:
        result = await run_service_worker_tick(
            worker_id=worker_id,
            lease_ttl_seconds=lease_ttl_seconds,
        )
        LOGGER.info(
            "Harness worker tick completed: scanned=%s leased=%s executed=%s completed=%s failed=%s skipped=%s errors=%s",
            result.scanned_run_count,
            result.leased_run_count,
            result.executed_run_count,
            result.completed_run_count,
            result.failed_run_count,
            result.skipped_run_count,
            len(result.errors),
        )
        if run_once:
            return
        await asyncio.sleep(poll_seconds)


def main() -> None:
    """Start the queued-run worker loop."""
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    asyncio.run(
        run_worker_loop(
            poll_seconds=settings.worker_poll_seconds,
            run_once=settings.worker_run_once,
            worker_id=settings.worker_id,
            lease_ttl_seconds=settings.worker_lease_ttl_seconds,
        ),
    )


if __name__ == "__main__":
    main()


__all__ = [
    "WorkerRunResult",
    "WorkerTickResult",
    "execute_inline_worker_run",
    "execute_worker_run",
    "list_queued_worker_runs",
    "main",
    "run_service_worker_tick",
    "run_worker_loop",
    "run_worker_tick",
]
