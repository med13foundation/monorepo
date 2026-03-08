from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/", summary="Health check endpoint")
def health_check() -> dict[str, str]:
    """Return a simple health check response."""
    return {"status": "ok"}
