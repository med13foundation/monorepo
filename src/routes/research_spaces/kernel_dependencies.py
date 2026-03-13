"""Public kernel dependency exports for research-space routes."""

from __future__ import annotations

from src.routes.research_spaces import _kernel_core_dependencies as core_dependencies

get_concept_service = core_dependencies.get_concept_service
get_dictionary_service = core_dependencies.get_dictionary_service
get_ingestion_pipeline = core_dependencies.get_ingestion_pipeline
get_kernel_entity_service = core_dependencies.get_kernel_entity_service
get_kernel_entity_similarity_service = (
    core_dependencies.get_kernel_entity_similarity_service
)
get_kernel_observation_service = core_dependencies.get_kernel_observation_service
get_kernel_relation_service = core_dependencies.get_kernel_relation_service
get_kernel_relation_suggestion_service = (
    core_dependencies.get_kernel_relation_suggestion_service
)
get_provenance_service = core_dependencies.get_provenance_service

__all__ = [
    "get_concept_service",
    "get_dictionary_service",
    "get_ingestion_pipeline",
    "get_kernel_entity_service",
    "get_kernel_entity_similarity_service",
    "get_kernel_observation_service",
    "get_kernel_relation_service",
    "get_kernel_relation_suggestion_service",
    "get_provenance_service",
]
