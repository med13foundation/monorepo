"""Service-facing compatibility re-export for graph concept persistence."""

from __future__ import annotations

from src.infrastructure.graph_governance.concept_repository import (
    GraphConceptRepository,
)

__all__ = ["GraphConceptRepository"]
