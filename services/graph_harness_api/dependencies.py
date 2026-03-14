"""Dependency providers for the standalone harness service."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from fastapi import Depends

from services.graph_harness_api.artana_stores import (
    ArtanaBackedHarnessArtifactStore,
    ArtanaBackedHarnessRunRegistry,
)
from services.graph_harness_api.composition import (
    GraphHarnessKernelRuntime,
    get_graph_harness_kernel_runtime,
)
from services.graph_harness_api.graph_chat_runtime import HarnessGraphChatRunner
from services.graph_harness_api.graph_client import GraphApiGateway
from services.graph_harness_api.graph_connection_runtime import (
    HarnessGraphConnectionRunner,
)
from services.graph_harness_api.graph_search_runtime import HarnessGraphSearchRunner
from services.graph_harness_api.graph_snapshot import HarnessGraphSnapshotStore
from services.graph_harness_api.harness_runtime import HarnessExecutionServices
from services.graph_harness_api.research_state import HarnessResearchStateStore
from services.graph_harness_api.sqlalchemy_stores import (
    SqlAlchemyHarnessApprovalStore,
    SqlAlchemyHarnessChatSessionStore,
    SqlAlchemyHarnessGraphSnapshotStore,
    SqlAlchemyHarnessProposalStore,
    SqlAlchemyHarnessResearchStateStore,
    SqlAlchemyHarnessScheduleStore,
)
from src.database.session import SessionLocal, get_session, set_session_rls_context
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator
    from contextlib import AbstractContextManager

    from sqlalchemy.orm import Session

    from services.graph_harness_api.approval_store import HarnessApprovalStore
    from services.graph_harness_api.artifact_store import HarnessArtifactStore
    from services.graph_harness_api.chat_sessions import HarnessChatSessionStore
    from services.graph_harness_api.graph_snapshot import HarnessGraphSnapshotStore
    from services.graph_harness_api.proposal_store import HarnessProposalStore
    from services.graph_harness_api.research_state import HarnessResearchStateStore
    from services.graph_harness_api.run_registry import HarnessRunRegistry
    from services.graph_harness_api.schedule_store import HarnessScheduleStore
    from src.application.services.pubmed_discovery_service import PubMedDiscoveryService

_SESSION_DEPENDENCY = Depends(get_session)
_KERNEL_RUNTIME_DEPENDENCY = Depends(get_graph_harness_kernel_runtime)


def get_approval_store(
    session: Session = _SESSION_DEPENDENCY,
) -> HarnessApprovalStore:
    """Return the durable approval store."""
    return SqlAlchemyHarnessApprovalStore(session)


def get_artifact_store(
    runtime: GraphHarnessKernelRuntime = _KERNEL_RUNTIME_DEPENDENCY,
) -> HarnessArtifactStore:
    """Return the Artana-backed artifact and workspace store."""
    return ArtanaBackedHarnessArtifactStore(runtime=runtime)


def get_run_registry(
    session: Session = _SESSION_DEPENDENCY,
    runtime: GraphHarnessKernelRuntime = _KERNEL_RUNTIME_DEPENDENCY,
) -> HarnessRunRegistry:
    """Return the Artana-backed harness run registry."""
    return ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)


def get_chat_session_store(
    session: Session = _SESSION_DEPENDENCY,
) -> HarnessChatSessionStore:
    """Return the durable chat session store."""
    return SqlAlchemyHarnessChatSessionStore(session)


def get_graph_snapshot_store(
    session: Session = _SESSION_DEPENDENCY,
) -> HarnessGraphSnapshotStore:
    """Return the durable graph snapshot store."""
    return SqlAlchemyHarnessGraphSnapshotStore(session)


def get_proposal_store(
    session: Session = _SESSION_DEPENDENCY,
) -> HarnessProposalStore:
    """Return the durable proposal store."""
    return SqlAlchemyHarnessProposalStore(session)


def get_research_state_store(
    session: Session = _SESSION_DEPENDENCY,
) -> HarnessResearchStateStore:
    """Return the durable research-state store."""
    return SqlAlchemyHarnessResearchStateStore(session)


def get_schedule_store(
    session: Session = _SESSION_DEPENDENCY,
) -> HarnessScheduleStore:
    """Return the durable schedule store."""
    return SqlAlchemyHarnessScheduleStore(session)


def get_graph_api_gateway() -> GraphApiGateway:
    """Return the graph API gateway used by harness flows."""
    return GraphApiGateway()


def get_graph_api_gateway_factory() -> Callable[[], GraphApiGateway]:
    """Return the graph API gateway factory used by worker-owned harness execution."""
    return GraphApiGateway


@contextmanager
def _pubmed_discovery_service_context() -> Iterator[PubMedDiscoveryService]:
    session = SessionLocal()
    set_session_rls_context(session, bypass_rls=True)
    try:
        yield get_legacy_dependency_container().create_pubmed_discovery_service(session)
    finally:
        session.close()


def get_pubmed_discovery_service() -> Generator[PubMedDiscoveryService]:
    """Return a scoped PubMed discovery service for literature refresh."""
    with _pubmed_discovery_service_context() as service:
        yield service


def get_pubmed_discovery_service_factory() -> Callable[
    [],
    AbstractContextManager[PubMedDiscoveryService],
]:
    """Return the scoped PubMed discovery-service factory used by harness execution."""
    return _pubmed_discovery_service_context


def get_graph_search_runner() -> HarnessGraphSearchRunner:
    """Return the harness-owned graph-search runner."""
    return HarnessGraphSearchRunner()


def get_graph_chat_runner() -> HarnessGraphChatRunner:
    """Return the harness-owned graph-chat runner."""
    return HarnessGraphChatRunner()


def get_graph_connection_runner() -> HarnessGraphConnectionRunner:
    """Return the harness-owned graph-connection runner."""
    return HarnessGraphConnectionRunner()


_RUN_REGISTRY_PROVIDER = Depends(get_run_registry)
_ARTIFACT_STORE_PROVIDER = Depends(get_artifact_store)
_CHAT_SESSION_STORE_PROVIDER = Depends(get_chat_session_store)
_PROPOSAL_STORE_PROVIDER = Depends(get_proposal_store)
_APPROVAL_STORE_PROVIDER = Depends(get_approval_store)
_RESEARCH_STATE_STORE_PROVIDER = Depends(get_research_state_store)
_GRAPH_SNAPSHOT_STORE_PROVIDER = Depends(get_graph_snapshot_store)
_SCHEDULE_STORE_PROVIDER = Depends(get_schedule_store)
_GRAPH_CONNECTION_RUNNER_PROVIDER = Depends(get_graph_connection_runner)
_GRAPH_CHAT_RUNNER_PROVIDER = Depends(get_graph_chat_runner)
_GRAPH_API_GATEWAY_FACTORY_PROVIDER = Depends(get_graph_api_gateway_factory)
_PUBMED_DISCOVERY_FACTORY_PROVIDER = Depends(get_pubmed_discovery_service_factory)


def get_harness_execution_services(  # noqa: PLR0913
    runtime: GraphHarnessKernelRuntime = _KERNEL_RUNTIME_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_PROVIDER,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_PROVIDER,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_PROVIDER,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_PROVIDER,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_PROVIDER,
    research_state_store: HarnessResearchStateStore = _RESEARCH_STATE_STORE_PROVIDER,
    graph_snapshot_store: HarnessGraphSnapshotStore = _GRAPH_SNAPSHOT_STORE_PROVIDER,
    schedule_store: HarnessScheduleStore = _SCHEDULE_STORE_PROVIDER,
    graph_connection_runner: HarnessGraphConnectionRunner = (
        _GRAPH_CONNECTION_RUNNER_PROVIDER
    ),
    graph_chat_runner: HarnessGraphChatRunner = _GRAPH_CHAT_RUNNER_PROVIDER,
    graph_api_gateway_factory: Callable[[], GraphApiGateway] = (
        _GRAPH_API_GATEWAY_FACTORY_PROVIDER
    ),
    pubmed_discovery_service_factory: Callable[
        [],
        AbstractContextManager[PubMedDiscoveryService],
    ] = _PUBMED_DISCOVERY_FACTORY_PROVIDER,
) -> HarnessExecutionServices:
    """Return the shared service bundle used by the harness dispatcher and worker."""
    return HarnessExecutionServices(
        runtime=runtime,
        run_registry=run_registry,
        artifact_store=artifact_store,
        chat_session_store=chat_session_store,
        proposal_store=proposal_store,
        approval_store=approval_store,
        research_state_store=research_state_store,
        graph_snapshot_store=graph_snapshot_store,
        schedule_store=schedule_store,
        graph_connection_runner=graph_connection_runner,
        graph_chat_runner=graph_chat_runner,
        graph_api_gateway_factory=graph_api_gateway_factory,
        pubmed_discovery_service_factory=pubmed_discovery_service_factory,
    )


__all__ = [
    "get_approval_store",
    "get_artifact_store",
    "get_chat_session_store",
    "get_graph_api_gateway_factory",
    "get_graph_chat_runner",
    "get_graph_connection_runner",
    "get_graph_api_gateway",
    "get_graph_snapshot_store",
    "get_graph_search_runner",
    "get_harness_execution_services",
    "get_pubmed_discovery_service",
    "get_pubmed_discovery_service_factory",
    "get_proposal_store",
    "get_research_state_store",
    "get_run_registry",
    "get_schedule_store",
]
