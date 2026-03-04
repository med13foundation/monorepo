"""
Kernel domain repository interfaces.

These define the abstract contracts for kernel data access,
replacing the 7 entity-specific repository interfaces.
"""

from .concept_repository import ConceptRepository
from .dictionary_repository import DictionaryRepository
from .entity_repository import KernelEntityRepository
from .observation_repository import KernelObservationRepository
from .provenance_repository import ProvenanceRepository
from .relation_claim_repository import KernelRelationClaimRepository
from .relation_repository import KernelRelationRepository

__all__ = [
    "ConceptRepository",
    "DictionaryRepository",
    "KernelEntityRepository",
    "KernelObservationRepository",
    "KernelRelationClaimRepository",
    "KernelRelationRepository",
    "ProvenanceRepository",
]
