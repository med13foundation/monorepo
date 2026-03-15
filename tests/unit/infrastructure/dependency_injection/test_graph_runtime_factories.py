"""Focused tests for shared graph runtime repository builders."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.orm import Session

from src.application.services.kernel.kernel_relation_suggestion_service import (
    KernelRelationSuggestionService,
)
from src.graph.core.read_model import ProjectorBackedGraphReadModelUpdateDispatcher
from src.graph.core.relation_autopromotion_policy import AutoPromotionPolicy
from src.infrastructure.dependency_injection.graph_runtime_factories import (
    build_dictionary_repository,
    build_graph_read_model_update_dispatcher,
    build_relation_repository,
    create_kernel_relation_suggestion_service,
)
from src.infrastructure.graph_governance.dictionary_repository import (
    GraphDictionaryRepository,
)
from src.infrastructure.repositories.kernel.kernel_relation_repository import (
    SqlAlchemyKernelRelationRepository,
)


def test_build_relation_repository_injects_explicit_autopromotion_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_RELATION_AUTOPROMOTE_ENABLED", "0")
    monkeypatch.setenv("GRAPH_RELATION_AUTOPROMOTE_MIN_DISTINCT_SOURCES", "6")

    repository = build_relation_repository(cast("Session", object()))
    assert isinstance(repository, SqlAlchemyKernelRelationRepository)
    policy = repository._auto_promotion_policy  # noqa: SLF001

    assert isinstance(policy, AutoPromotionPolicy)
    assert policy.enabled is False
    assert policy.min_distinct_sources == 6


def test_build_dictionary_repository_injects_pack_domain_contexts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_extension = SimpleNamespace(
        builtin_domain_contexts=(
            SimpleNamespace(
                id="custom",
                display_name="Custom",
                description="Custom domain context.",
            ),
        ),
        builtin_relation_types=(),
        builtin_relation_synonyms=(),
    )
    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.graph_runtime_factories.create_graph_domain_pack",
        lambda: SimpleNamespace(dictionary_loading_extension=expected_extension),
    )

    repository = build_dictionary_repository(cast("Session", object()))

    assert isinstance(repository, GraphDictionaryRepository)
    assert (
        repository._builtin_domain_contexts
        == expected_extension.builtin_domain_contexts
    )  # noqa: SLF001
    assert repository._builtin_relation_types == ()  # noqa: SLF001
    assert repository._builtin_relation_synonyms == ()  # noqa: SLF001


def test_create_kernel_relation_suggestion_service_injects_pack_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_extension = SimpleNamespace(
        vector_candidate_limit=9,
        min_vector_similarity=0.25,
    )
    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.graph_runtime_factories.create_graph_domain_pack",
        lambda: SimpleNamespace(
            relation_suggestion_extension=expected_extension,
            dictionary_loading_extension=SimpleNamespace(
                builtin_domain_contexts=(),
                builtin_relation_types=(),
                builtin_relation_synonyms=(),
            ),
        ),
    )

    service = create_kernel_relation_suggestion_service(cast("Session", object()))

    assert isinstance(service, KernelRelationSuggestionService)
    assert service._relation_suggestion_extension == expected_extension  # noqa: SLF001


def test_build_graph_read_model_update_dispatcher_returns_runtime_adapter() -> None:
    dispatcher = build_graph_read_model_update_dispatcher(cast("Session", object()))

    assert isinstance(dispatcher, ProjectorBackedGraphReadModelUpdateDispatcher)
    assert "entity_claim_summary" in dispatcher.projectors
    assert "entity_mechanism_paths" in dispatcher.projectors
    assert "entity_neighbors" in dispatcher.projectors
    assert "entity_relation_summary" in dispatcher.projectors
