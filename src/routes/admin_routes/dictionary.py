"""
Admin dictionary endpoints for the kernel (Layer 1).

These endpoints allow platform administrators to browse and curate the
master dictionary: variable definitions, transforms, resolution policies,
entity types, relation types, and relation constraints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.routes.admin_routes.dependencies import get_admin_db_session

from .dictionary_entity_types_routes import router as dictionary_entity_types_router
from .dictionary_misc_routes import router as dictionary_misc_router
from .dictionary_relation_synonyms_routes import (
    router as dictionary_relation_synonyms_router,
)
from .dictionary_relation_types_routes import router as dictionary_relation_types_router
from .dictionary_route_common import get_dictionary_service, require_admin_user
from .dictionary_value_sets_routes import router as dictionary_value_sets_router
from .dictionary_variables_routes import router as dictionary_variables_router

router = APIRouter(
    dependencies=[Depends(require_admin_user)],
    tags=["dictionary"],
)
router.include_router(dictionary_variables_router)
router.include_router(dictionary_entity_types_router)
router.include_router(dictionary_relation_types_router)
router.include_router(dictionary_relation_synonyms_router)
router.include_router(dictionary_value_sets_router)
router.include_router(dictionary_misc_router)

__all__ = [
    "get_admin_db_session",
    "get_dictionary_service",
    "require_admin_user",
    "router",
]
