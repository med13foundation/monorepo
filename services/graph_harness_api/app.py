"""FastAPI application factory for the standalone harness service."""

from __future__ import annotations

from fastapi import FastAPI

from .config import get_settings
from .routers.approvals import router as approvals_router
from .routers.artifacts import router as artifacts_router
from .routers.chat import router as chat_router
from .routers.continuous_learning_runs import (
    router as continuous_learning_runs_router,
)
from .routers.graph_connection_runs import router as graph_connection_runs_router
from .routers.graph_curation_runs import router as graph_curation_runs_router
from .routers.graph_search_runs import router as graph_search_runs_router
from .routers.harnesses import router as harnesses_router
from .routers.health import router as health_router
from .routers.hypothesis_runs import router as hypothesis_runs_router
from .routers.mechanism_discovery_runs import (
    router as mechanism_discovery_runs_router,
)
from .routers.proposals import router as proposals_router
from .routers.research_bootstrap_runs import (
    router as research_bootstrap_runs_router,
)
from .routers.runs import router as runs_router
from .routers.schedules import router as schedules_router
from .routers.supervisor_runs import router as supervisor_runs_router


def create_app() -> FastAPI:
    """Create the standalone harness API application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        docs_url="/docs",
        openapi_url=settings.openapi_url,
    )
    app.include_router(approvals_router)
    app.include_router(health_router)
    app.include_router(artifacts_router)
    app.include_router(chat_router)
    app.include_router(continuous_learning_runs_router)
    app.include_router(graph_connection_runs_router)
    app.include_router(graph_curation_runs_router)
    app.include_router(graph_search_runs_router)
    app.include_router(hypothesis_runs_router)
    app.include_router(mechanism_discovery_runs_router)
    app.include_router(harnesses_router)
    app.include_router(proposals_router)
    app.include_router(research_bootstrap_runs_router)
    app.include_router(runs_router)
    app.include_router(schedules_router)
    app.include_router(supervisor_runs_router)
    return app


__all__ = ["create_app"]
