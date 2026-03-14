"""Integration tests for workflow monitor SSE endpoints."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from src.database import session as session_module
from src.domain.entities.user import UserRole
from src.infrastructure.security.jwt_provider import JWTProvider
from src.main import create_app
from src.models.database import Base
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.source_document import SourceDocumentModel
from src.models.database.user import UserModel
from src.models.database.user_data_source import (
    SourceStatusEnum,
    SourceTypeEnum,
    UserDataSourceModel,
)
from src.routes.research_spaces.workflow_monitor_routes import (
    get_source_workflow_monitor_service,
)
from tests.db_reset import reset_database

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject


def _using_postgres() -> bool:
    return os.getenv("DATABASE_URL", "").startswith("postgresql")


@contextmanager
def _session_for_api(db_session):
    if _using_postgres():
        session = session_module.SessionLocal()
        try:
            yield session
        finally:
            session.close()
    else:
        yield db_session


def _auth_headers(user: UserModel) -> dict[str, str]:
    secret = os.getenv(
        "AUTH_JWT_SECRET",
        "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz",
    )
    provider = JWTProvider(secret_key=secret)
    role_value = user.role.value if isinstance(user.role, UserRole) else str(user.role)
    token = provider.create_access_token(user_id=user.id, role=role_value)
    return {
        "Authorization": f"Bearer {token}",
        "X-TEST-USER-ID": str(user.id),
        "X-TEST-USER-EMAIL": user.email,
        "X-TEST-USER-ROLE": role_value,
    }


def _read_first_sse_event_lines(response) -> list[str]:
    first_chunk_text = ""
    for chunk in response.iter_bytes():
        if not chunk:
            continue
        first_chunk_text = chunk.decode("utf-8")
        break
    return first_chunk_text.splitlines()


def _read_all_sse_text(response) -> str:
    chunks = [chunk.decode("utf-8") for chunk in response.iter_bytes() if chunk]
    return "".join(chunks)


def _extract_sse_data(lines: list[str]) -> JSONObject:
    data_line = next((line for line in lines if line.startswith("data: ")), None)
    if data_line is None:
        return {}
    payload = json.loads(data_line.removeprefix("data: "))
    return payload if isinstance(payload, dict) else {}


def _build_monitor_payload(source_id: str) -> dict[str, object]:
    return {
        "source_snapshot": {"source_id": source_id, "name": "PubMed Source"},
        "last_run": None,
        "pipeline_runs": [],
        "documents": [],
        "document_status_counts": {},
        "extraction_queue": [],
        "extraction_queue_status_counts": {},
        "publication_extractions": [],
        "publication_extraction_status_counts": {},
        "relation_review": {},
        "graph_summary": None,
        "operational_counters": {
            "last_pipeline_status": "running",
            "pending_paper_count": 2,
            "pending_relation_review_count": 1,
            "extraction_extracted_count": 1,
            "extraction_failed_count": 1,
            "extraction_skipped_count": 0,
            "extraction_timeout_failed_count": 1,
            "graph_edges_delta_last_run": 3,
            "graph_edges_total": 9,
        },
        "warnings": [],
    }


class StubSourceWorkflowMonitorService:
    """Stub monitor service that emits deterministic payloads for stream tests."""

    def __init__(self) -> None:
        self.monitor_calls: list[dict[str, object]] = []
        self.events_calls: list[dict[str, object]] = []

    def get_source_workflow_monitor(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        run_id: str | None = None,
        limit: int = 50,
        include_graph: bool = True,
    ) -> dict[str, object]:
        self.monitor_calls.append(
            {
                "space_id": str(space_id),
                "source_id": str(source_id),
                "run_id": run_id,
                "limit": limit,
                "include_graph": include_graph,
            },
        )
        return _build_monitor_payload(str(source_id))

    def list_workflow_events(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        run_id: str | None = None,
        limit: int = 6,
        since: str | None = None,
    ) -> dict[str, object]:
        self.events_calls.append(
            {
                "space_id": str(space_id),
                "source_id": str(source_id),
                "run_id": run_id,
                "limit": limit,
                "since": since,
            },
        )
        events: list[dict[str, object]]
        if since is None:
            events = [
                {
                    "event_id": str(uuid4()),
                    "source_id": str(source_id),
                    "run_id": run_id,
                    "occurred_at": "2026-03-02T10:00:00+00:00",
                    "category": "run",
                    "stage": "ingestion",
                    "status": "running",
                    "message": "Bootstrap event",
                    "payload": {},
                },
            ]
        else:
            events = []
        return {"events": events}


class FlakySourceWorkflowMonitorService(StubSourceWorkflowMonitorService):
    """Stub service that fails after the bootstrap monitor payload."""

    def __init__(self) -> None:
        super().__init__()
        self._should_fail = False

    def get_source_workflow_monitor(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        run_id: str | None = None,
        limit: int = 50,
        include_graph: bool = True,
    ) -> dict[str, object]:
        if self._should_fail:
            msg = "workflow monitor failed"
            raise RuntimeError(msg)
        self._should_fail = True
        return super().get_source_workflow_monitor(
            space_id=space_id,
            source_id=source_id,
            run_id=run_id,
            limit=limit,
            include_graph=include_graph,
        )


@pytest.fixture(scope="function")
def test_client(test_engine):
    db_engine = session_module.engine if _using_postgres() else test_engine
    reset_database(db_engine, Base.metadata)
    app = create_app()
    client = TestClient(app)
    yield client
    reset_database(db_engine, Base.metadata)


@pytest.fixture
def researcher_user(db_session) -> UserModel:
    suffix = uuid4().hex[:10]
    with _session_for_api(db_session) as session:
        user = UserModel(
            email=f"workflow-stream-owner-{suffix}@example.com",
            username=f"wf-owner-{suffix}",
            full_name="Workflow Stream Owner",
            hashed_password="hashed_password",
            role=UserRole.RESEARCHER.value,
            status="active",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
    return user


@pytest.fixture
def outsider_user(db_session) -> UserModel:
    suffix = uuid4().hex[:10]
    with _session_for_api(db_session) as session:
        user = UserModel(
            email=f"workflow-stream-outsider-{suffix}@example.com",
            username=f"wf-outsider-{suffix}",
            full_name="Workflow Stream Outsider",
            hashed_password="hashed_password",
            role=UserRole.RESEARCHER.value,
            status="active",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
    return user


@pytest.fixture
def space(db_session, researcher_user) -> ResearchSpaceModel:
    suffix = uuid4().hex[:16]
    with _session_for_api(db_session) as session:
        space = ResearchSpaceModel(
            slug=f"workflow-stream-space-{suffix}",
            name="Workflow Stream Space",
            description="Research space for workflow stream tests",
            owner_id=researcher_user.id,
            status="active",
        )
        session.add(space)
        session.commit()
        session.refresh(space)
        session.expunge(space)
    return space


@pytest.fixture
def source(db_session, researcher_user, space) -> UserDataSourceModel:
    source_id = str(uuid4())
    with _session_for_api(db_session) as session:
        model = UserDataSourceModel(
            id=source_id,
            owner_id=str(researcher_user.id),
            research_space_id=str(space.id),
            name="Workflow Stream Source",
            description="PubMed source for workflow stream",
            source_type=SourceTypeEnum.PUBMED,
            configuration={"query": "MED13"},
            status=SourceStatusEnum.ACTIVE,
            ingestion_schedule={"enabled": False, "frequency": "manual"},
            quality_metrics={},
            tags=[],
            version="1.0",
        )
        session.add(model)
        session.commit()
        session.refresh(model)
        session.expunge(model)
    return model


def test_source_workflow_stream_requires_authentication(
    test_client: TestClient,
    space: ResearchSpaceModel,
    source: UserDataSourceModel,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_WORKFLOW_SSE", "true")
    response = test_client.get(
        f"/research-spaces/{space.id}/sources/{source.id}/workflow-stream",
    )
    assert response.status_code == 401


def test_source_workflow_stream_enforces_membership(
    space: ResearchSpaceModel,
    source: UserDataSourceModel,
    outsider_user: UserModel,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_WORKFLOW_SSE", "true")
    app = create_app()
    service = StubSourceWorkflowMonitorService()
    app.dependency_overrides[get_source_workflow_monitor_service] = lambda: service
    client = TestClient(app)

    response = client.get(
        f"/research-spaces/{space.id}/sources/{source.id}/workflow-stream",
        headers=_auth_headers(outsider_user),
    )
    app.dependency_overrides.clear()

    assert response.status_code == 403


def test_source_workflow_stream_emits_bootstrap_payload(
    researcher_user: UserModel,
    space: ResearchSpaceModel,
    source: UserDataSourceModel,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_WORKFLOW_SSE", "true")

    async def _always_disconnected(_: Request) -> bool:
        return True

    monkeypatch.setattr(Request, "is_disconnected", _always_disconnected)

    app = create_app()
    service = StubSourceWorkflowMonitorService()
    app.dependency_overrides[get_source_workflow_monitor_service] = lambda: service
    client = TestClient(app)

    response = client.get(
        f"/research-spaces/{space.id}/sources/{source.id}/workflow-stream",
        headers=_auth_headers(researcher_user),
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    lines = _read_first_sse_event_lines(response)
    assert "event: bootstrap" in lines
    payload = _extract_sse_data(lines)
    assert payload.get("run_id") is None
    monitor = payload.get("monitor")
    assert isinstance(monitor, dict)
    assert monitor.get("source_snapshot", {}).get("source_id") == source.id
    counters = monitor.get("operational_counters")
    assert isinstance(counters, dict)
    assert counters.get("extraction_timeout_failed_count") == 1
    assert isinstance(payload.get("events"), list)


def test_space_workflow_stream_emits_bootstrap_payload(
    researcher_user: UserModel,
    space: ResearchSpaceModel,
    source: UserDataSourceModel,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_WORKFLOW_SSE", "true")

    async def _always_disconnected(_: Request) -> bool:
        return True

    monkeypatch.setattr(Request, "is_disconnected", _always_disconnected)

    app = create_app()
    service = StubSourceWorkflowMonitorService()
    app.dependency_overrides[get_source_workflow_monitor_service] = lambda: service
    client = TestClient(app)

    response = client.get(
        f"/research-spaces/{space.id}/workflow-stream?source_ids={source.id}",
        headers=_auth_headers(researcher_user),
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    lines = _read_first_sse_event_lines(response)
    assert "event: bootstrap" in lines
    payload = _extract_sse_data(lines)
    sources = payload.get("sources")
    assert isinstance(sources, list)
    assert len(sources) == 1
    source_payload = sources[0]
    assert isinstance(source_payload, dict)
    assert source_payload.get("source_id") == source.id
    workflow_status = source_payload.get("workflow_status")
    assert isinstance(workflow_status, dict)
    assert workflow_status.get("last_pipeline_status") == "running"
    assert workflow_status.get("extraction_timeout_failed_count") == 1


def test_source_workflow_stream_emits_heartbeat_when_idle(
    researcher_user: UserModel,
    space: ResearchSpaceModel,
    source: UserDataSourceModel,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_WORKFLOW_SSE", "true")
    monkeypatch.setattr(
        "src.routes.research_spaces.workflow_monitor_stream_utils.STREAM_HEARTBEAT_SECONDS",
        0.0,
    )
    monkeypatch.setattr(
        "src.routes.research_spaces.workflow_monitor_stream_utils.STREAM_TICK_SECONDS",
        0.0,
    )

    disconnect_checks = {"count": 0}

    async def _disconnect_after_one_iteration(_: Request) -> bool:
        disconnect_checks["count"] += 1
        return disconnect_checks["count"] > 1

    monkeypatch.setattr(Request, "is_disconnected", _disconnect_after_one_iteration)

    app = create_app()
    service = StubSourceWorkflowMonitorService()
    app.dependency_overrides[get_source_workflow_monitor_service] = lambda: service
    client = TestClient(app)

    response = client.get(
        f"/research-spaces/{space.id}/sources/{source.id}/workflow-stream",
        headers=_auth_headers(researcher_user),
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = _read_all_sse_text(response)
    assert "event: bootstrap" in body
    assert "event: heartbeat" in body


def test_source_workflow_stream_emits_error_event_on_iteration_failure(
    researcher_user: UserModel,
    space: ResearchSpaceModel,
    source: UserDataSourceModel,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_WORKFLOW_SSE", "true")
    monkeypatch.setattr(
        "src.routes.research_spaces.workflow_monitor_stream_utils.STREAM_TICK_SECONDS",
        0.0,
    )

    disconnect_checks = {"count": 0}

    async def _disconnect_after_error(_: Request) -> bool:
        disconnect_checks["count"] += 1
        return disconnect_checks["count"] > 1

    monkeypatch.setattr(Request, "is_disconnected", _disconnect_after_error)

    app = create_app()
    service = FlakySourceWorkflowMonitorService()
    app.dependency_overrides[get_source_workflow_monitor_service] = lambda: service
    client = TestClient(app)

    response = client.get(
        f"/research-spaces/{space.id}/sources/{source.id}/workflow-stream",
        headers=_auth_headers(researcher_user),
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = _read_all_sse_text(response)
    assert "event: bootstrap" in body
    assert "event: error" in body


def test_source_workflow_monitor_reports_timeout_failure_counter(
    test_client: TestClient,
    db_session,
    researcher_user: UserModel,
    space: ResearchSpaceModel,
    source: UserDataSourceModel,
) -> None:
    with _session_for_api(db_session) as session:
        timeout_failed_doc = SourceDocumentModel(
            id=str(uuid4()),
            research_space_id=str(space.id),
            source_id=str(source.id),
            external_record_id="PMID-TIMEOUT",
            source_type=SourceTypeEnum.PUBMED.value,
            document_format="json",
            extraction_status="failed",
            metadata_payload={
                "entity_recognition_failure_reason": "agent_execution_timeout",
            },
        )
        failed_doc = SourceDocumentModel(
            id=str(uuid4()),
            research_space_id=str(space.id),
            source_id=str(source.id),
            external_record_id="PMID-FAILED",
            source_type=SourceTypeEnum.PUBMED.value,
            document_format="json",
            extraction_status="failed",
            metadata_payload={
                "entity_recognition_failure_reason": "dictionary_mutation_failed",
            },
        )
        extracted_doc = SourceDocumentModel(
            id=str(uuid4()),
            research_space_id=str(space.id),
            source_id=str(source.id),
            external_record_id="PMID-EXTRACTED",
            source_type=SourceTypeEnum.PUBMED.value,
            document_format="json",
            extraction_status="extracted",
            metadata_payload={},
        )
        session.add_all([timeout_failed_doc, failed_doc, extracted_doc])
        session.commit()

    response = test_client.get(
        (
            f"/research-spaces/{space.id}/sources/{source.id}/workflow-monitor"
            "?limit=10&include_graph=false"
        ),
        headers=_auth_headers(researcher_user),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    counters = payload.get("operational_counters", {})
    assert counters.get("extraction_extracted_count") == 1
    assert counters.get("extraction_failed_count") == 2
    assert counters.get("extraction_timeout_failed_count") == 1
