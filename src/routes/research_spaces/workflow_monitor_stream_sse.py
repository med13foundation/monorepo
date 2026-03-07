"""SSE response helpers for workflow monitor stream routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from importlib import import_module

from starlette.responses import Response, StreamingResponse


def resolve_event_source_response_factory() -> type[Response] | None:
    """Resolve native EventSourceResponse when FastAPI SSE support is installed."""
    try:
        module = import_module("fastapi.sse")
    except ImportError:  # pragma: no cover - depends on installed FastAPI extras
        return None
    response_factory = getattr(module, "EventSourceResponse", None)
    if isinstance(response_factory, type) and issubclass(response_factory, Response):
        return response_factory
    return None


def build_event_source_response(content: AsyncIterator[str]) -> Response:
    """Construct an SSE response without double-encoding preformatted events."""
    response_factory = resolve_event_source_response_factory()
    if response_factory is not None:
        return response_factory(content)
    return StreamingResponse(content, media_type="text/event-stream")


__all__ = ["build_event_source_response"]
