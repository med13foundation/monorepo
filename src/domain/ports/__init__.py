"""Domain-wide service port interfaces."""

from src.domain.ports.dictionary_port import DictionaryPort
from src.domain.ports.graph_query_port import GraphQueryPort
from src.domain.ports.research_query_port import ResearchQueryPort
from src.domain.ports.text_embedding_port import TextEmbeddingPort

__all__ = [
    "DictionaryPort",
    "GraphQueryPort",
    "ResearchQueryPort",
    "TextEmbeddingPort",
]
