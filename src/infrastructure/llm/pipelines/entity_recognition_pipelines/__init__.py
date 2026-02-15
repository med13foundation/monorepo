"""Entity-recognition pipeline factories."""

from src.infrastructure.llm.pipelines.entity_recognition_pipelines.clinvar_pipeline import (
    create_clinvar_entity_recognition_pipeline,
)

__all__ = ["create_clinvar_entity_recognition_pipeline"]
