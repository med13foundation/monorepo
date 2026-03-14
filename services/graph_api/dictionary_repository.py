"""Service-facing compatibility re-export for graph dictionary persistence."""

from __future__ import annotations

from src.infrastructure.graph_governance.dictionary_repository import (
    GraphDictionaryRepository,
)

__all__ = ["GraphDictionaryRepository"]
