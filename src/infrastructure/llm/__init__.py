"""
LLM infrastructure layer for AI agents.

Provides Flujo-based implementations for AI agent operations
following contract-first, evidence-based patterns.

Module Organization:
- config/: Configuration management (flujo_config, governance, model_registry)
- factories/: Agent factories for creating Flujo agents
- pipelines/: Pipeline definitions with governance patterns
- adapters/: Port adapter implementations
- state/: State backend and lifecycle management
- skills/: Skill registry for bounded capabilities
- prompts/: Version-controlled system prompts
"""

from __future__ import annotations

from importlib import import_module

__all__ = [
    # Adapters
    "FlujoEntityRecognitionAdapter",
    "FlujoExtractionAdapter",
    "FlujoGraphConnectionAdapter",
    "FlujoGraphSearchAdapter",
    "FlujoQueryAgentAdapter",
    # Config
    "FlujoModelRegistry",
    "GovernanceConfig",
    "ModelRegistry",
    "get_model_registry",
    "resolve_flujo_state_uri",
    # Factories
    "create_entity_recognition_agent_for_source",
    "create_clinvar_entity_recognition_agent",
    "EntityRecognitionAgentFactory",
    "create_extraction_agent_for_source",
    "create_clinvar_extraction_agent",
    "ExtractionAgentFactory",
    "create_graph_connection_agent_for_source",
    "create_clinvar_graph_connection_agent",
    "GraphConnectionAgentFactory",
    "create_graph_search_agent",
    "GraphSearchAgentFactory",
    "create_pubmed_query_agent",
    "create_clinvar_query_agent",
    "QueryAgentFactory",
    # Pipelines
    "create_clinvar_entity_recognition_pipeline",
    "create_clinvar_extraction_pipeline",
    "create_clinvar_graph_connection_pipeline",
    "create_graph_search_pipeline",
    "create_pubmed_query_pipeline",
    "create_clinvar_query_pipeline",
    # Skills
    "build_extraction_validation_tools",
    "build_entity_recognition_dictionary_tools",
    "build_graph_connection_tools",
    "build_graph_search_tools",
    "get_skill_registry",
    "register_all_skills",
    "SkillRegistry",
    # State
    "flujo_lifespan",
    "FlujoLifecycleManager",
    "get_lifecycle_manager",
    "get_state_backend",
    "SqlAlchemyFlujoStateRepository",
    "StateBackendManager",
]

