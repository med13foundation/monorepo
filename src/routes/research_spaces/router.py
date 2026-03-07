"""
Research Spaces API router for MED13 Resource Library.

Defines the shared FastAPI router and HTTP status constants.
Actual route handlers live in sibling modules to keep files concise.
"""

from fastapi import APIRouter

# HTTP status codes
HTTP_201_CREATED = 201
HTTP_400_BAD_REQUEST = 400
HTTP_403_FORBIDDEN = 403
HTTP_404_NOT_FOUND = 404
HTTP_409_CONFLICT = 409
HTTP_500_INTERNAL_SERVER_ERROR = 500

research_spaces_router = APIRouter(
    prefix="/research-spaces",
    tags=["research-spaces"],
    responses={
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        404: {"description": "Not Found"},
        422: {"description": "Validation Error"},
        500: {"description": "Internal Server Error"},
    },
)

# Import route modules so decorators register against the router.
from . import (  # noqa: E402,F401
    artana_run_routes,
    claim_graph_routes,
    concept_routes,
    content_enrichment_routes,
    curation_routes,
    data_source_routes,
    graph_connection_routes,
    hypothesis_routes,
    kernel_entities_routes,
    kernel_graph_search_routes,
    kernel_ingestion_routes,
    kernel_observations_routes,
    kernel_provenance_routes,
    kernel_relations_routes,
    knowledge_extraction_routes,
    membership_routes,
    ontology_routes,
    pipeline_orchestration_routes,
    space_routes,
    workflow_monitor_routes,
    workflow_monitor_stream_routes,
)

__all__ = ["research_spaces_router"]
