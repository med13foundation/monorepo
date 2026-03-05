"""Domain-wide service port interfaces."""

from src.domain.ports.concept_decision_harness_port import ConceptDecisionHarnessPort
from src.domain.ports.concept_port import ConceptPort
from src.domain.ports.dictionary_port import DictionaryPort
from src.domain.ports.dictionary_search_harness_port import DictionarySearchHarnessPort
from src.domain.ports.evidence_sentence_harness_port import EvidenceSentenceHarnessPort
from src.domain.ports.graph_query_port import GraphQueryPort
from src.domain.ports.research_query_port import ResearchQueryPort
from src.domain.ports.text_embedding_port import TextEmbeddingPort

__all__ = [
    "ConceptDecisionHarnessPort",
    "ConceptPort",
    "DictionaryPort",
    "DictionarySearchHarnessPort",
    "EvidenceSentenceHarnessPort",
    "GraphQueryPort",
    "ResearchQueryPort",
    "TextEmbeddingPort",
]
