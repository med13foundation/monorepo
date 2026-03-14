"""Sports graph domain-pack wiring."""

from __future__ import annotations

from src.graph.core.dictionary_domain_contexts import DictionaryDomainContextDefinition
from src.graph.core.dictionary_loading_extension import GraphDictionaryLoadingConfig
from src.graph.core.domain_context_policy import (
    GraphDomainContextPolicy,
    SourceTypeDomainContextDefault,
)
from src.graph.core.domain_pack import GraphDomainPack
from src.graph.core.entity_recognition_bootstrap import (
    BootstrapRelationConstraintDefinition,
    BootstrapRelationTypeDefinition,
    BootstrapVariableDefinition,
    DomainBootstrapEntityTypes,
    EntityRecognitionBootstrapConfig,
)
from src.graph.core.entity_recognition_fallback import (
    EntityRecognitionHeuristicFieldMap,
)
from src.graph.core.entity_recognition_payload import (
    EntityRecognitionCompactRecordRule,
    EntityRecognitionPayloadConfig,
)
from src.graph.core.entity_recognition_prompt import EntityRecognitionPromptConfig
from src.graph.core.extraction_fallback import (
    ExtractionHeuristicConfig,
    ExtractionHeuristicRelation,
)
from src.graph.core.extraction_payload import (
    ExtractionCompactRecordRule,
    ExtractionPayloadConfig,
)
from src.graph.core.extraction_prompt import ExtractionPromptConfig
from src.graph.core.feature_flags import FeatureFlagDefinition, GraphFeatureFlags
from src.graph.core.graph_connection_prompt import GraphConnectionPromptConfig
from src.graph.core.relation_autopromotion_defaults import (
    RelationAutopromotionDefaults,
)
from src.graph.core.relation_suggestion_extension import (
    GraphRelationSuggestionConfig,
)
from src.graph.core.runtime_identity import GraphRuntimeIdentity
from src.graph.core.search_extension import GraphSearchConfig
from src.graph.core.view_config import GraphViewConfig

SPORTS_DICTIONARY_LOADING_EXTENSION = GraphDictionaryLoadingConfig(
    builtin_domain_contexts=(
        DictionaryDomainContextDefinition(
            id="general",
            display_name="General",
            description="Shared sports domain context for cross-cutting graph types.",
        ),
        DictionaryDomainContextDefinition(
            id="competition",
            display_name="Competition",
            description="Competition, fixture, and match-report domain context.",
        ),
        DictionaryDomainContextDefinition(
            id="roster",
            display_name="Roster",
            description="Player, coach, and team-roster domain context.",
        ),
    ),
)

SPORTS_GRAPH_DOMAIN_CONTEXT_POLICY = GraphDomainContextPolicy(
    source_type_defaults=(
        SourceTypeDomainContextDefault(
            source_type="match_report",
            domain_context="competition",
        ),
        SourceTypeDomainContextDefault(
            source_type="player_profile",
            domain_context="roster",
        ),
        SourceTypeDomainContextDefault(
            source_type="box_score",
            domain_context="competition",
        ),
    ),
)

SPORTS_ENTITY_RECOGNITION_BOOTSTRAP = EntityRecognitionBootstrapConfig(
    default_relation_type="RELATED_TO",
    default_relation_display_name="Related To",
    default_relation_description="General sports association between graph entities.",
    default_relation_inverse_label=None,
    interaction_relation_type="COMPETES_AGAINST",
    interaction_relation_display_name="Competes Against",
    interaction_relation_description="Competitive interaction between sports entities.",
    interaction_relation_inverse_label="COMPETES_AGAINST",
    min_entity_types_for_default_relation=2,
    interaction_entity_types=("TEAM", "ATHLETE"),
    domain_entity_types=(
        DomainBootstrapEntityTypes(
            domain_context="competition",
            entity_types=("MATCH", "TEAM", "TOURNAMENT", "SEASON"),
        ),
        DomainBootstrapEntityTypes(
            domain_context="roster",
            entity_types=("ATHLETE", "TEAM", "COACH"),
        ),
    ),
    source_types_with_publication_baseline=("match_report",),
    publication_baseline_source_label="match_report",
    publication_baseline_entity_description="Sports reporting document or match recap.",
    publication_baseline_entity_types=("REPORT", "MATCH", "TEAM", "ATHLETE"),
    publication_baseline_relation_types=(
        BootstrapRelationTypeDefinition(
            relation_type="MENTIONS",
            display_name="Mentions",
            description="A sports report mentions an entity or event.",
            is_directional=True,
            inverse_label="MENTIONED_IN",
        ),
        BootstrapRelationTypeDefinition(
            relation_type="REPORTS_ON",
            display_name="Reports On",
            description="A sports report describes a match or competition outcome.",
            is_directional=True,
            inverse_label="REPORTED_IN",
        ),
    ),
    publication_baseline_constraints=(
        BootstrapRelationConstraintDefinition(
            source_type="REPORT",
            relation_type="MENTIONS",
            target_type="TEAM",
            requires_evidence=True,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="REPORT",
            relation_type="MENTIONS",
            target_type="ATHLETE",
            requires_evidence=True,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="REPORT",
            relation_type="REPORTS_ON",
            target_type="MATCH",
            requires_evidence=True,
        ),
    ),
    publication_metadata_variables=(
        BootstrapVariableDefinition(
            variable_id="season",
            canonical_name="season",
            display_name="Season",
            data_type="string",
            description="Season identifier for a sports report or fixture.",
            constraints=None,
            synonyms=("campaign",),
        ),
        BootstrapVariableDefinition(
            variable_id="competition",
            canonical_name="competition",
            display_name="Competition",
            data_type="string",
            description="Competition or league associated with a sports record.",
            constraints=None,
            synonyms=("league", "tournament"),
        ),
        BootstrapVariableDefinition(
            variable_id="venue",
            canonical_name="venue",
            display_name="Venue",
            data_type="string",
            description="Venue or arena associated with the event.",
            constraints=None,
            synonyms=("stadium", "arena"),
        ),
    ),
)

