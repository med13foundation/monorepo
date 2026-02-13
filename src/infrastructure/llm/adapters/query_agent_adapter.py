"""
Flujo-based implementation of the query agent port.

Implements the QueryAgentPort using Flujo pipelines with
evidence-first contracts and governance patterns.
"""

import logging
from typing import Any

from flujo import Flujo
from flujo.domain.models import PipelineResult, StepResult
from flujo.exceptions import FlujoError, PausedException, PipelineAbortSignal

from src.domain.agents.contracts.query_generation import QueryGenerationContract
from src.domain.agents.ports.query_agent_port import (
    QueryAgentPort,
    QueryAgentRunMetadataProvider,
)
from src.infrastructure.llm.config.governance import GovernanceConfig
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.config.query_profiles import load_query_source_policies
from src.infrastructure.llm.pipelines.query_pipelines.clinvar_pipeline import (
    create_clinvar_query_pipeline,
)
from src.infrastructure.llm.pipelines.query_pipelines.pubmed_pipeline import (
    create_pubmed_query_pipeline,
)
from src.infrastructure.llm.state.backend_manager import get_state_backend
from src.infrastructure.llm.state.lifecycle import get_lifecycle_manager

from .query_agent_adapter_helpers import (
    PipelineCacheKey,
    QueryAgentContractMixin,
    QueryAgentPipelineConfigMixin,
    QueryPipelineFactory,
    _build_input_text,
)

logger = logging.getLogger(__name__)

_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})

_QUERY_PIPELINE_FACTORIES: dict[str, QueryPipelineFactory] = {
    "pubmed": create_pubmed_query_pipeline,
    "clinvar": create_clinvar_query_pipeline,
}


class FlujoQueryAgentAdapter(
    QueryAgentPipelineConfigMixin,
    QueryAgentContractMixin,
    QueryAgentPort,
    QueryAgentRunMetadataProvider,
):
    """
    Adapter that uses Flujo framework for query generation.

    Supports per-request model selection by caching pipelines for each
    (source_type, model_id) combination.
    """

    _query_pipeline_factories: dict[str, QueryPipelineFactory]

    def __init__(
        self,
        model: str | None = None,
        *,
        use_governance: bool = True,
        use_granular: bool = False,
    ) -> None:
        """
        Initialize the Flujo query agent adapter.

        Args:
            model: Optional default model ID override
            use_governance: Enable confidence-based governance
            use_granular: Use granular steps for multi-turn durability (default False)
        """
        self._default_model = model
        self._use_governance = use_governance
        self._use_granular = use_granular
        self._state_backend = get_state_backend()
        self._pipelines: dict[PipelineCacheKey, Flujo[Any, Any, Any]] = {}
        self._last_run_id: str | None = None
        self._governance = GovernanceConfig.from_environment()
        self._query_source_policies = load_query_source_policies()
        self._lifecycle_manager = get_lifecycle_manager()
        self._registry = get_model_registry()
        self._query_pipeline_factories = _QUERY_PIPELINE_FACTORIES

        # Initialize default pipeline for supported sources
        self._setup_default_pipelines()

    @staticmethod
    def _has_openai_key() -> bool:
        """
        Check if a valid OpenAI API key is configured.
        """
        import os

        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("FLUJO_OPENAI_API_KEY")
        if api_key is None:
            return False
        normalized = api_key.strip()
        if not normalized:
            return False
        return normalized.lower() not in _INVALID_OPENAI_KEYS

    async def generate_query(  # noqa: PLR0913
        self,
        research_space_description: str,
        user_instructions: str,
        source_type: str,
        *,
        model_id: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
    ) -> QueryGenerationContract:
        """
        Generate an intelligent query for the specified source type.

        Args:
            research_space_description: Description of the research space context
            user_instructions: User-provided prompting to steer the agent
            source_type: The source type (e.g., "pubmed", "clinvar")
        """
        self._last_run_id = None
        source_key = source_type.lower()

        if not self._is_supported_source(source_key):
            logger.warning(
                "Unsupported source type: %s. Returning escalation contract.",
                source_type,
            )
            return self._create_unsupported_source_contract(source_type)

        effective_model_id = self._resolve_model_id(source_key, model_id)
        if self._is_openai_model(effective_model_id) and not self._has_openai_key():
            logger.info(
                "OpenAI API key not configured; returning fallback contract for %s.",
                source_type,
            )
            return self._create_no_api_key_contract(source_type)

        pipeline = self._get_or_create_pipeline(source_key, effective_model_id)
        input_text = _build_input_text(
            research_space_description,
            user_instructions,
            source_type,
        )

        initial_context = {
            "user_id": user_id,
            "correlation_id": correlation_id,
            "source_type": source_type,
            "research_space_description": research_space_description,
            "user_instructions": user_instructions,
            "request_source": "api",
        }

        try:
            return await self._execute_pipeline(
                pipeline,
                input_text,
                initial_context,
            )
        except (PausedException, PipelineAbortSignal):
            raise
        except FlujoError as exc:
            logger.warning(
                "Flujo pipeline failed for %s; returning fallback contract. Error: %s",
                source_type,
                exc,
            )
            return self._create_error_contract(source_type, str(exc))

    async def _execute_pipeline(
        self,
        pipeline: Flujo[Any, Any, Any],
        input_text: str,
        initial_context: dict[str, str | None],
    ) -> QueryGenerationContract:
        """
        Execute pipeline and extract final query contract.
        """
        final_output: QueryGenerationContract | None = None

        async for item in pipeline.run_async(
            input_text,
            initial_context_data=initial_context,
        ):
            if isinstance(item, StepResult):
                candidate = self._extract_contract(item.output)
                if candidate:
                    final_output = candidate
            elif isinstance(item, PipelineResult):
                self._capture_run_id(item)
                candidate = self._extract_from_pipeline_result(item)
                if candidate:
                    final_output = candidate

        if final_output is None:
            logger.warning("Pipeline completed without producing a valid contract")
            return self._create_empty_result_contract(
                initial_context.get("source_type") or "unknown",
            )

        return final_output

    async def close(self) -> None:
        """
        Clean up cached pipelines and lifecycle registrations.
        """
        for cache_key, pipeline in self._pipelines.items():
            try:
                if hasattr(pipeline, "aclose"):
                    await pipeline.aclose()
                self._lifecycle_manager.unregister_runner(pipeline)
            except (RuntimeError, OSError, ConnectionError) as exc:
                logger.warning(
                    "Error closing pipeline for %s: %s",
                    cache_key,
                    exc,
                )

        self._pipelines.clear()

    def get_last_run_id(self) -> str | None:
        """
        Return the most recently executed Flujo run id.
        """
        return self._last_run_id
