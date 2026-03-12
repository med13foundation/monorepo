"""
Kernel domain repository interfaces.

These define the abstract contracts for kernel data access,
replacing the 7 entity-specific repository interfaces.
"""

from .claim_evidence_repository import KernelClaimEvidenceRepository
from .claim_participant_repository import KernelClaimParticipantRepository
from .claim_relation_repository import KernelClaimRelationRepository
from .concept_repository import ConceptRepository
from .dictionary_repository import DictionaryRepository
from .entity_embedding_repository import EntityEmbeddingRepository
from .entity_repository import KernelEntityRepository
from .observation_repository import KernelObservationRepository
from .provenance_repository import ProvenanceRepository
from .relation_claim_repository import KernelRelationClaimRepository
from .relation_projection_source_repository import (
    KernelRelationProjectionSourceRepository,
)
from .relation_repository import KernelRelationRepository

__all__ = [
    "ConceptRepository",
    "DictionaryRepository",
    "EntityEmbeddingRepository",
    "KernelClaimEvidenceRepository",
    "KernelClaimParticipantRepository",
    "KernelClaimRelationRepository",
    "KernelEntityRepository",
    "KernelObservationRepository",
    "KernelRelationClaimRepository",
    "KernelRelationProjectionSourceRepository",
    "KernelRelationRepository",
    "ProvenanceRepository",
]
