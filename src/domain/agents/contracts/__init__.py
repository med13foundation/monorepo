"""
Evidence-First Output Schemas for AI Agents.

Flujo agents must not expose internal chain-of-thought. Instead, use
Evidence-First schemas that separate:
- the decision
- the confidence
- the human-readable justification
- and the structured evidence supporting that decision

Design rule: If a decision cannot be supported by structured evidence,
it must not be auto-approved.
"""

from src.domain.agents.contracts.base import (
    AgentDecision,
    BaseAgentContract,
    EvidenceItem,
)
from src.domain.agents.contracts.content_enrichment import ContentEnrichmentContract
from src.domain.agents.contracts.entity_recognition import (
    EntityRecognitionContract,
    RecognizedEntityCandidate,
    RecognizedObservationCandidate,
)
from src.domain.agents.contracts.extraction import (
    ExtractedObservation,
    ExtractedRelation,
    ExtractionContract,
    RejectedFact,
)
from src.domain.agents.contracts.graph_connection import (
    GraphConnectionContract,
    ProposedRelation,
    RejectedCandidate,
)
from src.domain.agents.contracts.graph_search import (
    EvidenceChainItem,
    GraphSearchContract,
    GraphSearchResultEntry,
)
from src.domain.agents.contracts.query_generation import QueryGenerationContract

__all__ = [
    "AgentDecision",
    "BaseAgentContract",
    "ContentEnrichmentContract",
    "EntityRecognitionContract",
    "EvidenceItem",
    "ExtractedObservation",
    "ExtractedRelation",
    "ExtractionContract",
    "GraphConnectionContract",
    "GraphSearchContract",
    "GraphSearchResultEntry",
    "EvidenceChainItem",
    "ProposedRelation",
    "QueryGenerationContract",
    "RejectedCandidate",
    "RejectedFact",
    "RecognizedEntityCandidate",
    "RecognizedObservationCandidate",
]