_EXPORT_MAP: dict[str, tuple[str, str]] = {
    "FlujoEntityRecognitionAdapter": (
        "src.infrastructure.llm.adapters.entity_recognition_agent_adapter",
        "FlujoEntityRecognitionAdapter",
    ),
    "FlujoExtractionAdapter": (
        "src.infrastructure.llm.adapters.extraction_agent_adapter",
        "FlujoExtractionAdapter",
    ),
    "FlujoGraphConnectionAdapter": (
        "src.infrastructure.llm.adapters.graph_connection_agent_adapter",
        "FlujoGraphConnectionAdapter",
    ),
    "FlujoGraphSearchAdapter": (
        "src.infrastructure.llm.adapters.graph_search_agent_adapter",
        "FlujoGraphSearchAdapter",
    ),
    "FlujoQueryAgentAdapter": (
        "src.infrastructure.llm.adapters.query_agent_adapter",
        "FlujoQueryAgentAdapter",
    ),
    "FlujoModelRegistry": (
        "src.infrastructure.llm.config.model_registry",
        "FlujoModelRegistry",
    ),
    "GovernanceConfig": (
        "src.infrastructure.llm.config.governance",
        "GovernanceConfig",
    ),
    "ModelRegistry": ("src.infrastructure.llm.config.model_registry", "ModelRegistry"),
    "get_model_registry": (
        "src.infrastructure.llm.config.model_registry",
        "get_model_registry",
    ),
    "resolve_flujo_state_uri": (
        "src.infrastructure.llm.config.flujo_config",
        "resolve_flujo_state_uri",
    ),
    "create_entity_recognition_agent_for_source": (
        "src.infrastructure.llm.factories.entity_recognition_agent_factory",
        "create_entity_recognition_agent_for_source",
    ),
    "create_clinvar_entity_recognition_agent": (
        "src.infrastructure.llm.factories.entity_recognition_agent_factory",
        "create_clinvar_entity_recognition_agent",
    ),
    "EntityRecognitionAgentFactory": (
        "src.infrastructure.llm.factories.entity_recognition_agent_factory",
        "EntityRecognitionAgentFactory",
    ),
    "create_extraction_agent_for_source": (
        "src.infrastructure.llm.factories.extraction_agent_factory",
        "create_extraction_agent_for_source",
    ),
    "create_clinvar_extraction_agent": (
        "src.infrastructure.llm.factories.extraction_agent_factory",
        "create_clinvar_extraction_agent",
    ),
    "ExtractionAgentFactory": (
        "src.infrastructure.llm.factories.extraction_agent_factory",
        "ExtractionAgentFactory",
    ),
    "create_graph_connection_agent_for_source": (
        "src.infrastructure.llm.factories.graph_connection_agent_factory",
        "create_graph_connection_agent_for_source",
    ),
    "create_clinvar_graph_connection_agent": (
        "src.infrastructure.llm.factories.graph_connection_agent_factory",
        "create_clinvar_graph_connection_agent",
    ),
    "GraphConnectionAgentFactory": (
        "src.infrastructure.llm.factories.graph_connection_agent_factory",
        "GraphConnectionAgentFactory",
    ),
    "create_graph_search_agent": (
        "src.infrastructure.llm.factories.graph_search_agent_factory",
        "create_graph_search_agent",
    ),
    "GraphSearchAgentFactory": (
        "src.infrastructure.llm.factories.graph_search_agent_factory",
        "GraphSearchAgentFactory",
    ),
    "create_pubmed_query_agent": (
        "src.infrastructure.llm.factories.query_agent_factory",
        "create_pubmed_query_agent",
    ),
    "create_clinvar_query_agent": (
        "src.infrastructure.llm.factories.query_agent_factory",
        "create_clinvar_query_agent",
    ),
    "QueryAgentFactory": (
        "src.infrastructure.llm.factories.query_agent_factory",
        "QueryAgentFactory",
    ),
    "create_clinvar_entity_recognition_pipeline": (
        "src.infrastructure.llm.pipelines.entity_recognition_pipelines.clinvar_pipeline",
        "create_clinvar_entity_recognition_pipeline",
    ),
    "create_clinvar_extraction_pipeline": (
        "src.infrastructure.llm.pipelines.extraction_pipelines.clinvar_pipeline",
        "create_clinvar_extraction_pipeline",
    ),
    "create_clinvar_graph_connection_pipeline": (
        "src.infrastructure.llm.pipelines.graph_connection_pipelines.clinvar_pipeline",
        "create_clinvar_graph_connection_pipeline",
    ),
    "create_graph_search_pipeline": (
        "src.infrastructure.llm.pipelines.graph_search_pipelines.default_pipeline",
        "create_graph_search_pipeline",
    ),
    "create_pubmed_query_pipeline": (
        "src.infrastructure.llm.pipelines.query_pipelines.pubmed_pipeline",
        "create_pubmed_query_pipeline",
    ),
    "create_clinvar_query_pipeline": (
        "src.infrastructure.llm.pipelines.query_pipelines.clinvar_pipeline",
        "create_clinvar_query_pipeline",
    ),
    "build_extraction_validation_tools": (
        "src.infrastructure.llm.skills.registry",
        "build_extraction_validation_tools",
    ),
    "build_entity_recognition_dictionary_tools": (
        "src.infrastructure.llm.skills.registry",
        "build_entity_recognition_dictionary_tools",
    ),
    "build_graph_connection_tools": (
        "src.infrastructure.llm.skills.registry",
        "build_graph_connection_tools",
    ),
    "build_graph_search_tools": (
        "src.infrastructure.llm.skills.registry",
        "build_graph_search_tools",
    ),
    "get_skill_registry": (
        "src.infrastructure.llm.skills.registry",
        "get_skill_registry",
    ),
    "register_all_skills": (
        "src.infrastructure.llm.skills.registry",
        "register_all_skills",
    ),
    "SkillRegistry": ("src.infrastructure.llm.skills.registry", "SkillRegistry"),
    "flujo_lifespan": ("src.infrastructure.llm.state.lifecycle", "flujo_lifespan"),
    "FlujoLifecycleManager": (
        "src.infrastructure.llm.state.lifecycle",
        "FlujoLifecycleManager",
    ),
    "get_lifecycle_manager": (
        "src.infrastructure.llm.state.lifecycle",
        "get_lifecycle_manager",
    ),
    "get_state_backend": (
        "src.infrastructure.llm.state.backend_manager",
        "get_state_backend",
    ),
    "SqlAlchemyFlujoStateRepository": (
        "src.infrastructure.llm.state.flujo_state_repository",
        "SqlAlchemyFlujoStateRepository",
    ),
    "StateBackendManager": (
        "src.infrastructure.llm.state.backend_manager",
        "StateBackendManager",
    ),
}


def __getattr__(name: str) -> object:
    target = _EXPORT_MAP.get(name)
    if target is None:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    module_name, attribute_name = target
    module = import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
