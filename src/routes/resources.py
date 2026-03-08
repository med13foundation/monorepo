from collections.abc import Sequence

from fastapi import APIRouter

from src.application.services.resource_service import list_resources
from src.models.resource_model import Resource

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("/", summary="List curated resources")
def get_resources() -> Sequence[Resource]:
    """Return curated resources using the service layer."""
    return list_resources()
