"""Root info route for the MED13 Resource Library API."""

from fastapi import APIRouter

from src.type_definitions.common import JSONObject

router = APIRouter(tags=["info"])


@router.get("/", summary="Welcome to MED13 Resource Library", tags=["info"])
async def root() -> JSONObject:
    """Welcome endpoint with API information."""
    return {
        "message": "Welcome to the MED13 Resource Library API",
        "description": "Curated biomedical resource library built on a "
        "metadata-driven kernel (dictionary + entities + observations + relations).",
        "version": "0.1.0",
        "documentation": "/docs",
        "health_check": "/health",
        "resources": "/resources",
        "dashboard": "/api/dashboard",
        "research_spaces": "/research-spaces",
        "kernel": {
            "entities": "/research-spaces/{space_id}/entities",
            "observations": "/research-spaces/{space_id}/observations",
            "relations": "/research-spaces/{space_id}/relations",
            "provenance": "/research-spaces/{space_id}/provenance",
            "ingest": "/research-spaces/{space_id}/ingest",
            "graph_export": "/research-spaces/{space_id}/graph/export",
            "graph_search": "/research-spaces/{space_id}/graph/search",
            "graph_connections_discover": (
                "/research-spaces/{space_id}/graph/connections/discover"
            ),
            "entity_graph_connections": (
                "/research-spaces/{space_id}/entities/{entity_id}/connections"
            ),
            "content_enrichment_run": (
                "/research-spaces/{space_id}/documents/enrichment/run"
            ),
            "knowledge_extraction_run": (
                "/research-spaces/{space_id}/documents/extraction/run"
            ),
        },
        "admin": "/admin",
        "authentication": {
            "type": "JWT Bearer Token",
            "header": "Authorization",
            "format": "Bearer {token}",
            "login_endpoint": "/auth/login",
            "description": "Use JWT tokens obtained from /auth/login for API authentication",
        },
        "rate_limiting": {
            "description": "Rate limiting applied based on client IP",
            "headers": [
                "X-RateLimit-Remaining",
                "X-RateLimit-Limit",
                "X-RateLimit-Reset",
            ],
        },
        "contact": "https://med13foundation.org",
        "license": "CC-BY 4.0",
    }


__all__ = ["router"]
