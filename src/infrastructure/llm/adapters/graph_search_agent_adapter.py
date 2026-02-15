"""Flujo-based adapter for graph-search agent operations."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Literal

from flujo.domain.models import PipelineResult, StepResult
from flujo.exceptions import FlujoError, PausedException, PipelineAbortSignal

from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_search import GraphSearchContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.graph_search_port import GraphSearchPort
from src.infrastructure.llm.config.governance import GovernanceConfig
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.pipelines.graph_search_pipelines import (
    create_graph_search_pipeline,
)
from src.infrastructure.llm.skills.registry import build_graph_search_tools
from src.infrastructure.llm.state.backend_manager import get_state_backend
from src.infrastructure.llm.state.lifecycle import get_lifecycle_manager

if TYPE_CHECKING:
    from flujo import Flujo

    from src.domain.agents.contexts.graph_search_context import GraphSearchContext
    from src.domain.ports.graph_query_port import GraphQueryPort
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)

_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})


class FlujoGraphSearchAdapter(GraphSearchPort):
    """Adapter that executes graph-search workflows through Flujo."""

    def __init__(
        self,
        model: str | None = None,
        *,
        graph_query_service: GraphQueryPort | None = None,
    ) -> None:
        self._default_model = model
        self._graph_query_service = graph_query_service
        self._state_backend = get_state_backend()
        self._governance = GovernanceConfig.from_environment()
        self._registry = get_model_registry()
        self._lifecycle_manager = get_lifecycle_manager()
        self._pipelines: dict[
            tuple[str, str],
            Flujo[str, GraphSearchContract, GraphSearchContext],
        ] = {}
        self._last_run_id: str | None = None

    async def search(
        self,
        context: GraphSearchContext,
        *,
        model_id: str | None = None,
    ) -> GraphSearchContract:
        self._last_run_id = None

        if not self._has_openai_key():
            return self._fallback_contract(
                context,
                decision="fallback",
                reason="Graph-search agent API key is not configured.",
            )

        if self._graph_query_service is None:
            logger.warning(
                "Graph-search adapter missing graph_query_service; "
                "falling back to deterministic path.",
            )
            return self._fallback_contract(
                context,
                decision="fallback",
                reason="Graph-search tools are unavailable.",
            )

        effective_model = self._resolve_model_id(model_id)
        pipeline = self._get_or_create_pipeline(effective_model, context=context)
        input_text = self._build_input_text(context)
        initial_context = context.model_dump(mode="json")

        try:
            return await self._execute_pipeline(
                pipeline,
                input_text=input_text,
                initial_context=initial_context,
                fallback_context=context,
            )
        except (PausedException, PipelineAbortSignal):
            raise
        except FlujoError as exc:
            logger.warning(
                "Graph-search pipeline failed for research_space_id=%s: %s",
                context.research_space_id,
                exc,
            )
            return self._fallback_contract(
                context,
                decision="fallback",
                reason="Graph-search agent execution failed.",
            )

    async def close(self) -> None:
        for cache_key, pipeline in self._pipelines.items():
            try:
                if hasattr(pipeline, "aclose"):
                    await pipeline.aclose()
                self._lifecycle_manager.unregister_runner(pipeline)
            except (RuntimeError, OSError, ConnectionError) as exc:
                logger.warning(
                    "Error closing graph-search pipeline for key=%s: %s",
                    cache_key,
                    exc,
                )
        self._pipelines.clear()

    @staticmethod
    def _has_openai_key() -> bool:
        raw_value = os.getenv("OPENAI_API_KEY") or os.getenv("FLUJO_OPENAI_API_KEY")
        if raw_value is None:
            return False
        normalized = raw_value.strip()
        if not normalized:
            return False
        return normalized.lower() not in _INVALID_OPENAI_KEYS

    def _resolve_model_id(self, model_id: str | None) -> str:
        if model_id is not None and self._registry.validate_model_for_capability(
            model_id,
            ModelCapability.QUERY_GENERATION,
        ):
            return model_id
        if self._default_model is not None:
            return self._default_model
        return self._registry.get_default_model(
            ModelCapability.QUERY_GENERATION,
        ).model_id

    def _get_or_create_pipeline(
        self,
        model_id: str,
        *,
        context: GraphSearchContext,
    ) -> Flujo[str, GraphSearchContract, GraphSearchContext]:
        cache_key = (model_id, context.research_space_id)
        if cache_key in self._pipelines:
            return self._pipelines[cache_key]

        tools: list[object] | None = None
        if self._graph_query_service is not None:
            try:
                tools = list(
                    build_graph_search_tools(
                        graph_query_service=self._graph_query_service,
                        research_space_id=context.research_space_id,
                    ),
                )
            except (LookupError, PermissionError, ValueError) as exc:
                logger.warning(
                    "Graph-search tools unavailable for research_space_id=%s: %s",
                    context.research_space_id,
                    exc,
                )
                tools = None

        pipeline = create_graph_search_pipeline(
            state_backend=self._state_backend,
            model=model_id,
            usage_limits=self._governance.usage_limits,
            tools=tools,
        )
        self._pipelines[cache_key] = pipeline
        self._lifecycle_manager.register_runner(pipeline)
        return pipeline

    @staticmethod
    def _build_input_text(context: GraphSearchContext) -> str:
        return (
            f"QUESTION: {context.question}\n"
            f"RESEARCH SPACE ID: {context.research_space_id}\n"
            f"MAX DEPTH: {context.max_depth}\n"
            f"TOP K: {context.top_k}\n"
            f"INCLUDE EVIDENCE CHAINS: {context.include_evidence_chains}\n"
            f"FORCE AGENT: {context.force_agent}\n"
        )

    async def _execute_pipeline(
        self,
        pipeline: Flujo[str, GraphSearchContract, GraphSearchContext],
        *,
        input_text: str,
        initial_context: JSONObject,
        fallback_context: GraphSearchContext,
    ) -> GraphSearchContract:
        final_output: GraphSearchContract | None = None

        async for item in pipeline.run_async(
            input_text,
            initial_context_data=initial_context,
        ):
            if isinstance(item, StepResult):
                if isinstance(item.output, GraphSearchContract):
                    final_output = item.output
            elif isinstance(item, PipelineResult):
                self._capture_run_id(item)
                candidate = self._extract_from_pipeline_result(item)
                if candidate is not None:
                    final_output = candidate

        if final_output is None:
            return self._fallback_contract(
                fallback_context,
                decision="fallback",
                reason="Graph-search agent returned no structured result.",
            )

        if self._last_run_id is not None and final_output.agent_run_id is None:
            final_output.agent_run_id = self._last_run_id
        return final_output

    def _extract_from_pipeline_result(
        self,
        result: PipelineResult[GraphSearchContext],
    ) -> GraphSearchContract | None:
        step_history = getattr(result, "step_history", None)
        if not isinstance(step_history, list):
            return None
        for step_result in reversed(step_history):
            if isinstance(step_result, StepResult) and isinstance(
                step_result.output,
                GraphSearchContract,
            ):
                return step_result.output
        return None

    def _capture_run_id(self, result: PipelineResult[GraphSearchContext]) -> None:
        context = result.final_pipeline_context
        run_id = getattr(context, "run_id", None)
        if isinstance(run_id, str) and run_id.strip():
            self._last_run_id = run_id.strip()

    def _fallback_contract(
        self,
        context: GraphSearchContext,
        *,
        decision: Literal["fallback", "escalate"],
        reason: str,
    ) -> GraphSearchContract:
        return GraphSearchContract(
            decision=decision,
            confidence_score=0.35 if decision == "fallback" else 0.05,
            rationale=reason,
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"graph-search:{context.research_space_id}",
                    excerpt=reason,
                    relevance=0.4 if decision == "fallback" else 0.1,
                ),
            ],
            research_space_id=context.research_space_id,
            original_query=context.question,
            interpreted_intent=context.question,
            query_plan_summary=(
                "Graph-search adapter fallback. Use deterministic search result."
            ),
            total_results=0,
            results=[],
            executed_path="agent",
            warnings=[reason],
            agent_run_id=self._last_run_id,
        )


__all__ = ["FlujoGraphSearchAdapter"]
