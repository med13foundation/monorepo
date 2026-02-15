"""Content-enrichment pipeline factories."""

from src.infrastructure.llm.pipelines.content_enrichment_pipelines.default_pipeline import (
    create_content_enrichment_pipeline,
)

__all__ = ["create_content_enrichment_pipeline"]
