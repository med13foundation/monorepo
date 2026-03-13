"""Kernel SQLAlchemy repository implementations."""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "SqlAlchemyConceptRepository": (
        ".kernel_concept_repository",
        "SqlAlchemyConceptRepository",
    ),
    "SqlAlchemyDictionaryRepository": (
        ".kernel_dictionary_repository",
        "SqlAlchemyDictionaryRepository",
    ),
    "SqlAlchemyEntityEmbeddingRepository": (
        ".kernel_entity_embedding_repository",
        "SqlAlchemyEntityEmbeddingRepository",
    ),
    "SqlAlchemyGraphQueryRepository": (
        ".graph_query_repository",
        "SqlAlchemyGraphQueryRepository",
    ),
    "SqlAlchemyKernelClaimEvidenceRepository": (
        ".kernel_claim_evidence_repository",
        "SqlAlchemyKernelClaimEvidenceRepository",
    ),
    "SqlAlchemyKernelClaimParticipantRepository": (
        ".kernel_claim_participant_repository",
        "SqlAlchemyKernelClaimParticipantRepository",
    ),
    "SqlAlchemyKernelClaimRelationRepository": (
        ".kernel_claim_relation_repository",
        "SqlAlchemyKernelClaimRelationRepository",
    ),
    "SqlAlchemyKernelEntityRepository": (
        ".kernel_entity_repository",
        "SqlAlchemyKernelEntityRepository",
    ),
    "SqlAlchemyKernelObservationRepository": (
        ".kernel_observation_repository",
        "SqlAlchemyKernelObservationRepository",
    ),
    "SqlAlchemyKernelReasoningPathRepository": (
        ".kernel_reasoning_path_repository",
        "SqlAlchemyKernelReasoningPathRepository",
    ),
    "SqlAlchemyKernelRelationClaimRepository": (
        ".kernel_relation_claim_repository",
        "SqlAlchemyKernelRelationClaimRepository",
    ),
    "SqlAlchemyKernelRelationProjectionSourceRepository": (
        ".kernel_relation_projection_source_repository",
        "SqlAlchemyKernelRelationProjectionSourceRepository",
    ),
    "SqlAlchemyKernelRelationRepository": (
        ".kernel_relation_repository",
        "SqlAlchemyKernelRelationRepository",
    ),
    "SqlAlchemyKernelSourceDocumentReferenceRepository": (
        ".kernel_source_document_reference_repository",
        "SqlAlchemyKernelSourceDocumentReferenceRepository",
    ),
    "SqlAlchemyKernelSpaceAccessRepository": (
        ".kernel_space_access_repository",
        "SqlAlchemyKernelSpaceAccessRepository",
    ),
    "SqlAlchemyKernelSpaceMembershipRepository": (
        ".kernel_space_membership_repository",
        "SqlAlchemyKernelSpaceMembershipRepository",
    ),
    "SqlAlchemyKernelSpaceRegistryRepository": (
        ".kernel_space_registry_repository",
        "SqlAlchemyKernelSpaceRegistryRepository",
    ),
    "SqlAlchemyKernelSpaceSettingsRepository": (
        ".kernel_space_settings_repository",
        "SqlAlchemyKernelSpaceSettingsRepository",
    ),
    "SqlAlchemyProvenanceRepository": (
        ".kernel_provenance_repository",
        "SqlAlchemyProvenanceRepository",
    ),
}

__all__ = tuple(sorted(_EXPORTS))


def __getattr__(name: str) -> object:
    if name not in _EXPORTS:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    module_name, attribute_name = _EXPORTS[name]
    module = import_module(module_name, __name__)
    return getattr(module, attribute_name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
