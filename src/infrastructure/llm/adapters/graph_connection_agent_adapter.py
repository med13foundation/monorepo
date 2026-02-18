"""Flujo-based adapter for graph-connection agent operations."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING

from flujo.exceptions import FlujoError, PausedException, PipelineAbortSignal

from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.graph_connection_port import GraphConnectionPort
from src.infrastructure.llm.adapters._graph_connection_adapter_pipeline_mixin import (
    _GraphConnectionAdapterPipelineMixin,
)
from src.infrastructure.llm.adapters._graph_connection_adapter_trace_mixin import (
    _GraphConnectionAdapterTraceMixin,
)
from src.infrastructure.llm.config.governance import GovernanceConfig
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.pipelines.graph_connection_pipelines import (
    create_clinvar_graph_connection_pipeline,
    create_pubmed_graph_connection_pipeline,
)
from src.infrastructure.llm.state import backend_manager, lifecycle

if TYPE_CHECKING:
    from collections.abc import Callable

    from flujo import Flujo
    from flujo.state.backends.base import StateBackend

    from src.domain.agents.contexts.graph_connection_context import (
        GraphConnectionContext,
    )
    from src.domain.agents.contracts.graph_connection import GraphConnectionContract
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.domain.ports.graph_query_port import GraphQueryPort
    from src.domain.repositories.kernel.relation_repository import (
        KernelRelationRepository,
    )
    from src.infrastructure.llm.state.lifecycle import FlujoLifecycleManager

logger = logging.getLogger(__name__)

_SUPPORTED_SOURCE_TYPES = frozenset({"clinvar", "pubmed"})

if TYPE_CHECKING:
    GraphConnectionPipelineFactory = Callable[
        ...,
        Flujo[str, GraphConnectionContract, GraphConnectionContext],
    ]


def get_state_backend() -> StateBackend:
    """Patch-friendly indirection for tests and adapter construction."""
    return backend_manager.get_state_backend()


def get_lifecycle_manager() -> FlujoLifecycleManager:
    """Patch-friendly indirection for tests and adapter construction."""
    return lifecycle.get_lifecycle_manager()


def build_graph_connection_tools(
    *,
    dictionary_service: DictionaryPort,
    graph_query_service: GraphQueryPort,
    relation_repository: KernelRelationRepository,
    research_space_id: str,
) -> tuple[object, ...]:
    """Load graph tool builders lazily while preserving patchable module API."""
    registry_module = __import__(
        "src.infrastructure.llm.skills.registry",
        fromlist=["build_graph_connection_tools"],
    )
    builder = registry_module.build_graph_connection_tools
    return tuple(
        builder(
            dictionary_service=dictionary_service,
            graph_query_service=graph_query_service,
            relation_repository=relation_repository,
            research_space_id=research_space_id,
        ),
    )


_PIPELINE_FACTORIES: dict[str, GraphConnectionPipelineFactory] = {
    "clinvar": create_clinvar_graph_connection_pipeline,
    "pubmed": create_pubmed_graph_connection_pipeline,
}


class FlujoGraphConnectionAdapter(
    _GraphConnectionAdapterPipelineMixin,
    _GraphConnectionAdapterTraceMixin,
    GraphConnectionPort,
):
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
        trace_enabled = self._is_trace_dump_enabled()
        trace_events: list[dict[str, object]] = []
        input_chars = len(input_text)
        initial_context_chars = self._estimate_json_chars(initial_context)
        started_at = time.monotonic()
        logger.info(
            "Graph-connection pipeline run started",
            extra={
                "graph_source_type": source_type,
                "graph_model_id": effective_model,
                "graph_seed_entity_id": context.seed_entity_id,
                "graph_research_space_id": context.research_space_id,
                "graph_shadow_mode": context.shadow_mode,
                "graph_max_depth": context.max_depth,
                "graph_relation_type_count": (
                    len(context.relation_types)
                    if isinstance(context.relation_types, list)
                    else 0
                ),
                "graph_input_chars": input_chars,
                "graph_initial_context_chars": initial_context_chars,
            },
        )

        try:
            result = await self._execute_pipeline(
                pipeline,
                input_text=input_text,
                initial_context=initial_context,
                fallback_context=context,
                trace_events=trace_events if trace_enabled else None,
            )
            duration_ms = int((time.monotonic() - started_at) * 1000)
            logger.info(
                "Graph-connection pipeline run completed",
                extra={
                    "graph_source_type": source_type,
                    "graph_model_id": effective_model,
                    "graph_seed_entity_id": context.seed_entity_id,
                    "graph_research_space_id": context.research_space_id,
                    "graph_duration_ms": duration_ms,
                    "graph_decision": result.decision,
                    "graph_confidence_score": result.confidence_score,
                    "graph_proposed_relations": len(result.proposed_relations),
                    "graph_rejected_candidates": len(result.rejected_candidates),
                },
            )
            if trace_enabled:
                self._emit_trace_dump(
                    status="completed",
                    context=context,
                    effective_model=effective_model,
                    input_text=input_text,
                    initial_context=initial_context,
                    trace_events=trace_events,
                    output_contract=result,
                    duration_ms=duration_ms,
                    error_message=None,
                )
        except (PausedException, PipelineAbortSignal):
            raise
        except FlujoError as exc:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            logger.warning(
                "Graph-connection pipeline failed; returning heuristic fallback",
                extra={
                    "graph_source_type": source_type,
                    "graph_model_id": effective_model,
                    "graph_seed_entity_id": context.seed_entity_id,
                    "graph_research_space_id": context.research_space_id,
                    "graph_duration_ms": duration_ms,
                    "graph_failure_type": type(exc).__name__,
                    "graph_failure_message": str(exc),
                },
            )
            fallback_contract = self._heuristic_contract(context, decision="fallback")
            if trace_enabled:
                self._emit_trace_dump(
                    status="flujo_error_fallback",
                    context=context,
                    effective_model=effective_model,
                    input_text=input_text,
                    initial_context=initial_context,
                    trace_events=trace_events,
                    output_contract=fallback_contract,
                    duration_ms=duration_ms,
                    error_message=str(exc),
                )
            return fallback_contract
        else:
            return result

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

    def _resolve_model_id(self, model_id: str | None) -> str:
        if (
            self._registry.allow_runtime_model_overrides()
            and model_id is not None
            and self._registry.validate_model_for_capability(
                model_id,
                ModelCapability.EVIDENCE_EXTRACTION,
            )
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

    def _build_input_text(self, context: GraphConnectionContext) -> str:
        relation_types = (
            json.dumps(context.relation_types, default=str)
            if context.relation_types is not None
            else "null"
        )
        settings_payload = json.dumps(context.research_space_settings, default=str)
        base_input = (
            f"SOURCE TYPE: {context.source_type}\n"
            f"RESEARCH SPACE ID: {context.research_space_id}\n"
            f"SEED ENTITY ID: {context.seed_entity_id}\n"
            f"MAX DEPTH: {context.max_depth}\n"
            f"RELATION TYPES FILTER: {relation_types}\n"
            f"SHADOW MODE: {context.shadow_mode}\n\n"
            f"RESEARCH SPACE SETTINGS JSON:\n{settings_payload}"
        )
        snapshot_payload = self._build_seed_snapshot(context)
        if snapshot_payload is None:
            logger.info(
                "Graph-connection context payload assembled without seed snapshot",
                extra={
                    "graph_seed_entity_id": context.seed_entity_id,
                    "graph_research_space_id": context.research_space_id,
                    "graph_settings_chars": len(settings_payload),
                    "graph_snapshot_chars": 0,
                    "graph_input_chars": len(base_input),
                },
            )
            return base_input
        composed_input = f"{base_input}{self._INPUT_SNAPSHOT_MARKER}{snapshot_payload}"
        logger.info(
            "Graph-connection context payload assembled",
            extra={
                "graph_seed_entity_id": context.seed_entity_id,
                "graph_research_space_id": context.research_space_id,
                "graph_settings_chars": len(settings_payload),
                "graph_snapshot_chars": len(snapshot_payload),
                "graph_input_chars": len(composed_input),
            },
        )
        return composed_input


__all__ = ["FlujoGraphConnectionAdapter"]
