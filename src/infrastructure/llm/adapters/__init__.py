"""
Port adapter implementations for AI agents.

Adapters implement the domain port interfaces using Flujo
as the underlying agent execution framework.

Available Adapters:
    FlujoEntityRecognitionAdapter: Implements EntityRecognitionPort
    FlujoExtractionAdapter: Implements ExtractionAgentPort
    FlujoQueryAgentAdapter: Implements QueryAgentPort for query generation
"""

from src.infrastructure.llm.adapters.content_enrichment_agent_adapter import (
    FlujoContentEnrichmentAdapter,
)
from src.infrastructure.llm.adapters.entity_recognition_agent_adapter import (
    FlujoEntityRecognitionAdapter,
)
from src.infrastructure.llm.adapters.extraction_agent_adapter import (
    FlujoExtractionAdapter,
)
from src.infrastructure.llm.adapters.graph_connection_agent_adapter import (
    FlujoGraphConnectionAdapter,
)
from src.infrastructure.llm.adapters.graph_search_agent_adapter import (
    FlujoGraphSearchAdapter,
)
from src.infrastructure.llm.adapters.query_agent_adapter import FlujoQueryAgentAdapter

__all__ = [
    "FlujoContentEnrichmentAdapter",
    "FlujoEntityRecognitionAdapter",
    "FlujoExtractionAdapter",
    "FlujoGraphConnectionAdapter",
    "FlujoGraphSearchAdapter",
    "FlujoQueryAgentAdapter",
]
