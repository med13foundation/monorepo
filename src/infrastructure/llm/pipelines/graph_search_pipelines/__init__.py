"""Graph-search pipeline factories."""

from src.infrastructure.llm.pipelines.graph_search_pipelines.default_pipeline import (
    create_graph_search_pipeline,
)

__all__ = ["create_graph_search_pipeline"]
