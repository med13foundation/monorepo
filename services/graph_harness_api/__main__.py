"""Run the standalone harness API service."""

from __future__ import annotations

import uvicorn

from .config import get_settings


def main() -> None:
    """Launch the harness API service with local runtime settings."""
    settings = get_settings()
    uvicorn.run(
        "services.graph_harness_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    main()
