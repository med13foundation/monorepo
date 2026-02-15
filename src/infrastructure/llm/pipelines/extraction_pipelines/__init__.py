"""Extraction pipeline factories."""

from src.infrastructure.llm.pipelines.extraction_pipelines.clinvar_pipeline import (
    create_clinvar_extraction_pipeline,
)

__all__ = ["create_clinvar_extraction_pipeline"]
