"""Facade exports for claim-backed kernel route dependencies."""

from __future__ import annotations

from src.routes.research_spaces import (
    _kernel_claim_projection_dependencies as claim_projection_dependencies,
)
from src.routes.research_spaces import (
    _kernel_reasoning_hypothesis_dependencies as reasoning_hypothesis_dependencies,
)

get_hypothesis_generation_service = (
    reasoning_hypothesis_dependencies.get_hypothesis_generation_service
)
get_kernel_claim_evidence_service = (
    claim_projection_dependencies.get_kernel_claim_evidence_service
)
get_kernel_claim_participant_backfill_service = (
    reasoning_hypothesis_dependencies.get_kernel_claim_participant_backfill_service
)
get_kernel_claim_participant_service = (
    claim_projection_dependencies.get_kernel_claim_participant_service
)
get_kernel_claim_projection_readiness_service = (
    reasoning_hypothesis_dependencies.get_kernel_claim_projection_readiness_service
)
get_kernel_claim_relation_service = (
    claim_projection_dependencies.get_kernel_claim_relation_service
)
get_kernel_graph_view_service = (
    reasoning_hypothesis_dependencies.get_kernel_graph_view_service
)
get_kernel_reasoning_path_service = (
    reasoning_hypothesis_dependencies.get_kernel_reasoning_path_service
)
get_kernel_relation_claim_service = (
    claim_projection_dependencies.get_kernel_relation_claim_service
)
get_kernel_relation_projection_invariant_service = (
    claim_projection_dependencies.get_kernel_relation_projection_invariant_service
)
get_kernel_relation_projection_materialization_service = (
    claim_projection_dependencies.get_kernel_relation_projection_materialization_service
)
get_kernel_relation_projection_source_service = (
    claim_projection_dependencies.get_kernel_relation_projection_source_service
)

__all__ = [
    "get_hypothesis_generation_service",
    "get_kernel_claim_evidence_service",
    "get_kernel_claim_participant_backfill_service",
    "get_kernel_claim_participant_service",
    "get_kernel_claim_projection_readiness_service",
    "get_kernel_claim_relation_service",
    "get_kernel_graph_view_service",
    "get_kernel_reasoning_path_service",
    "get_kernel_relation_claim_service",
    "get_kernel_relation_projection_invariant_service",
    "get_kernel_relation_projection_materialization_service",
    "get_kernel_relation_projection_source_service",
]
