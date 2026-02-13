"""Helper mixins for the Flujo query agent adapter.

These helpers isolate supporting logic for pipeline resolution and contract
creation while keeping the adapter class focused on orchestration.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from flujo import Flujo
from flujo.domain.models import PipelineResult, StepResult

from src.domain.agents.contexts import QueryGenerationContext
from src.domain.agents.contracts.query_generation import QueryGenerationContract
from src.domain.agents.models import ModelCapability
from src.infrastructure.llm.config.governance import GovernanceConfig, UsageLimits
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.config.query_profiles import QuerySourcePolicy

PipelineCacheKey = tuple[str, str]
QueryPipelineFactory = Callable[
    ...,
    Flujo[str, QueryGenerationContract, QueryGenerationContext],
]


class _LifecycleManager(Protocol):
    """Minimal lifecycle-manager interface used by this adapter."""

    def register_runner(
        self,
        runner: Flujo[str, QueryGenerationContract, QueryGenerationContext],
    ) -> None: ...

    def unregister_runner(
        self,
        runner: Flujo[str, QueryGenerationContract, QueryGenerationContext],
    ) -> None: ...


def _build_input_text(
    research_space_description: str,
    user_instructions: str,
    source_type: str,
) -> str:
    """Build the input text for the agent."""
    return (
        f"SOURCE TYPE: {source_type.upper()}\n"
        f"RESEARCH SPACE CONTEXT:\n{research_space_description}\n\n"
        f"USER STEERING INSTRUCTIONS:\n{user_instructions}\n\n"
        f"Generate a high-fidelity search query optimized for {source_type}."
    )


class QueryAgentPipelineConfigMixin:
    """Pipeline setup and resolution helpers."""

    _default_model: str | None
    _query_pipeline_factories: dict[str, QueryPipelineFactory]
    _query_source_policies: dict[str, QuerySourcePolicy]
    _governance: GovernanceConfig
    _use_governance: bool
    _use_granular: bool
    _state_backend: object
    _lifecycle_manager: _LifecycleManager
    _pipelines: dict[
        PipelineCacheKey,
        Flujo[str, QueryGenerationContract, QueryGenerationContext],
    ]

    def _setup_default_pipelines(self) -> None:
        """Initialize default pipelines for supported data sources."""
        default_model = self._default_model
        if default_model is None:
            default_model = (
                get_model_registry()
                .get_default_model(
                    ModelCapability.QUERY_GENERATION,
                )
                .model_id
            )

        # Create default PubMed pipeline
        self._get_or_create_pipeline("pubmed", default_model)

    def _get_or_create_pipeline(
        self,
        source_type: str,
        model_id: str | None,
    ) -> Flujo[str, QueryGenerationContract, QueryGenerationContext]:
        """Get cached pipeline or create a new one for the given source and model."""
        if model_id is None:
            model_id = self._default_model
            if model_id is None:
                registry = get_model_registry()
                model_id = registry.get_default_model(
                    ModelCapability.QUERY_GENERATION,
                ).model_id

        cache_key: PipelineCacheKey = (source_type.lower(), model_id)

        if cache_key in self._pipelines:
            return self._pipelines[cache_key]

        pipeline = self._create_pipeline_for_source(source_type.lower(), model_id)
        self._pipelines[cache_key] = pipeline
        self._lifecycle_manager.register_runner(pipeline)

        return pipeline

    def _create_pipeline_for_source(
        self,
        source_type: str,
        model_id: str,
    ) -> Flujo[str, QueryGenerationContract, QueryGenerationContext]:
        """Create a pipeline for a specific source and model."""
        if source_type in self._query_pipeline_factories:
            pipeline_factory = self._query_pipeline_factories[source_type]
            return pipeline_factory(
                state_backend=self._state_backend,
                model=model_id,
                use_governance=self._use_governance,
                use_granular=self._use_granular,
                usage_limits=self._resolve_usage_limits(source_type),
            )

        msg = f"Unsupported source type: {source_type}"
        raise ValueError(msg)

    def _is_supported_source(self, source_type: str) -> bool:
        """Check if a source type is supported."""
        return source_type.lower() in self._query_pipeline_factories

    def _resolve_usage_limits(self, source_type: str) -> UsageLimits:
        """Resolve usage limits for a source type."""
        policy = self._query_source_policies.get(source_type.lower())
        profile_limits = policy.usage_limits if policy else None
        if profile_limits is None:
            return self._governance.usage_limits

        return UsageLimits(
            total_cost_usd=(
                profile_limits.total_cost_usd
                if profile_limits.total_cost_usd is not None
                else self._governance.usage_limits.total_cost_usd
            ),
            max_turns=(
                profile_limits.max_turns
                if profile_limits.max_turns is not None
                else self._governance.usage_limits.max_turns
            ),
            max_tokens=(
                profile_limits.max_tokens
                if profile_limits.max_tokens is not None
                else self._governance.usage_limits.max_tokens
            ),
        )

    def _resolve_model_id(
        self,
        source_type: str,
        model_id: str | None = None,
    ) -> str:
        """Resolve the effective model ID."""
        if model_id is not None and get_model_registry().validate_model_for_capability(
            model_id,
            ModelCapability.QUERY_GENERATION,
        ):
            return model_id

        source_model_id = self._query_source_policies.get(
            source_type.lower(),
            QuerySourcePolicy(),
        ).model_id
        if (
            source_model_id is not None
            and get_model_registry().validate_model_for_capability(
                source_model_id,
                ModelCapability.QUERY_GENERATION,
            )
        ):
            return source_model_id

        if self._default_model is not None:
            return self._default_model

        return (
            get_model_registry()
            .get_default_model(
                ModelCapability.QUERY_GENERATION,
            )
            .model_id
        )

    @staticmethod
    def _is_openai_model(model_id: str | None = None) -> bool:
        """Check if model is an OpenAI model."""
        if model_id:
            return model_id.startswith("openai:")
        return True


class QueryAgentContractMixin:
    """Contract and pipeline-result extraction helpers."""

    _last_run_id: str | None

    @staticmethod
    def _extract_contract(output: object) -> QueryGenerationContract | None:
        """Extract a contract from step output."""
        if isinstance(output, QueryGenerationContract):
            return output
        return None

    def _extract_from_pipeline_result(
        self,
        result: PipelineResult[QueryGenerationContext],
    ) -> QueryGenerationContract | None:
        """Extract contract from pipeline result's step history."""
        step_history = getattr(result, "step_history", None)
        if not isinstance(step_history, list):
            return None

        for step_result in reversed(step_history):
            if isinstance(step_result, StepResult):
                candidate = self._extract_contract(step_result.output)
                if candidate:
                    return candidate
        return None

    def _capture_run_id(self, result: PipelineResult[QueryGenerationContext]) -> None:
        """Capture the run ID from the pipeline result."""
        context: object = result.final_pipeline_context
        if context is None:
            return

        run_id = getattr(context, "run_id", None)
        if isinstance(run_id, str) and run_id.strip():
            self._last_run_id = run_id.strip()
            return

        if hasattr(context, "get"):
            get_method = context.get
            run_id_val = get_method("run_id")
            if isinstance(run_id_val, str) and run_id_val.strip():
                self._last_run_id = run_id_val.strip()

    @staticmethod
    def _create_unsupported_source_contract(
        source_type: str,
    ) -> QueryGenerationContract:
        """Create a contract for unsupported source types."""
        return QueryGenerationContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=f"Source type '{source_type}' is not yet supported.",
            evidence=[],
            query="",
            source_type=source_type,
            query_complexity="simple",
        )

    @staticmethod
    def _create_no_api_key_contract(source_type: str) -> QueryGenerationContract:
        """Create a contract when API key is missing."""
        return QueryGenerationContract(
            decision="fallback",
            confidence_score=0.0,
            rationale="OpenAI API key not configured. Cannot generate intelligent query.",
            evidence=[],
            query="",
            source_type=source_type,
            query_complexity="simple",
        )

    @staticmethod
    def _create_error_contract(
        source_type: str,
        error: str,
    ) -> QueryGenerationContract:
        """Create a contract for pipeline errors."""
        return QueryGenerationContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=f"Pipeline execution failed: {error}",
            evidence=[],
            query="",
            source_type=source_type,
            query_complexity="simple",
        )

    @staticmethod
    def _create_empty_result_contract(source_type: str) -> QueryGenerationContract:
        """Create a contract when pipeline produces no output."""
        return QueryGenerationContract(
            decision="escalate",
            confidence_score=0.0,
            rationale="Pipeline completed without producing a valid query.",
            evidence=[],
            query="",
            source_type=source_type,
            query_complexity="simple",
        )
