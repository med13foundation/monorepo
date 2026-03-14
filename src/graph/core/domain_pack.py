"""Domain-pack contracts for graph platform wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.graph.core.dictionary_domain_contexts import (
        DictionaryDomainContextDefinition,
    )
    from src.graph.core.dictionary_loading_extension import (
        GraphDictionaryLoadingExtension,
    )
    from src.graph.core.domain_context_policy import GraphDomainContextPolicy
    from src.graph.core.entity_recognition_bootstrap import (
        EntityRecognitionBootstrapConfig,
    )
    from src.graph.core.entity_recognition_fallback import (
        EntityRecognitionHeuristicFieldMap,
    )
    from src.graph.core.entity_recognition_payload import (
        EntityRecognitionPayloadConfig,
    )
    from src.graph.core.entity_recognition_prompt import (
        EntityRecognitionPromptConfig,
    )
    from src.graph.core.extraction_fallback import ExtractionHeuristicConfig
    from src.graph.core.extraction_payload import ExtractionPayloadConfig
    from src.graph.core.extraction_prompt import ExtractionPromptConfig
    from src.graph.core.feature_flags import GraphFeatureFlags
    from src.graph.core.graph_connection_prompt import GraphConnectorExtension
    from src.graph.core.relation_autopromotion_defaults import (
        RelationAutopromotionDefaults,
    )
    from src.graph.core.relation_suggestion_extension import (
        GraphRelationSuggestionExtension,
    )
    from src.graph.core.runtime_identity import GraphRuntimeIdentity
    from src.graph.core.search_extension import GraphSearchExtension
    from src.graph.core.view_config import GraphViewExtension


@dataclass(frozen=True)
class GraphDomainPack:
    """One registered graph domain pack layered on top of graph-core."""

    name: str
    runtime_identity: GraphRuntimeIdentity
    view_extension: GraphViewExtension
    feature_flags: GraphFeatureFlags
    dictionary_loading_extension: GraphDictionaryLoadingExtension
    domain_context_policy: GraphDomainContextPolicy
    entity_recognition_bootstrap: EntityRecognitionBootstrapConfig
    entity_recognition_fallback: EntityRecognitionHeuristicFieldMap
    entity_recognition_payload: EntityRecognitionPayloadConfig
    entity_recognition_prompt: EntityRecognitionPromptConfig
    extraction_fallback: ExtractionHeuristicConfig
    extraction_payload: ExtractionPayloadConfig
    extraction_prompt: ExtractionPromptConfig
    graph_connection_prompt: GraphConnectorExtension
    search_extension: GraphSearchExtension
    relation_suggestion_extension: GraphRelationSuggestionExtension
    relation_autopromotion_defaults: RelationAutopromotionDefaults

    @property
    def dictionary_domain_contexts(
        self,
    ) -> tuple[DictionaryDomainContextDefinition, ...]:
        """Compatibility accessor for pack-owned builtin dictionary contexts."""
        return self.dictionary_loading_extension.builtin_domain_contexts
