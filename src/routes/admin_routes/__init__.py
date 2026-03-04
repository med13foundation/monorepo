"""
Admin API router aggregation.
"""

from __future__ import annotations

from fastapi import APIRouter

from .ai_models import router as ai_models_router
from .audit import router as audit_router
from .catalog import router as catalog_router
from .concepts import router as concepts_router
from .data_sources import router as data_sources_router
from .dictionary import router as dictionary_router
from .dictionary_transforms import router as dictionary_transforms_router
from .stats import stats_router
from .storage import router as storage_router
from .system_status import router as system_router
from .templates import router as templates_router

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    responses={
        401: {"description": "Unauthorized - Invalid or missing authentication"},
        403: {"description": "Forbidden - Insufficient permissions"},
        500: {"description": "Internal Server Error"},
    },
)

router.include_router(ai_models_router)
router.include_router(audit_router)
router.include_router(templates_router)
router.include_router(data_sources_router)
router.include_router(catalog_router)
router.include_router(concepts_router)
router.include_router(dictionary_router)
router.include_router(dictionary_transforms_router)
router.include_router(stats_router)
router.include_router(storage_router)
router.include_router(system_router)

__all__ = ["router"]
