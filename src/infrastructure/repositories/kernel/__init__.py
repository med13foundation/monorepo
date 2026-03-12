"""
Kernel SQLAlchemy repository implementations.

Concrete implementations of the kernel domain repository interfaces
using SQLAlchemy ORM against the PostgreSQL database.
"""

from .graph_query_repository import SqlAlchemyGraphQueryRepository
from .kernel_claim_evidence_repository import SqlAlchemyKernelClaimEvidenceRepository
from .kernel_claim_participant_repository import (
    SqlAlchemyKernelClaimParticipantRepository,
)
from .kernel_claim_relation_repository import SqlAlchemyKernelClaimRelationRepository
from .kernel_concept_repository import SqlAlchemyConceptRepository
from .kernel_dictionary_repository import SqlAlchemyDictionaryRepository
from .kernel_entity_embedding_repository import SqlAlchemyEntityEmbeddingRepository
from .kernel_entity_repository import SqlAlchemyKernelEntityRepository
from .kernel_observation_repository import SqlAlchemyKernelObservationRepository
from .kernel_provenance_repository import SqlAlchemyProvenanceRepository
from .kernel_reasoning_path_repository import SqlAlchemyKernelReasoningPathRepository
from .kernel_relation_claim_repository import SqlAlchemyKernelRelationClaimRepository
from .kernel_relation_projection_source_repository import (
    SqlAlchemyKernelRelationProjectionSourceRepository,
)
from .kernel_relation_repository import SqlAlchemyKernelRelationRepository

__all__ = [
    "SqlAlchemyConceptRepository",
    "SqlAlchemyDictionaryRepository",
    "SqlAlchemyEntityEmbeddingRepository",
    "SqlAlchemyGraphQueryRepository",
    "SqlAlchemyKernelClaimEvidenceRepository",
    "SqlAlchemyKernelClaimParticipantRepository",
    "SqlAlchemyKernelClaimRelationRepository",
    "SqlAlchemyKernelEntityRepository",
    "SqlAlchemyKernelObservationRepository",
    "SqlAlchemyKernelRelationClaimRepository",
    "SqlAlchemyKernelRelationProjectionSourceRepository",
    "SqlAlchemyKernelRelationRepository",
    "SqlAlchemyKernelReasoningPathRepository",
    "SqlAlchemyProvenanceRepository",
]
