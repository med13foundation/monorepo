"""
Kernel domain entities (Layer 0/1 core graph + dictionary concepts).

These are domain-level representations of the kernel tables (dictionary, entities,
observations, relations, provenance). They intentionally do NOT depend on
SQLAlchemy models so that the domain layer remains infrastructure-agnostic.
"""

from .claim_evidence import (
    ClaimEvidenceSentenceConfidence,
    ClaimEvidenceSentenceSource,
    KernelClaimEvidence,
)
from .concepts import (
    ConceptAlias,
    ConceptDecision,
    ConceptDecisionProposal,
    ConceptHarnessCheck,
    ConceptHarnessResult,
    ConceptHarnessVerdict,
    ConceptLink,
    ConceptMember,
    ConceptPolicy,
    ConceptSet,
)
from .dictionary import (
    DictionaryChangelog,
    DictionaryDataType,
    DictionaryDomainContext,
    DictionaryEntityType,
    DictionaryRelationSynonym,
    DictionaryRelationType,
    DictionarySearchResult,
    DictionarySensitivityLevel,
    EntityResolutionPolicy,
    RelationConstraint,
    TransformRegistry,
    TransformVerificationResult,
    ValueSet,
    ValueSetItem,
    VariableDefinition,
    VariableSynonym,
)
from .embeddings import (
    KernelEntityEmbedding,
    KernelEntitySimilarityCandidate,
    KernelEntitySimilarityResult,
    KernelEntitySimilarityScoreBreakdown,
    KernelRelationSuggestionConstraintCheck,
    KernelRelationSuggestionResult,
    KernelRelationSuggestionScoreBreakdown,
)
from .entities import KernelEntity, KernelEntityIdentifier
from .observations import KernelObservation
from .provenance import KernelProvenanceRecord
from .relation_claims import (
    KernelRelationClaim,
    KernelRelationConflictSummary,
    RelationClaimPersistability,
    RelationClaimPolarity,
    RelationClaimStatus,
    RelationClaimValidationState,
)
from .relations import (
    EvidenceSentenceConfidence,
    EvidenceSentenceGenerationRequest,
    EvidenceSentenceGenerationResult,
    EvidenceSentenceHarnessOutcome,
    EvidenceSentenceSource,
    KernelRelation,
    KernelRelationEvidence,
)

__all__ = [
    "DictionaryChangelog",
    "DictionaryDataType",
    "DictionaryDomainContext",
    "DictionaryEntityType",
    "DictionaryRelationSynonym",
    "DictionaryRelationType",
    "DictionarySearchResult",
    "DictionarySensitivityLevel",
    "EntityResolutionPolicy",
    "KernelEntityEmbedding",
    "KernelEntity",
    "KernelEntityIdentifier",
    "KernelEntitySimilarityCandidate",
    "KernelEntitySimilarityResult",
    "KernelEntitySimilarityScoreBreakdown",
    "KernelObservation",
    "KernelProvenanceRecord",
    "KernelRelationClaim",
    "KernelRelationConflictSummary",
    "KernelClaimEvidence",
    "ClaimEvidenceSentenceSource",
    "ClaimEvidenceSentenceConfidence",
    "RelationClaimPolarity",
    "RelationClaimPersistability",
    "RelationClaimStatus",
    "RelationClaimValidationState",
    "KernelRelation",
    "KernelRelationEvidence",
    "EvidenceSentenceSource",
    "EvidenceSentenceConfidence",
    "EvidenceSentenceHarnessOutcome",
    "EvidenceSentenceGenerationRequest",
    "EvidenceSentenceGenerationResult",
    "RelationConstraint",
    "TransformRegistry",
    "TransformVerificationResult",
    "ValueSet",
    "ValueSetItem",
    "VariableDefinition",
    "VariableSynonym",
    "KernelRelationSuggestionConstraintCheck",
    "KernelRelationSuggestionResult",
    "KernelRelationSuggestionScoreBreakdown",
    "ConceptAlias",
    "ConceptDecision",
    "ConceptDecisionProposal",
    "ConceptHarnessCheck",
    "ConceptHarnessResult",
    "ConceptHarnessVerdict",
    "ConceptLink",
    "ConceptMember",
    "ConceptPolicy",
    "ConceptSet",
]
