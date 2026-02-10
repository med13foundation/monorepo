"""API route definitions for the MED13 Resource Library."""

from . import (
    admin,
    auth,
    curation,
    dashboard,
    data_discovery,
    evidence,
    export,
    extractions,
    genes,
    health,
    phenotypes,
    research_space_discovery,
    research_spaces,
    resources,
    root,
    search,
    users,
    variants,
)

admin_router = admin.router
auth_router = auth.auth_router
curation_router = curation.router
dashboard_router = dashboard.router
data_discovery_router = data_discovery.router
evidence_router = evidence.router
extractions_router = extractions.router
export_router = export.router
genes_router = genes.router
health_router = health.router
phenotypes_router = phenotypes.router
research_space_discovery_router = research_space_discovery.router
research_spaces_router = research_spaces.research_spaces_router
resources_router = resources.router
root_router = root.router
search_router = search.router
users_router = users.users_router
variants_router = variants.router

__all__ = [
    "admin_router",
    "auth_router",
    "curation_router",
    "dashboard_router",
    "data_discovery_router",
    "evidence_router",
    "extractions_router",
    "export_router",
    "genes_router",
    "health_router",
    "phenotypes_router",
    "research_space_discovery_router",
    "research_spaces_router",
    "resources_router",
    "root_router",
    "search_router",
    "users_router",
    "variants_router",
]
