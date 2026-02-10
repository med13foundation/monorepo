import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.background import run_ingestion_scheduler_loop, run_session_cleanup_loop
from src.database.seed import (
    ensure_default_research_space_seeded,
    ensure_source_catalog_seeded,
    ensure_system_status_initialized,
)
from src.database.session import get_session
from src.infrastructure.api.exception_handlers import register_exception_handlers
from src.infrastructure.dependency_injection.container import container
from src.infrastructure.dependency_injection.dependencies import (
    initialize_legacy_session,
)
from src.infrastructure.security.cors import get_allowed_origins
from src.middleware import (
    AuditLoggingMiddleware,
    AuthMiddleware,
    EndpointRateLimitMiddleware,
    JWTAuthMiddleware,
    MaintenanceModeMiddleware,
    RequestContextMiddleware,
)
from src.routes import (
    admin_router,
    auth_router,
    curation_router,
    dashboard_router,
    data_discovery_router,
    evidence_router,
    export_router,
    extractions_router,
    genes_router,
    health_router,
    phenotypes_router,
    research_space_discovery_router,
    research_spaces_router,
    resources_router,
    root_router,
    search_router,
    users_router,
    variants_router,
)


def _skip_startup_tasks() -> bool:
    return os.getenv("MED13_SKIP_STARTUP_TASKS") == "1"


def _scheduler_disabled() -> bool:
    return os.getenv("MED13_DISABLE_INGESTION_SCHEDULER") == "1"


INGESTION_SCHEDULER_INTERVAL_SECONDS = int(
    os.getenv("MED13_INGESTION_SCHEDULER_INTERVAL_SECONDS", "300"),
)

SESSION_CLEANUP_INTERVAL_SECONDS = int(
    os.getenv("MED13_SESSION_CLEANUP_INTERVAL_SECONDS", "3600"),
)  # Default: 1 hour


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan context manager."""
    legacy_session = None
    scheduler_task: asyncio.Task[None] | None = None
    session_cleanup_task: asyncio.Task[None] | None = None
    try:
        if not _skip_startup_tasks():
            legacy_session = next(get_session())
            initialize_legacy_session(legacy_session)
            ensure_source_catalog_seeded(legacy_session)
            ensure_default_research_space_seeded(legacy_session)
            ensure_system_status_initialized(legacy_session)
            legacy_session.commit()
            if not _scheduler_disabled():
                scheduler_task = asyncio.create_task(
                    run_ingestion_scheduler_loop(INGESTION_SCHEDULER_INTERVAL_SECONDS),
                    name="ingestion-scheduler-loop",
                )
            # Start session cleanup task
            session_cleanup_task = asyncio.create_task(
                run_session_cleanup_loop(SESSION_CLEANUP_INTERVAL_SECONDS),
                name="session-cleanup-loop",
            )
        yield
    except Exception:
        if legacy_session is not None:
            legacy_session.rollback()
        raise
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task
        if session_cleanup_task is not None:
            session_cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await session_cleanup_task
        if legacy_session is not None:
            legacy_session.close()
        await container.engine.dispose()


def create_app() -> FastAPI:
    """Instantiate the FastAPI application with middleware and routes."""
    app = FastAPI(
        title="MED13 Resource Library",
        version="0.1.0",
        description="Curated resource library for MED13 variants, "
        "phenotypes, and evidence.",
        contact={
            "name": "MED13 Foundation",
            "url": "https://med13foundation.org",
        },
        license_info={
            "name": "CC-BY 4.0",
            "url": "https://creativecommons.org/licenses/by/4.0/",
        },
        lifespan=lifespan,
    )

    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_allowed_origins(),
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["*"],
        allow_credentials=True,
        expose_headers=["*"],
    )

    # Attach request IDs + audit context metadata
    app.add_middleware(RequestContextMiddleware)

    # Add legacy API key authentication middleware (runs first)
    app.add_middleware(AuthMiddleware)

    # Add JWT authentication middleware
    app.add_middleware(JWTAuthMiddleware)

    # Log read access for audit trails
    app.add_middleware(AuditLoggingMiddleware)

    # Add rate limiting middleware
    app.add_middleware(EndpointRateLimitMiddleware)
    app.add_middleware(MaintenanceModeMiddleware)

    app.include_router(health_router)
    app.include_router(root_router)
    app.include_router(resources_router)
    app.include_router(genes_router)
    app.include_router(variants_router)
    app.include_router(phenotypes_router)
    app.include_router(evidence_router)
    app.include_router(extractions_router)
    app.include_router(search_router)
    app.include_router(export_router)
    app.include_router(dashboard_router)
    app.include_router(admin_router)
    app.include_router(curation_router)
    app.include_router(research_spaces_router)
    app.include_router(research_space_discovery_router)
    app.include_router(data_discovery_router)

    # Authentication routes
    app.include_router(auth_router)
    app.include_router(users_router)

    return app


app = create_app()
