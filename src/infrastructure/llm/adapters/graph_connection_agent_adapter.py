"""Flujo-based adapter for graph-connection agent operations."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Literal

from flujo.domain.models import PipelineResult, StepResult
from flujo.exceptions import FlujoError, PausedException, PipelineAbortSignal

from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_connection import (
    GraphConnectionContract,
    RejectedCandidate,
)
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.graph_connection_port import GraphConnectionPort
from src.infrastructure.llm.config.governance import GovernanceConfig
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.pipelines.graph_connection_pipelines import (
    create_clinvar_graph_connection_pipeline,
    create_pubmed_graph_connection_pipeline,
)
from src.infrastructure.llm.skills.registry import build_graph_connection_tools
from src.infrastructure.llm.state.backend_manager import get_state_backend
from src.infrastructure.llm.state.lifecycle import get_lifecycle_manager

if TYPE_CHECKING:
    from collections.abc import Callable

    from flujo import Flujo

    from src.domain.agents.contexts.graph_connection_context import (
        GraphConnectionContext,
    )
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.domain.ports.graph_query_port import GraphQueryPort
    from src.domain.repositories.kernel.relation_repository import (
        KernelRelationRepository,
    )
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)

_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})
_SUPPORTED_SOURCE_TYPES = frozenset({"clinvar", "pubmed"})

if TYPE_CHECKING:
    GraphConnectionPipelineFactory = Callable[
        ...,
        Flujo[str, GraphConnectionContract, GraphConnectionContext],
    ]

_PIPELINE_FACTORIES: dict[str, GraphConnectionPipelineFactory] = {
    "clinvar": create_clinvar_graph_connection_pipeline,
    "pubmed": create_pubmed_graph_connection_pipeline,
}


class FlujoGraphConnectionAdapter(GraphConnectionPort):
    """Adapter that executes graph-connection workflows through Flujo."""

    def __init__(
        self,
        model: str | None = None,
        *,
        use_governance: bool = True,
        dictionary_service: DictionaryPort | None = None,
        graph_query_service: GraphQueryPort | None = None,
        relation_repository: KernelRelationRepository | None = None,
    ) -> None:
        self._default_model = model
        self._use_governance = use_governance
        self._dictionary_service = dictionary_service
        self._graph_query_service = graph_query_service
        self._relation_repository = relation_repository
        self._state_backend = get_state_backend()
        self._governance = GovernanceConfig.from_environment()
        self._registry = get_model_registry()
        self._lifecycle_manager = get_lifecycle_manager()
        self._pipelines: dict[
            tuple[str, str, str],
            Flujo[str, GraphConnectionContract, GraphConnectionContext],
        ] = {}
        self._last_run_id: str | None = None

    async def discover(
        self,
        context: GraphConnectionContext,
        *,
        model_id: str | None = None,
    ) -> GraphConnectionContract:
        self._last_run_id = None
        source_type = context.source_type.strip().lower()
        if source_type not in _SUPPORTED_SOURCE_TYPES:
            return self._unsupported_source_contract(context)

        if not self._has_openai_key():
            return self._heuristic_contract(context, decision="fallback")

        if (
            self._dictionary_service is None
            or self._graph_query_service is None
            or self._relation_repository is None
        ):
            logger.warning(
                "Graph connection adapter missing required services for tool binding; "
                "falling back to heuristic mode.",
            )
            return self._heuristic_contract(context, decision="fallback")

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
                "Graph-connection pipeline failed for seed=%s: %s",
                context.seed_entity_id,
                exc,
            )
            return self._heuristic_contract(context, decision="fallback")

    async def close(self) -> None:
        for cache_key, pipeline in self._pipelines.items():
            try:
                if hasattr(pipeline, "aclose"):
                    await pipeline.aclose()
                self._lifecycle_manager.unregister_runner(pipeline)
            except (RuntimeError, OSError, ConnectionError) as exc:
                logger.warning(
                    "Error closing graph-connection pipeline for key=%s: %s",
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
            ModelCapability.EVIDENCE_EXTRACTION,
        ):
            return model_id
        if self._default_model is not None:
            return self._default_model
        return self._registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        ).model_id

    def _get_or_create_pipeline(
        self,
        model_id: str,
        *,
        context: GraphConnectionContext,
    ) -> Flujo[str, GraphConnectionContract, GraphConnectionContext]:
        source_type = context.source_type.strip().lower()
        cache_key = (source_type, model_id, context.research_space_id)
        if cache_key in self._pipelines:
            return self._pipelines[cache_key]

        tools: list[object] | None = None
        if (
            self._dictionary_service is not None
            and self._graph_query_service is not None
            and self._relation_repository is not None
        ):
            try:
                tools = list(
                    build_graph_connection_tools(
                        dictionary_service=self._dictionary_service,
                        graph_query_service=self._graph_query_service,
                        relation_repository=self._relation_repository,
                        research_space_id=context.research_space_id,
                    ),
                )
            except (LookupError, PermissionError, ValueError) as exc:
                logger.warning(
                    "Graph-connection tools unavailable for research_space_id=%s: %s",
                    context.research_space_id,
                    exc,
                )
                tools = None

        pipeline_factory = _PIPELINE_FACTORIES.get(source_type)
        if pipeline_factory is None:
            msg = f"Unsupported source type for pipeline dispatch: {source_type}"
            raise ValueError(msg)

        pipeline = pipeline_factory(
            state_backend=self._state_backend,
            model=model_id,
            use_governance=self._use_governance,
            usage_limits=self._governance.usage_limits,
            tools=tools,
        )
        self._pipelines[cache_key] = pipeline
        self._lifecycle_manager.register_runner(pipeline)
        return pipeline

    @staticmethod
    def _build_input_text(context: GraphConnectionContext) -> str:
        relation_types = (
            json.dumps(context.relation_types, default=str)
            if context.relation_types is not None
            else "null"
        )
        settings_payload = json.dumps(context.research_space_settings, default=str)
        return (
            f"SOURCE TYPE: {context.source_type}\n"
            f"RESEARCH SPACE ID: {context.research_space_id}\n"
            f"SEED ENTITY ID: {context.seed_entity_id}\n"
            f"MAX DEPTH: {context.max_depth}\n"
            f"RELATION TYPES FILTER: {relation_types}\n"
            f"SHADOW MODE: {context.shadow_mode}\n\n"
            f"RESEARCH SPACE SETTINGS JSON:\n{settings_payload}"
        )

    async def _execute_pipeline(
        self,
        pipeline: Flujo[str, GraphConnectionContract, GraphConnectionContext],
        *,
        input_text: str,
        initial_context: JSONObject,
        fallback_context: GraphConnectionContext,
    ) -> GraphConnectionContract:
        final_output: GraphConnectionContract | None = None

        async for item in pipeline.run_async(
            input_text,
            initial_context_data=initial_context,
        ):
            if isinstance(item, StepResult):
                candidate = self._extract_contract(item.output)
                if candidate is not None:
                    final_output = candidate
            elif isinstance(item, PipelineResult):
                self._capture_run_id(item)
                candidate = self._extract_from_pipeline_result(item)
                if candidate is not None:
                    final_output = candidate

        if final_output is None:
            return self._heuristic_contract(fallback_context, decision="fallback")
        return final_output

    def _extract_from_pipeline_result(
        self,
        result: PipelineResult[GraphConnectionContext],
    ) -> GraphConnectionContract | None:
        step_history = getattr(result, "step_history", None)
        if not isinstance(step_history, list):
            return None
        for step_result in reversed(step_history):
            if not isinstance(step_result, StepResult):
                continue
            candidate = self._extract_contract(step_result.output)
            if candidate is not None:
                return candidate
        return None

    @staticmethod
    def _extract_contract(output: object) -> GraphConnectionContract | None:
        if isinstance(output, GraphConnectionContract):
            return output
        wrapped_output = getattr(output, "output", None)
        if isinstance(wrapped_output, GraphConnectionContract):
            return wrapped_output
        return None

    def _capture_run_id(self, result: PipelineResult[GraphConnectionContext]) -> None:
        context = result.final_pipeline_context
        run_id = getattr(context, "run_id", None)
        if isinstance(run_id, str) and run_id.strip():
            self._last_run_id = run_id.strip()

    def _heuristic_contract(
        self,
        context: GraphConnectionContext,
        *,
        decision: Literal["generated", "fallback", "escalate"],
    ) -> GraphConnectionContract:
        rejected_candidates: list[RejectedCandidate] = []
        relation_count = 0
        if self._graph_query_service is not None:
            neighborhood = self._graph_query_service.graph_query_neighbourhood(
                research_space_id=context.research_space_id,
                entity_id=context.seed_entity_id,
                depth=1,
                relation_types=context.relation_types,
                limit=10,
            )
            relation_count = len(neighborhood)
            for relation in neighborhood[:3]:
                source_is_seed = str(relation.source_id) == context.seed_entity_id
                target_id = (
                    str(relation.target_id)
                    if source_is_seed
                    else str(relation.source_id)
                )
                rejected_candidates.append(
                    RejectedCandidate(
                        source_id=context.seed_entity_id,
                        relation_type=relation.relation_type,
                        target_id=target_id,
                        reason="heuristic_fallback_no_llm_reasoning",
                        confidence=min(relation.aggregate_confidence, 0.49),
                    ),
                )

        evidence = [
            EvidenceItem(
                source_type="db",
                locator=f"seed_entity:{context.seed_entity_id}",
                excerpt=(
                    "Heuristic graph fallback executed using deterministic "
                    "neighbourhood scan"
                ),
                relevance=0.65 if relation_count > 0 else 0.35,
            ),
        ]

        return GraphConnectionContract(
            decision=decision,
            confidence_score=0.45 if relation_count > 0 else 0.3,
            rationale="Heuristic graph-connection fallback executed",
            evidence=evidence,
            source_type=context.source_type,
            research_space_id=context.research_space_id,
            seed_entity_id=context.seed_entity_id,
            proposed_relations=[],
            rejected_candidates=rejected_candidates,
            shadow_mode=context.shadow_mode,
            agent_run_id=self._last_run_id,
        )

    @staticmethod
    def _unsupported_source_contract(
        context: GraphConnectionContext,
    ) -> GraphConnectionContract:
        return GraphConnectionContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=f"Source type '{context.source_type}' is not supported",
            evidence=[],
            source_type=context.source_type,
            research_space_id=context.research_space_id,
            seed_entity_id=context.seed_entity_id,
            shadow_mode=context.shadow_mode,
        )


__all__ = ["FlujoGraphConnectionAdapter"]
