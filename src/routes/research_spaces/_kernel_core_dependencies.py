"""Facade exports for core kernel route dependencies."""

from __future__ import annotations

from src.routes.research_spaces import (
    _kernel_dictionary_entity_dependencies as dictionary_entity_dependencies,
)
from src.routes.research_spaces import (
    _kernel_graph_operation_dependencies as graph_operation_dependencies,
)

build_entity_repository = dictionary_entity_dependencies.build_entity_repository
get_concept_service = dictionary_entity_dependencies.get_concept_service
get_dictionary_service = dictionary_entity_dependencies.get_dictionary_service
get_kernel_entity_service = dictionary_entity_dependencies.get_kernel_entity_service
get_kernel_entity_similarity_service = (
    dictionary_entity_dependencies.get_kernel_entity_similarity_service
)
get_ingestion_pipeline = graph_operation_dependencies.get_ingestion_pipeline
get_kernel_observation_service = (
    graph_operation_dependencies.get_kernel_observation_service
)
get_kernel_relation_service = graph_operation_dependencies.get_kernel_relation_service
get_kernel_relation_suggestion_service = (
    graph_operation_dependencies.get_kernel_relation_suggestion_service
)
get_provenance_service = graph_operation_dependencies.get_provenance_service

__all__ = [
    "build_entity_repository",
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
