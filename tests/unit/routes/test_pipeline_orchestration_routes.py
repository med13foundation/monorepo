"""Unit tests for pipeline orchestration route dependency wiring."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from src.domain.entities.user import User, UserRole, UserStatus
from src.routes.research_spaces import pipeline_orchestration_routes as routes


class _StubSchedulingService:
    def get_job_repository(self) -> object:
        return object()


class _StubRepository:
    def __init__(self, session: object) -> None:
        self.session = session


def _build_user() -> User:
    return User(
        id=uuid4(),
        email="pipeline-user@example.com",
        username="pipeline-user",
        full_name="Pipeline User",
        hashed_password="hashed-password",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )


def test_get_pipeline_orchestration_service_uses_user_graph_service_search(
    monkeypatch,
) -> None:
    current_user = _build_user()
    sentinel_graph_seed_runner = object()
    sentinel_graph_search = object()
    graph_search_users: list[User] = []
    graph_seed_users: list[User] = []

    monkeypatch.setattr(
        routes,
        "build_graph_connection_seed_runner_for_user",
        lambda user: graph_seed_users.append(user) or sentinel_graph_seed_runner,
    )
    monkeypatch.setattr(
        routes,
        "build_graph_search_service_for_user",
        lambda user: graph_search_users.append(user) or sentinel_graph_search,
    )

    import src.infrastructure.dependency_injection.dependencies as dependency_module
    import src.infrastructure.repositories as repository_module

    monkeypatch.setattr(
        dependency_module,
        "get_legacy_dependency_container",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        repository_module,
        "SqlAlchemyResearchSpaceRepository",
        _StubRepository,
    )
    monkeypatch.setattr(
        repository_module,
        "SqlAlchemyPipelineRunEventRepository",
        _StubRepository,
    )

    service = routes.get_pipeline_orchestration_service(
        scheduling_service=_StubSchedulingService(),
        content_enrichment_service=object(),
        entity_recognition_service=object(),
        current_user=current_user,
        session=object(),
    )

    assert service._graph_search is sentinel_graph_search
    assert service._graph_seed_runner is sentinel_graph_seed_runner
    assert service._graph is None
    assert graph_search_users == [current_user]
    assert graph_seed_users == [current_user]