SPORTS_ENTITY_RECOGNITION_HEURISTIC_FIELD_MAP = EntityRecognitionHeuristicFieldMap(
    source_type_fields={
        "match_report": {
            "team": ("home_team", "away_team", "team"),
            "athlete": ("player_name", "scorer", "assister"),
            "match": ("match_id", "fixture_id"),
        },
        "player_profile": {
            "athlete": ("player_name", "athlete_name"),
            "team": ("team", "club"),
            "coach": ("coach",),
        },
    },
    default_source_type="match_report",
    primary_entity_types={
        "match_report": "REPORT",
        "player_profile": "ATHLETE",
    },
)

SPORTS_ENTITY_RECOGNITION_PAYLOAD_CONFIG = EntityRecognitionPayloadConfig(
    compact_record_rules={
        "match_report": EntityRecognitionCompactRecordRule(
            fields=(
                "report_id",
                "competition",
                "season",
                "home_team",
                "away_team",
                "summary",
            ),
            preferred_text_fields=("full_text", "summary"),
        ),
        "player_profile": EntityRecognitionCompactRecordRule(
            fields=("player_id", "player_name", "team", "position", "bio"),
            preferred_text_fields=("bio",),
        ),
    },
)

SPORTS_ENTITY_RECOGNITION_PROMPT_CONFIG = EntityRecognitionPromptConfig(
    system_prompts_by_source_type={
        "match_report": (
            "Extract sports graph entities from match reports, including teams, "
            "athletes, matches, venues, and competition context."
        ),
        "player_profile": (
            "Extract sports graph entities from roster and player profile "
            "records, including athletes, teams, coaches, and roles."
        ),
    },
)

SPORTS_EXTRACTION_HEURISTIC_CONFIG = ExtractionHeuristicConfig(
    relation_when_variant_and_phenotype_present=ExtractionHeuristicRelation(
        source_type="ATHLETE",
        relation_type="PLAYS_FOR",
        target_type="TEAM",
        polarity="SUPPORT",
    ),
    claim_text_fields=("summary", "headline"),
)

SPORTS_EXTRACTION_PAYLOAD_CONFIG = ExtractionPayloadConfig(
    compact_record_rules={
        "match_report": ExtractionCompactRecordRule(
            fields=(
                "report_id",
                "competition",
                "season",
                "home_team",
                "away_team",
                "headline",
                "summary",
            ),
            chunk_fields=(
                "report_id",
                "competition",
                "season",
                "home_team",
                "away_team",
                "full_text_chunk",
            ),
            chunk_indicator_field="full_text_chunk_index",
            fallback_text_field="summary",
        ),
        "player_profile": ExtractionCompactRecordRule(
            fields=("player_id", "player_name", "team", "position", "bio"),
            fallback_text_field="bio",
        ),
    },
)

SPORTS_EXTRACTION_PROMPT_CONFIG = ExtractionPromptConfig(
    system_prompts_by_source_type={
        "match_report": (
            "Extract grounded sports claims and relations from match reports. "
            "Prefer explicit game events, roster facts, and competition outcomes."
        ),
        "player_profile": (
            "Extract stable sports roster facts from player profile records, "
            "including team membership, role, and coach relationships."
        ),
    },
)

