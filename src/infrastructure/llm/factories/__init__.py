"""
Agent factories for creating Flujo agents.

Factories centralize agent creation to enable:
- Consistent configuration across agents
- Easy model swapping
- Centralized retry/timeout policies
- Testable agent creation
"""

from src.infrastructure.llm.factories.base_factory import (
    BaseAgentFactory,
    FlujoAgent,
)
from src.infrastructure.llm.factories.content_enrichment_agent_factory import (
    ContentEnrichmentAgentFactory,
    create_content_enrichment_agent,
)
from src.infrastructure.llm.factories.entity_recognition_agent_factory import (
    EntityRecognitionAgentFactory,
    create_clinvar_entity_recognition_agent,
    create_entity_recognition_agent_for_source,
)
from src.infrastructure.llm.factories.extraction_agent_factory import (
    ExtractionAgentFactory,
    create_clinvar_extraction_agent,
    create_extraction_agent_for_source,
)
from src.infrastructure.llm.factories.graph_connection_agent_factory import (
    GraphConnectionAgentFactory,
    create_clinvar_graph_connection_agent,
    create_graph_connection_agent_for_source,
)
from src.infrastructure.llm.factories.graph_search_agent_factory import (
    GraphSearchAgentFactory,
    create_graph_search_agent,
)
from src.infrastructure.llm.factories.query_agent_factory import (
    QueryAgentFactory,
    create_clinvar_query_agent,
    create_pubmed_query_agent,
)

__all__ = [
    "BaseAgentFactory",
    "create_content_enrichment_agent",
    "create_entity_recognition_agent_for_source",
    "create_clinvar_entity_recognition_agent",
    "create_extraction_agent_for_source",
    "create_clinvar_extraction_agent",
    "create_graph_connection_agent_for_source",
    "create_clinvar_graph_connection_agent",
    "create_graph_search_agent",
    "FlujoAgent",
    "create_pubmed_query_agent",
    "create_clinvar_query_agent",
    "EntityRecognitionAgentFactory",
    "ContentEnrichmentAgentFactory",
    "ExtractionAgentFactory",
    "GraphConnectionAgentFactory",
    "GraphSearchAgentFactory",
    "QueryAgentFactory",
]
