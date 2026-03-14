"""Shared Artana-kernel composition for graph-harness runtime services."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from threading import Event, Thread
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

from src.infrastructure.llm.state.shared_postgres_store import (
    get_shared_artana_postgres_store,
)

from .policy import build_graph_harness_policy
from .tool_registry import build_graph_harness_tool_registry

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from artana import ResumePoint, RunProgress, RunStatus, StepToolResult
    from artana.events import KernelEvent, RunSummaryPayload
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
    from artana.ports.model import ModelRequest, ModelResult

_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
except ImportError as exc:  # pragma: no cover - environment dependent
    _ARTANA_IMPORT_ERROR = exc

OutputT = TypeVar("OutputT", bound=BaseModel)
ResultT = TypeVar("ResultT")
_DEFAULT_TENANT_BUDGET_USD = 10.0


class _NoopModelPort:
    """Minimal model-port stub for lifecycle, artifact, and worker operations."""

    async def complete(
        self,
        request: ModelRequest[OutputT],
    ) -> ModelResult[OutputT]:
        _ = request
        msg = "Model execution is not supported by the graph-harness lifecycle runtime."
        raise RuntimeError(msg)


class _AsyncLoopRunner:
    """Run Artana async APIs from synchronous store adapters."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._started = Event()
        self._closed = False
        self._thread = Thread(
            target=self._run_loop,
            daemon=True,
            name="graph-harness-artana-loop",
        )
        self._thread.start()
        if not self._started.wait(timeout=2.0):
            msg = "Timed out starting the graph-harness Artana event loop."
            raise RuntimeError(msg)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._started.set()
        self._loop.run_forever()

    def run(self, coroutine: Coroutine[object, object, ResultT]) -> ResultT:
        if self._closed:
            msg = "Graph-harness Artana event loop is closed."
            raise RuntimeError(msg)
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2.0)
        if not self._thread.is_alive():
            self._loop.close()


@dataclass(slots=True)
class GraphHarnessKernelRuntime:
    """Shared synchronous façade over the service-local Artana kernel."""

    kernel: ArtanaKernel
    _runner: _AsyncLoopRunner

    def tenant_context(self, *, tenant_id: str) -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=_DEFAULT_TENANT_BUDGET_USD,
        )

    def ensure_run(self, *, run_id: str, tenant_id: str) -> bool:
        tenant = self.tenant_context(tenant_id=tenant_id)
        try:
            self._runner.run(self.kernel.load_run(run_id=run_id, tenant=tenant))
        except ValueError:
            self._runner.run(self.kernel.start_run(run_id=run_id, tenant=tenant))
            return True
        return False

    def append_run_summary(  # noqa: PLR0913
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        summary_json: str,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> int:
        tenant = self.tenant_context(tenant_id=tenant_id)
        return self._runner.run(
            self.kernel.append_run_summary(
                run_id=run_id,
                tenant=tenant,
                summary_type=summary_type,
                summary_json=summary_json,
                step_key=step_key,
                parent_step_key=parent_step_key,
            ),
        )

    def get_latest_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
    ) -> RunSummaryPayload | None:
        tenant = self.tenant_context(tenant_id=tenant_id)
        return self._runner.run(
            self.kernel.get_latest_run_summary(
                run_id=run_id,
                tenant=tenant,
                summary_type=summary_type,
            ),
        )

    def get_events(
        self,
        *,
        run_id: str,
        tenant_id: str,
    ) -> tuple[KernelEvent, ...]:
        tenant = self.tenant_context(tenant_id=tenant_id)
        return self._runner.run(self.kernel.get_events(run_id=run_id, tenant=tenant))

    def get_run_status(
        self,
        *,
        run_id: str,
        tenant_id: str,
    ) -> RunStatus | None:
        tenant = self.tenant_context(tenant_id=tenant_id)
        try:
            return self._runner.run(
                self.kernel.get_run_status(run_id=run_id, tenant=tenant),
            )
        except ValueError:
            return None

    def get_run_progress(
        self,
        *,
        run_id: str,
        tenant_id: str,
    ) -> RunProgress | None:
        tenant = self.tenant_context(tenant_id=tenant_id)
        try:
            return self._runner.run(
                self.kernel.get_run_progress(run_id=run_id, tenant=tenant),
            )
        except ValueError:
            return None

    def get_resume_point(
        self,
        *,
        run_id: str,
        tenant_id: str,
    ) -> ResumePoint | None:
        tenant = self.tenant_context(tenant_id=tenant_id)
        try:
            return self._runner.run(
                self.kernel.resume_point(run_id=run_id, tenant=tenant),
            )
        except ValueError:
            return None

    def acquire_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        tenant = self.tenant_context(tenant_id=tenant_id)
        return self._runner.run(
            self.kernel.acquire_run_lease(
                run_id=run_id,
                tenant=tenant,
                worker_id=worker_id,
                ttl_seconds=ttl_seconds,
            ),
        )

    def release_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
    ) -> bool:
        tenant = self.tenant_context(tenant_id=tenant_id)
        return self._runner.run(
            self.kernel.release_run_lease(
                run_id=run_id,
                tenant=tenant,
                worker_id=worker_id,
            ),
        )

    def explain_tool_allowlist(
        self,
        *,
        tenant_id: str,
        run_id: str,
        visible_tool_names: set[str] | None = None,
    ) -> dict[str, object]:
        tenant = self.tenant_context(tenant_id=tenant_id)
        return self._runner.run(
            self.kernel.explain_tool_allowlist(
                tenant=tenant,
                run_id=run_id,
                visible_tool_names=visible_tool_names,
            ),
        )

    def step_tool(  # noqa: PLR0913
        self,
        *,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        arguments: BaseModel,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> StepToolResult:
        tenant = self.tenant_context(tenant_id=tenant_id)
        return self._runner.run(
            self.kernel.step_tool(
                run_id=run_id,
                tenant=tenant,
                tool_name=tool_name,
                arguments=arguments,
                step_key=step_key,
                parent_step_key=parent_step_key,
            ),
        )

    def reconcile_tool(  # noqa: PLR0913
        self,
        *,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        arguments: BaseModel,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> str:
        tenant = self.tenant_context(tenant_id=tenant_id)
        return self._runner.run(
            self.kernel.reconcile_tool(
                run_id=run_id,
                tenant=tenant,
                tool_name=tool_name,
                arguments=arguments,
                step_key=step_key,
                parent_step_key=parent_step_key,
            ),
        )

    def close(self) -> None:
        self._runner.close()


@lru_cache(maxsize=1)
def get_graph_harness_kernel_runtime() -> GraphHarnessKernelRuntime:
    """Return the shared Artana-kernel lifecycle runtime for the harness service."""
    if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import guard
        msg = "artana-kernel is required for graph-harness runtime alignment."
        raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR
    runner = _AsyncLoopRunner()
    kernel = ArtanaKernel(
        store=get_shared_artana_postgres_store(),
        model_port=_NoopModelPort(),
        tool_port=build_graph_harness_tool_registry(),
        policy=build_graph_harness_policy(),
    )
    return GraphHarnessKernelRuntime(kernel=kernel, _runner=runner)


__all__ = ["GraphHarnessKernelRuntime", "get_graph_harness_kernel_runtime"]
