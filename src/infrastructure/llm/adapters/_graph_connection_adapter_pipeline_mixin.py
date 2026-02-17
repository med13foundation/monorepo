"""Pipeline execution helpers for graph-connection adapter."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Literal, Protocol

from flujo.domain.models import PipelineResult, StepResult
from pydantic import ValidationError

from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_connection import (
    GraphConnectionContract,
    RejectedCandidate,
)

if TYPE_CHECKING:
    from flujo import Flujo

    from src.domain.agents.contexts.graph_connection_context import (
        GraphConnectionContext,
    )
    from src.domain.ports.graph_query_port import GraphQueryPort
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


class _GraphConnectionAdapterPipelineContext(Protocol):
    """Structural typing contract for pipeline helper mixins."""

    _graph_query_service: GraphQueryPort | None
    _last_run_id: str | None

    @classmethod
    def _resolve_seed_snapshot_limit(cls) -> int: ...

    @classmethod
    def _resolve_seed_snapshot_max_chars(cls) -> int: ...

    @staticmethod
    def _estimate_json_chars(payload: object) -> int: ...

    @staticmethod
    def _estimate_output_chars(output: object) -> int: ...

    @classmethod
    def _to_trace_json_value(
        cls,
        value: object,
        *,
        depth: int = 0,
    ) -> object: ...

    @staticmethod
    def _extract_contract(output: object) -> GraphConnectionContract | None: ...

    def _capture_run_id(
        self,
        result: PipelineResult[GraphConnectionContext],
    ) -> None: ...

    def _extract_from_pipeline_result(
        self,
        result: PipelineResult[GraphConnectionContext],
    ) -> GraphConnectionContract | None: ...

    def _heuristic_contract(
        self,
        context: GraphConnectionContext,
        *,
        decision: Literal["generated", "fallback", "escalate"],
    ) -> GraphConnectionContract: ...


class _GraphConnectionAdapterPipelineMixin:
    """Shared pipeline execution and contract extraction methods."""

    _last_run_id: str | None

    def _build_seed_snapshot(
        self: _GraphConnectionAdapterPipelineContext,
        context: GraphConnectionContext,
    ) -> str | None:
        if self._graph_query_service is None:
            return None
        snapshot_limit = self._resolve_seed_snapshot_limit()
        snapshot_max_chars = self._resolve_seed_snapshot_max_chars()
        try:
            neighbourhood = self._graph_query_service.graph_query_neighbourhood(
                research_space_id=context.research_space_id,
                entity_id=context.seed_entity_id,
                depth=1,
                relation_types=context.relation_types,
                limit=snapshot_limit,
            )
        except (TypeError, ValueError, RuntimeError):
            return None

        snapshot_rows: list[dict[str, object]] = [
            {
                "source_id": str(relation.source_id),
                "relation_type": relation.relation_type,
                "target_id": str(relation.target_id),
                "aggregate_confidence": float(relation.aggregate_confidence),
                "curation_status": relation.curation_status,
            }
            for relation in neighbourhood[:snapshot_limit]
        ]
        truncated_by_chars = False
        snapshot = {
            "seed_entity_id": context.seed_entity_id,
            "max_depth_hint": context.max_depth,
            "relation_count_total": len(neighbourhood),
            "relation_count_included": len(snapshot_rows),
            "snapshot_truncated": len(neighbourhood) > len(snapshot_rows),
            "relations": snapshot_rows,
        }
        payload = json.dumps(snapshot, default=str)
        while len(payload) > snapshot_max_chars and len(snapshot_rows) > 1:
            truncated_by_chars = True
            reduced_size = max(len(snapshot_rows) // 2, 1)
            snapshot_rows = snapshot_rows[:reduced_size]
            snapshot["relation_count_included"] = len(snapshot_rows)
            snapshot["snapshot_truncated"] = True
            snapshot["relations"] = snapshot_rows
            payload = json.dumps(snapshot, default=str)

        logger.info(
            "Graph seed snapshot assembled",
            extra={
                "graph_seed_entity_id": context.seed_entity_id,
                "graph_research_space_id": context.research_space_id,
                "graph_snapshot_relation_count_total": len(neighbourhood),
                "graph_snapshot_relation_count_included": len(snapshot_rows),
                "graph_snapshot_limit": snapshot_limit,
                "graph_snapshot_max_chars": snapshot_max_chars,
                "graph_snapshot_chars": len(payload),
                "graph_snapshot_truncated_by_chars": truncated_by_chars,
            },
        )
        return payload

    async def _execute_pipeline(
        self: _GraphConnectionAdapterPipelineContext,
        pipeline: Flujo[str, GraphConnectionContract, GraphConnectionContext],
        *,
        input_text: str,
        initial_context: JSONObject,
        fallback_context: GraphConnectionContext,
        trace_events: list[dict[str, object]] | None = None,
    ) -> GraphConnectionContract:
        final_output: GraphConnectionContract | None = None
        step_events = 0
        pipeline_events = 0
        extracted_contracts = 0
        started_at = time.monotonic()

        async for item in pipeline.run_async(
            input_text,
            initial_context_data=initial_context,
        ):
            if isinstance(item, StepResult):
                step_events += 1
                candidate = self._extract_contract(item.output)
                if candidate is not None:
                    extracted_contracts += 1
                    final_output = candidate
                step_name = getattr(item, "name", None)
                if trace_events is not None:
                    trace_events.append(
                        {
                            "event_type": "step_result",
                            "index": step_events,
                            "step_name": (
                                step_name.strip()
                                if isinstance(step_name, str) and step_name.strip()
                                else None
                            ),
                            "output": self._to_trace_json_value(item.output),
                            "contract": (
                                candidate.model_dump(mode="json")
                                if candidate is not None
                                else None
                            ),
                        },
                    )
                logger.info(
                    "Graph-connection pipeline step event",
                    extra={
                        "graph_seed_entity_id": fallback_context.seed_entity_id,
                        "graph_research_space_id": fallback_context.research_space_id,
                        "graph_step_index": step_events,
                        "graph_step_name": (
                            step_name.strip()
                            if isinstance(step_name, str) and step_name.strip()
                            else None
                        ),
                        "graph_step_output_chars": self._estimate_output_chars(
                            item.output,
                        ),
                        "graph_step_contract_extracted": candidate is not None,
                        "graph_step_decision": (
                            candidate.decision if candidate is not None else None
                        ),
                        "graph_step_proposed_relations": (
                            len(candidate.proposed_relations)
                            if candidate is not None
                            else 0
                        ),
                    },
                )
            elif isinstance(item, PipelineResult):
                pipeline_events += 1
                self._capture_run_id(item)
                candidate = self._extract_from_pipeline_result(item)
                if candidate is not None:
                    extracted_contracts += 1
                    final_output = candidate
                step_history = getattr(item, "step_history", None)
                history_count = (
                    len(step_history) if isinstance(step_history, list) else 0
                )
                if trace_events is not None:
                    trace_events.append(
                        {
                            "event_type": "pipeline_result",
                            "index": pipeline_events,
                            "step_history_count": history_count,
                            "pipeline_result": self._to_trace_json_value(item),
                            "contract": (
                                candidate.model_dump(mode="json")
                                if candidate is not None
                                else None
                            ),
                        },
                    )
                logger.info(
                    "Graph-connection pipeline aggregate event",
                    extra={
                        "graph_seed_entity_id": fallback_context.seed_entity_id,
                        "graph_research_space_id": fallback_context.research_space_id,
                        "graph_pipeline_event_index": pipeline_events,
                        "graph_pipeline_step_history_count": history_count,
                        "graph_pipeline_contract_extracted": candidate is not None,
                        "graph_pipeline_decision": (
                            candidate.decision if candidate is not None else None
                        ),
                    },
                )

        if final_output is None:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            logger.warning(
                "Graph-connection pipeline produced no contract; using heuristic fallback",
                extra={
                    "graph_seed_entity_id": fallback_context.seed_entity_id,
                    "graph_research_space_id": fallback_context.research_space_id,
                    "graph_duration_ms": duration_ms,
                    "graph_step_events": step_events,
                    "graph_pipeline_events": pipeline_events,
                    "graph_extracted_contract_events": extracted_contracts,
                },
            )
            return self._heuristic_contract(fallback_context, decision="fallback")

        duration_ms = int((time.monotonic() - started_at) * 1000)
        logger.info(
            "Graph-connection pipeline produced final contract",
            extra={
                "graph_seed_entity_id": fallback_context.seed_entity_id,
                "graph_research_space_id": fallback_context.research_space_id,
                "graph_duration_ms": duration_ms,
                "graph_step_events": step_events,
                "graph_pipeline_events": pipeline_events,
                "graph_extracted_contract_events": extracted_contracts,
                "graph_final_decision": final_output.decision,
                "graph_final_confidence": final_output.confidence_score,
                "graph_final_proposed_relations": len(final_output.proposed_relations),
                "graph_final_rejected_candidates": len(
                    final_output.rejected_candidates,
                ),
            },
        )
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
    def _extract_contract(  # noqa: C901, PLR0911, PLR0912
        output: object,
    ) -> GraphConnectionContract | None:
        if isinstance(output, GraphConnectionContract):
            return output
        if isinstance(output, str):
            try:
                parsed_output = json.loads(output)
            except json.JSONDecodeError:
                parsed_output = None
            if isinstance(parsed_output, dict):
                try:
                    return GraphConnectionContract.model_validate(parsed_output)
                except ValidationError:
                    return None
        if isinstance(output, dict):
            try:
                return GraphConnectionContract.model_validate(output)
            except ValidationError:
                return None
        wrapped_output = getattr(output, "output", None)
        if isinstance(wrapped_output, GraphConnectionContract):
            return wrapped_output
        if isinstance(wrapped_output, str):
            try:
                parsed_wrapped_output = json.loads(wrapped_output)
            except json.JSONDecodeError:
                parsed_wrapped_output = None
            if isinstance(parsed_wrapped_output, dict):
                try:
                    return GraphConnectionContract.model_validate(parsed_wrapped_output)
                except ValidationError:
                    return None
        if isinstance(wrapped_output, dict):
            try:
                return GraphConnectionContract.model_validate(wrapped_output)
            except ValidationError:
                return None
        return None

    def _capture_run_id(
        self: _GraphConnectionAdapterPipelineContext,
        result: PipelineResult[GraphConnectionContext],
    ) -> None:
        context = result.final_pipeline_context
        run_id = getattr(context, "run_id", None)
        if isinstance(run_id, str) and run_id.strip():
            self._last_run_id = run_id.strip()

    def _heuristic_contract(
        self: _GraphConnectionAdapterPipelineContext,
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


__all__ = ["_GraphConnectionAdapterPipelineMixin"]
