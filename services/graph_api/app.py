"""FastAPI application factory for the standalone graph service."""

from __future__ import annotations

from fastapi import FastAPI

from src.graph.pack_registry import bootstrap_default_graph_domain_packs
from src.graph.product_contract import GRAPH_OPENAPI_URL, GRAPH_SERVICE_VERSION
from src.graph.runtime import create_graph_domain_pack

from .config import get_settings
from .database import SessionLocal
from .governance import seed_builtin_dictionary_entries
from .routers.claims import router as claims_router
from .routers.concepts import router as concepts_router
from .routers.dictionary import router as dictionary_router
from .routers.entities import router as entities_router
from .routers.graph_documents import router as graph_documents_router
from .routers.graph_views import router as graph_views_router
from .routers.health import router as health_router
from .routers.hypotheses import router as hypotheses_router
from .routers.observations import router as observations_router
from .routers.operations import router as operations_router
from .routers.provenance import router as provenance_router
from .routers.reasoning_paths import router as reasoning_paths_router
from .routers.relations import router as relations_router
from .routers.spaces import router as spaces_router


def create_app() -> FastAPI:
    """Create the standalone graph API application."""
    bootstrap_default_graph_domain_packs()
    graph_domain_pack = create_graph_domain_pack()
    with SessionLocal() as session:
        seed_builtin_dictionary_entries(
            session,
            dictionary_loading_extension=graph_domain_pack.dictionary_loading_extension,
        )
        session.commit()
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=GRAPH_SERVICE_VERSION,
        docs_url="/docs",
        openapi_url=GRAPH_OPENAPI_URL,
    )
    app.include_router(health_router)
    app.include_router(claims_router)
    app.include_router(concepts_router)
    app.include_router(dictionary_router)
    app.include_router(entities_router)
    app.include_router(graph_documents_router)
    app.include_router(graph_views_router)
    app.include_router(operations_router)
    app.include_router(hypotheses_router)
    app.include_router(observations_router)
    app.include_router(provenance_router)
    app.include_router(relations_router)
    app.include_router(reasoning_paths_router)
    app.include_router(spaces_router)
    return app


__all__ = ["create_app"]
