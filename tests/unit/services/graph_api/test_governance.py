from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from services.graph_api.governance import (
    build_concept_repository as build_service_concept_repository,
)
from services.graph_api.governance import (
    build_concept_service as build_service_concept_service,
)
from services.graph_api.governance import (
    build_dictionary_repository as build_service_dictionary_repository,
)
from services.graph_api.governance import (
    build_dictionary_service as build_service_dictionary_service,
)
from src.application.services.kernel.concept_management_service import (
    ConceptManagementService,
)
from src.application.services.kernel.dictionary_management_service import (
    DictionaryManagementService,
)
from src.graph.core.dictionary_loading_extension import GraphDictionaryLoadingConfig
from src.graph.pack_registry import resolve_graph_domain_pack
from src.infrastructure.graph_governance.concept_repository import (
    GraphConceptRepository,
)
from src.infrastructure.graph_governance.dictionary_repository import (
    GraphDictionaryRepository,
)
from src.infrastructure.graph_governance.governance import (
    build_concept_repository,
    build_concept_service,
    build_dictionary_repository,
    build_dictionary_service,
)
from src.models.database.kernel.dictionary import DictionaryDomainContextModel


def test_build_governance_repositories_use_service_local_persistence(
    db_session: Session,
) -> None:
    dictionary_loading_extension = GraphDictionaryLoadingConfig(
        builtin_domain_contexts=resolve_graph_domain_pack().dictionary_domain_contexts,
    )
    dictionary_repo = build_dictionary_repository(
        db_session,
        dictionary_loading_extension=dictionary_loading_extension,
    )
    concept_repo = build_concept_repository(db_session)

    assert isinstance(dictionary_repo, GraphDictionaryRepository)
    assert isinstance(concept_repo, GraphConceptRepository)
    assert (
        dictionary_repo.__class__.__module__
        == "src.infrastructure.graph_governance.dictionary_repository"
    )
    assert (
        concept_repo.__class__.__module__
        == "src.infrastructure.graph_governance.concept_repository"
    )
    assert (
        build_service_dictionary_repository(
            db_session,
            dictionary_loading_extension=dictionary_loading_extension,
        ).__class__
        is dictionary_repo.__class__
    )
    assert (
        build_service_concept_repository(db_session).__class__ is concept_repo.__class__
    )


def test_build_governance_services_use_service_local_repositories(
    db_session: Session,
) -> None:
    dictionary_loading_extension = GraphDictionaryLoadingConfig(
        builtin_domain_contexts=resolve_graph_domain_pack().dictionary_domain_contexts,
    )
    dictionary_service = build_dictionary_service(
        db_session,
        dictionary_loading_extension=dictionary_loading_extension,
    )
    concept_service = build_concept_service(db_session)
    service_dictionary_service = build_service_dictionary_service(
        db_session,
        dictionary_loading_extension=dictionary_loading_extension,
    )
    service_concept_service = build_service_concept_service(db_session)

    assert isinstance(dictionary_service, DictionaryManagementService)
    assert isinstance(service_dictionary_service, DictionaryManagementService)
    assert isinstance(concept_service, ConceptManagementService)
    assert isinstance(service_concept_service, ConceptManagementService)

    assert dictionary_service._dictionary.__class__.__module__ == (  # noqa: SLF001
        "src.infrastructure.graph_governance.dictionary_repository"
    )
    assert concept_service._concepts.__class__.__module__ == (  # noqa: SLF001
        "src.infrastructure.graph_governance.concept_repository"
    )
    assert (
        service_dictionary_service._dictionary.__class__  # noqa: SLF001
        is dictionary_service._dictionary.__class__  # noqa: SLF001
    )
    assert (
        service_concept_service._concepts.__class__  # noqa: SLF001
        is concept_service._concepts.__class__  # noqa: SLF001
    )


def test_graph_governance_repository_seeds_pack_domain_contexts(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "biomedical")
    repository = build_dictionary_repository(
        db_session,
        dictionary_loading_extension=GraphDictionaryLoadingConfig(
            builtin_domain_contexts=resolve_graph_domain_pack().dictionary_domain_contexts,
        ),
    )

    repository._ensure_domain_context_reference("clinical")  # noqa: SLF001

    clinical = repository._session.get(
        DictionaryDomainContextModel,
        "clinical",
    )  # noqa: SLF001
    assert clinical is not None
    assert clinical.description == "Clinical and biomedical literature domain context."
