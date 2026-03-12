"""Public kernel dependency exports for research-space routes."""

from __future__ import annotations

from src.routes.research_spaces import _kernel_claim_dependencies as claim_dependencies
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

get_hypothesis_generation_service = claim_dependencies.get_hypothesis_generation_service
get_kernel_claim_evidence_service = claim_dependencies.get_kernel_claim_evidence_service
get_kernel_claim_participant_backfill_service = (
    claim_dependencies.get_kernel_claim_participant_backfill_service
)
get_kernel_claim_participant_service = (
    claim_dependencies.get_kernel_claim_participant_service
)
get_kernel_claim_projection_readiness_service = (
    claim_dependencies.get_kernel_claim_projection_readiness_service
)
get_kernel_claim_relation_service = claim_dependencies.get_kernel_claim_relation_service
get_kernel_graph_view_service = claim_dependencies.get_kernel_graph_view_service
get_kernel_reasoning_path_service = claim_dependencies.get_kernel_reasoning_path_service
get_kernel_relation_claim_service = claim_dependencies.get_kernel_relation_claim_service
get_kernel_relation_projection_invariant_service = (
    claim_dependencies.get_kernel_relation_projection_invariant_service
)
get_kernel_relation_projection_materialization_service = (
    claim_dependencies.get_kernel_relation_projection_materialization_service
)
get_kernel_relation_projection_source_service = (
    claim_dependencies.get_kernel_relation_projection_source_service
)

__all__ = [
    "get_concept_service",
    "get_dictionary_service",
    "get_hypothesis_generation_service",
    "get_ingestion_pipeline",
    "get_kernel_claim_evidence_service",
    "get_kernel_claim_participant_backfill_service",
    "get_kernel_claim_participant_service",
    "get_kernel_claim_projection_readiness_service",
    "get_kernel_claim_relation_service",
    "get_kernel_entity_service",
    "get_kernel_entity_similarity_service",
    "get_kernel_graph_view_service",
    "get_kernel_observation_service",
    "get_kernel_reasoning_path_service",
    "get_kernel_relation_claim_service",
    "get_kernel_relation_projection_invariant_service",
    "get_kernel_relation_projection_materialization_service",
    "get_kernel_relation_projection_source_service",
    "get_kernel_relation_service",
    "get_kernel_relation_suggestion_service",
    "get_provenance_service",
]