SPORTS_GRAPH_FEATURE_FLAGS = GraphFeatureFlags(
    entity_embeddings=FeatureFlagDefinition(
        primary_env_name="GRAPH_ENABLE_ENTITY_EMBEDDINGS",
    ),
    relation_suggestions=FeatureFlagDefinition(
        primary_env_name="GRAPH_ENABLE_RELATION_SUGGESTIONS",
    ),
    hypothesis_generation=FeatureFlagDefinition(
        primary_env_name="GRAPH_ENABLE_HYPOTHESIS_GENERATION",
    ),
    search_agent=FeatureFlagDefinition(
        primary_env_name="GRAPH_ENABLE_SEARCH_AGENT",
        default_enabled=True,
    ),
)

SPORTS_GRAPH_CONNECTION_PROMPT_CONFIG = GraphConnectionPromptConfig(
    default_source_type="match_report",
    system_prompts_by_source_type={
        "match_report": (
            "Connect sports graph entities from match reports using grounded "
            "competition evidence, outcomes, and roster context."
        ),
        "player_profile": (
            "Connect athletes, teams, and coaches from sports profile records "
            "using grounded roster facts."
        ),
    },
    step_key_prefix="graph.connection.sports",
)

SPORTS_GRAPH_SEARCH_EXTENSION = GraphSearchConfig(
    system_prompt=(
        "Sports Graph Search Agent. Answer sports graph questions with explicit "
        "evidence, grounded claims, and concise competition context."
    ),
    step_key="graph.search.sports.v1",
)

SPORTS_RELATION_SUGGESTION_EXTENSION = GraphRelationSuggestionConfig(
    vector_candidate_limit=75,
    min_vector_similarity=0.1,
)

SPORTS_RELATION_AUTOPROMOTION_DEFAULTS = RelationAutopromotionDefaults(
    min_distinct_sources=2,
    min_aggregate_confidence=0.9,
    computational_min_distinct_sources=3,
    computational_min_aggregate_confidence=0.95,
)

SPORTS_GRAPH_VIEW_EXTENSION = GraphViewConfig(
    entity_view_types={
        "team": "TEAM",
        "athlete": "ATHLETE",
        "match": "MATCH",
    },
    document_view_types=frozenset({"report"}),
    claim_view_types=frozenset({"claim"}),
    mechanism_relation_types=frozenset(
        {
            "PLAYS_FOR",
            "COACHED_BY",
            "COMPETES_AGAINST",
            "DEFEATED",
            "SCORED_AGAINST",
        },
    ),
)

_SPORTS_GRAPH_DOMAIN_PACK = GraphDomainPack(
    name="sports",
    runtime_identity=GraphRuntimeIdentity(
        service_name="Sports Graph Service",
        jwt_issuer="graph-sports",
    ),
    view_extension=SPORTS_GRAPH_VIEW_EXTENSION,
    feature_flags=SPORTS_GRAPH_FEATURE_FLAGS,
    dictionary_loading_extension=SPORTS_DICTIONARY_LOADING_EXTENSION,
    domain_context_policy=SPORTS_GRAPH_DOMAIN_CONTEXT_POLICY,
    entity_recognition_bootstrap=SPORTS_ENTITY_RECOGNITION_BOOTSTRAP,
    entity_recognition_fallback=SPORTS_ENTITY_RECOGNITION_HEURISTIC_FIELD_MAP,
    entity_recognition_payload=SPORTS_ENTITY_RECOGNITION_PAYLOAD_CONFIG,
    entity_recognition_prompt=SPORTS_ENTITY_RECOGNITION_PROMPT_CONFIG,
    extraction_fallback=SPORTS_EXTRACTION_HEURISTIC_CONFIG,
    extraction_payload=SPORTS_EXTRACTION_PAYLOAD_CONFIG,
    extraction_prompt=SPORTS_EXTRACTION_PROMPT_CONFIG,
    graph_connection_prompt=SPORTS_GRAPH_CONNECTION_PROMPT_CONFIG,
    search_extension=SPORTS_GRAPH_SEARCH_EXTENSION,
    relation_suggestion_extension=SPORTS_RELATION_SUGGESTION_EXTENSION,
    relation_autopromotion_defaults=SPORTS_RELATION_AUTOPROMOTION_DEFAULTS,
)


def get_sports_graph_domain_pack() -> GraphDomainPack:
    """Return the sports graph domain pack."""
    return _SPORTS_GRAPH_DOMAIN_PACK
