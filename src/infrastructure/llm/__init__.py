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

from src.infrastructure.llm.adapters.query_agent_adapter import FlujoQueryAgentAdapter
from src.infrastructure.llm.config.flujo_config import resolve_flujo_state_uri
from src.infrastructure.llm.config.governance import GovernanceConfig
from src.infrastructure.llm.config.model_registry import (
    FlujoModelRegistry,
    ModelRegistry,
    get_model_registry,
)
from src.infrastructure.llm.factories.query_agent_factory import (
    QueryAgentFactory,
    create_clinvar_query_agent,
    create_pubmed_query_agent,
)
from src.infrastructure.llm.pipelines.query_pipelines.clinvar_pipeline import (
    create_clinvar_query_pipeline,
)
from src.infrastructure.llm.pipelines.query_pipelines.pubmed_pipeline import (
    create_pubmed_query_pipeline,
)
from src.infrastructure.llm.skills.registry import (
    SkillRegistry,
    get_skill_registry,
    register_all_skills,
)
from src.infrastructure.llm.state.backend_manager import (
    StateBackendManager,
    get_state_backend,
)
from src.infrastructure.llm.state.flujo_state_repository import (
    SqlAlchemyFlujoStateRepository,
)
from src.infrastructure.llm.state.lifecycle import (
    FlujoLifecycleManager,
    flujo_lifespan,
    get_lifecycle_manager,
)

__all__ = [
    # Adapters
    "FlujoQueryAgentAdapter",
    # Config
    "FlujoModelRegistry",
    "GovernanceConfig",
    "ModelRegistry",
    "get_model_registry",
    "resolve_flujo_state_uri",
    # Factories
    "create_pubmed_query_agent",
    "create_clinvar_query_agent",
    "QueryAgentFactory",
    # Pipelines
    "create_pubmed_query_pipeline",
    "create_clinvar_query_pipeline",
    # Skills
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
