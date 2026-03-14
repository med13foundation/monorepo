"""Biomedical graph domain-pack wiring."""

from __future__ import annotations

from src.graph.core.domain_pack import GraphDomainPack
from src.graph.core.runtime_identity import GraphRuntimeIdentity
from src.graph.domain_biomedical.dictionary_loading_extension import (
    get_biomedical_dictionary_loading_extension,
)
from src.graph.domain_biomedical.domain_context import (
    BIOMEDICAL_GRAPH_DOMAIN_CONTEXT_POLICY,
)
from src.graph.domain_biomedical.entity_recognition_bootstrap import (
    BIOMEDICAL_ENTITY_RECOGNITION_BOOTSTRAP,
)
from src.graph.domain_biomedical.entity_recognition_fallback import (
    BIOMEDICAL_ENTITY_RECOGNITION_HEURISTIC_FIELD_MAP,
)
from src.graph.domain_biomedical.entity_recognition_payload import (
    BIOMEDICAL_ENTITY_RECOGNITION_PAYLOAD_CONFIG,
)
from src.graph.domain_biomedical.entity_recognition_prompt import (
    BIOMEDICAL_ENTITY_RECOGNITION_PROMPT_CONFIG,
)
from src.graph.domain_biomedical.extraction_fallback import (
    BIOMEDICAL_EXTRACTION_HEURISTIC_CONFIG,
)
from src.graph.domain_biomedical.extraction_payload import (
    BIOMEDICAL_EXTRACTION_PAYLOAD_CONFIG,
)
from src.graph.domain_biomedical.extraction_prompt import (
    BIOMEDICAL_EXTRACTION_PROMPT_CONFIG,
)
from src.graph.domain_biomedical.feature_flags import (
    BIOMEDICAL_GRAPH_FEATURE_FLAGS,
)
from src.graph.domain_biomedical.graph_connection_prompt import (
    BIOMEDICAL_GRAPH_CONNECTION_PROMPT_CONFIG,
)
from src.graph.domain_biomedical.relation_autopromotion import (
    BIOMEDICAL_RELATION_AUTOPROMOTION_DEFAULTS,
)
from src.graph.domain_biomedical.relation_suggestion_extension import (
    get_biomedical_relation_suggestion_extension,
)
from src.graph.domain_biomedical.search_extension import (
    get_biomedical_graph_search_extension,
)
from src.graph.domain_biomedical.view_config import (
    get_biomedical_graph_view_extension,
)

_BIOMEDICAL_GRAPH_DOMAIN_PACK = GraphDomainPack(
    name="biomedical",
    runtime_identity=GraphRuntimeIdentity(
        service_name="Biomedical Graph Service",
        jwt_issuer="graph-biomedical",
    ),
    view_extension=get_biomedical_graph_view_extension(),
    feature_flags=BIOMEDICAL_GRAPH_FEATURE_FLAGS,
    dictionary_loading_extension=get_biomedical_dictionary_loading_extension(),
    domain_context_policy=BIOMEDICAL_GRAPH_DOMAIN_CONTEXT_POLICY,
    entity_recognition_bootstrap=BIOMEDICAL_ENTITY_RECOGNITION_BOOTSTRAP,
    entity_recognition_fallback=BIOMEDICAL_ENTITY_RECOGNITION_HEURISTIC_FIELD_MAP,
    entity_recognition_payload=BIOMEDICAL_ENTITY_RECOGNITION_PAYLOAD_CONFIG,
    entity_recognition_prompt=BIOMEDICAL_ENTITY_RECOGNITION_PROMPT_CONFIG,
    extraction_fallback=BIOMEDICAL_EXTRACTION_HEURISTIC_CONFIG,
    extraction_payload=BIOMEDICAL_EXTRACTION_PAYLOAD_CONFIG,
    extraction_prompt=BIOMEDICAL_EXTRACTION_PROMPT_CONFIG,
    graph_connection_prompt=BIOMEDICAL_GRAPH_CONNECTION_PROMPT_CONFIG,
    search_extension=get_biomedical_graph_search_extension(),
    relation_suggestion_extension=get_biomedical_relation_suggestion_extension(),
    relation_autopromotion_defaults=BIOMEDICAL_RELATION_AUTOPROMOTION_DEFAULTS,
)


def get_biomedical_graph_domain_pack() -> GraphDomainPack:
    """Return the biomedical graph domain pack."""
    return _BIOMEDICAL_GRAPH_DOMAIN_PACK
