from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from src.infrastructure.factories import pipeline_orchestration_factory

if TYPE_CHECKING:
    from src.application.services._pipeline_orchestration_queue_types import (
        PipelineOrchestrationDependencies,
    )


class _StubSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _StubSchedulingService:
    @staticmethod
    def get_job_repository() -> object:
        return object()


@dataclass
class _StubAsyncService:
    result: object | None = None
    close_calls: int = 0
    calls: list[dict[str, object]] = field(default_factory=list)

    async def close(self) -> None:
        self.close_calls += 1

    async def process_pending_documents(self, **kwargs: object) -> object | None:
        self.calls.append(dict(kwargs))
        return self.result

    async def discover_connections_for_seed(self, **kwargs: object) -> object | None:
        self.calls.append(dict(kwargs))
        return self.result


class _StubContainer:
    def __init__(self) -> None:
        self.content_services: list[_StubAsyncService] = []
        self.entity_services: list[_StubAsyncService] = []
        self.graph_services: list[_StubAsyncService] = []
        self.graph_search_services: list[_StubAsyncService] = []

    def create_content_enrichment_service(
        self,
        session: object,
    ) -> _StubAsyncService:
        service = _StubAsyncService(result={"stage": "enrichment", "session": session})
        self.content_services.append(service)
        return service

    def create_entity_recognition_service(
        self,
        session: object,
    ) -> _StubAsyncService:
        service = _StubAsyncService(result={"stage": "extraction", "session": session})
        self.entity_services.append(service)
        return service

    def create_graph_connection_service(
        self,
        session: object,
    ) -> _StubAsyncService:
        service = _StubAsyncService(result={"stage": "graph", "session": session})
        self.graph_services.append(service)
        return service

    def create_graph_search_service(
        self,
        session: object,
    ) -> _StubAsyncService:
        service = _StubAsyncService(
            result={"stage": "graph_search", "session": session},
        )
        self.graph_search_services.append(service)
        return service


class _DummyPipelineOrchestrationService:
    def __init__(self, dependencies: PipelineOrchestrationDependencies) -> None:
        self.dependencies = dependencies


@pytest.mark.asyncio
async def test_pipeline_worker_context_keeps_shared_artana_services_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions: list[_StubSession] = []
    container = _StubContainer()

    def build_session() -> _StubSession:
        session = _StubSession()
        sessions.append(session)
        return session

    def set_rls_context(
        session: _StubSession,
        *,
        bypass_rls: bool = False,
        current_user_id: object | None = None,
        has_phi_access: bool = False,
        is_admin: bool = False,
    ) -> None:
        _ = (
            session,
            bypass_rls,
            current_user_id,
            has_phi_access,
            is_admin,
        )

    def build_scheduling_service(*, session: _StubSession) -> _StubSchedulingService:
        _ = session
        return _StubSchedulingService()

    monkeypatch.setattr(pipeline_orchestration_factory, "SessionLocal", build_session)
    monkeypatch.setattr(
        pipeline_orchestration_factory,
        "set_session_rls_context",
        set_rls_context,
    )
    monkeypatch.setattr(
        pipeline_orchestration_factory,
        "get_legacy_dependency_container",
        lambda: container,
    )
    monkeypatch.setattr(
        pipeline_orchestration_factory,
        "build_ingestion_scheduling_service",
        build_scheduling_service,
    )
    monkeypatch.setattr(
        pipeline_orchestration_factory,
        "SqlAlchemyResearchSpaceRepository",
        lambda session: {"session": session},
    )
    monkeypatch.setattr(
        pipeline_orchestration_factory,
        "SqlAlchemyPipelineRunEventRepository",
        lambda session: {"session": session},
    )
    monkeypatch.setattr(
        pipeline_orchestration_factory,
        "PipelineRunTraceService",
        lambda session, event_repository: {
            "session": session,
            "event_repository": event_repository,
        },
    )
    monkeypatch.setattr(
        pipeline_orchestration_factory,
        "PipelineOrchestrationService",
        _DummyPipelineOrchestrationService,
    )

    async with (
        pipeline_orchestration_factory.pipeline_orchestration_service_context() as (
            service
        )
    ):
        dependencies = service.dependencies
        enrichment_result = await dependencies.content_enrichment_stage_runner(
            limit=2,
            source_id=None,
            ingestion_job_id=None,
            research_space_id=None,
            source_type="pubmed",
            model_id=None,
            pipeline_run_id="run_1",
        )
        extraction_result = await dependencies.entity_recognition_stage_runner(
            limit=3,
            source_id=None,
            ingestion_job_id=None,
            research_space_id=None,
            source_type="pubmed",
            model_id=None,
            shadow_mode=False,
            pipeline_run_id="run_1",
        )
        graph_result = await dependencies.graph_connection_seed_runner(
            source_id="source_1",
            research_space_id="space_1",
            seed_entity_id="entity_1",
            source_type="pubmed",
            model_id=None,
            relation_types=None,
            max_depth=2,
            shadow_mode=False,
            pipeline_run_id="run_1",
            fallback_relations=None,
        )

    assert enrichment_result == {"stage": "enrichment", "session": sessions[1]}
    assert extraction_result == {"stage": "extraction", "session": sessions[2]}
    assert graph_result == {"stage": "graph", "session": sessions[3]}

    assert all(session.closed for session in sessions)
    assert len(sessions) == 4

    all_services = (
        container.content_services
        + container.entity_services
        + container.graph_services
        + container.graph_search_services
    )
    assert all(service.close_calls == 0 for service in all_services)
