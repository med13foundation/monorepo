"""Flujo-based adapter for mapping-judge operations."""

from __future__ import annotations

import asyncio
import logging
import os
from threading import Thread
from typing import TYPE_CHECKING, Literal

from flujo.domain.models import PipelineResult, StepResult
from flujo.exceptions import FlujoError, PausedException, PipelineAbortSignal

from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.mapping_judge import MappingJudgeContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
from src.infrastructure.llm.config.governance import GovernanceConfig
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.pipelines.mapping_judge_pipelines import (
    create_mapping_judge_pipeline,
)
from src.infrastructure.llm.state.backend_manager import get_state_backend
from src.infrastructure.llm.state.lifecycle import get_lifecycle_manager

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from flujo import Flujo

    from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext

logger = logging.getLogger(__name__)

_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})


class FlujoMappingJudgeAdapter(MappingJudgePort):
    """Adapter that executes mapping-judge workflows through Flujo."""

    def __init__(self, model: str | None = None) -> None:
        self._default_model = model
        self._state_backend = get_state_backend()
        self._governance = GovernanceConfig.from_environment()
        self._registry = get_model_registry()
        self._lifecycle_manager = get_lifecycle_manager()
        self._pipelines: dict[
            str,
            Flujo[str, MappingJudgeContract, MappingJudgeContext],
        ] = {}
        self._last_run_id: str | None = None

    def judge(
        self,
        context: MappingJudgeContext,
        *,
        model_id: str | None = None,
    ) -> MappingJudgeContract:
        self._last_run_id = None

        if not self._has_openai_key():
            return self._fallback_contract(
                context,
                decision="no_match",
                reason="Mapping-judge API key is not configured.",
            )

        effective_model = self._resolve_model_id(model_id)
        pipeline = self._get_or_create_pipeline(effective_model)
        input_text = self._build_input_text(context)
        initial_context = context.model_dump(mode="json")

        try:
            return self._run_contract_coroutine(
                self._execute_pipeline(
                    pipeline,
                    input_text=input_text,
                    initial_context=initial_context,
                    fallback_context=context,
                ),
            )
        except (PausedException, PipelineAbortSignal):
            raise
        except FlujoError as exc:
            logger.warning(
                "Mapping-judge pipeline failed for field_key=%s: %s",
                context.field_key,
                exc,
            )
            return self._fallback_contract(
                context,
                decision="no_match",
                reason="Mapping-judge execution failed.",
            )

    def close(self) -> None:
        for cache_key, pipeline in self._pipelines.items():
            try:
                self._run_void_coroutine(
                    self._close_pipeline_async(pipeline),
                )
            except (RuntimeError, OSError, ConnectionError) as exc:
                logger.warning(
                    "Error closing mapping-judge pipeline for model=%s: %s",
                    cache_key,
                    exc,
                )
        self._pipelines.clear()

    async def _close_pipeline_async(
        self,
        pipeline: Flujo[str, MappingJudgeContract, MappingJudgeContext],
    ) -> None:
        if hasattr(pipeline, "aclose"):
            await pipeline.aclose()
        self._lifecycle_manager.unregister_runner(pipeline)

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
    ) -> Flujo[str, MappingJudgeContract, MappingJudgeContext]:
        if model_id in self._pipelines:
            return self._pipelines[model_id]

        pipeline = create_mapping_judge_pipeline(
            state_backend=self._state_backend,
            model=model_id,
            usage_limits=self._governance.usage_limits,
        )
        self._pipelines[model_id] = pipeline
        self._lifecycle_manager.register_runner(pipeline)
        return pipeline

    @staticmethod
    def _build_input_text(context: MappingJudgeContext) -> str:
        candidate_lines = [
            (
                f"- variable_id={candidate.variable_id}; "
                f"display_name={candidate.display_name}; "
                f"method={candidate.match_method}; "
                f"similarity={candidate.similarity_score:.3f}"
            )
            for candidate in context.candidates
        ]
        candidates_blob = "\n".join(candidate_lines)
        return (
            f"FIELD KEY: {context.field_key}\n"
            f"FIELD VALUE: {context.field_value_preview}\n"
            f"SOURCE ID: {context.source_id}\n"
            f"SOURCE TYPE: {context.source_type or 'unknown'}\n"
            f"DOMAIN CONTEXT: {context.domain_context or 'none'}\n"
            "CANDIDATES:\n"
            f"{candidates_blob}\n"
        )

    async def _execute_pipeline(
        self,
        pipeline: Flujo[str, MappingJudgeContract, MappingJudgeContext],
        *,
        input_text: str,
        initial_context: dict[str, object],
        fallback_context: MappingJudgeContext,
    ) -> MappingJudgeContract:
        final_output: MappingJudgeContract | None = None

        async for item in pipeline.run_async(
            input_text,
            initial_context_data=initial_context,
        ):
            if isinstance(item, StepResult):
                if isinstance(item.output, MappingJudgeContract):
                    final_output = item.output
            elif isinstance(item, PipelineResult):
                self._capture_run_id(item)
                candidate = self._extract_from_pipeline_result(item)
                if candidate is not None:
                    final_output = candidate

        if final_output is None:
            return self._fallback_contract(
                fallback_context,
                decision="no_match",
                reason="Mapping-judge returned no structured result.",
            )
        if self._last_run_id is not None and final_output.agent_run_id is None:
            final_output.agent_run_id = self._last_run_id
        return final_output

    def _extract_from_pipeline_result(
        self,
        result: PipelineResult[MappingJudgeContext],
    ) -> MappingJudgeContract | None:
        step_history = getattr(result, "step_history", None)
        if not isinstance(step_history, list):
            return None
        for step_result in reversed(step_history):
            if isinstance(step_result, StepResult) and isinstance(
                step_result.output,
                MappingJudgeContract,
            ):
                return step_result.output
        return None

    def _capture_run_id(self, result: PipelineResult[MappingJudgeContext]) -> None:
        context = result.final_pipeline_context
        run_id = getattr(context, "run_id", None)
        if isinstance(run_id, str) and run_id.strip():
            self._last_run_id = run_id.strip()

    def _fallback_contract(
        self,
        context: MappingJudgeContext,
        *,
        decision: Literal["no_match", "ambiguous"],
        reason: str,
    ) -> MappingJudgeContract:
        return MappingJudgeContract(
            decision=decision,
            selected_variable_id=None,
            candidate_count=len(context.candidates),
            selection_rationale=reason,
            selected_candidate=None,
            confidence_score=0.3 if decision == "no_match" else 0.2,
            rationale=reason,
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"mapping-judge:{context.source_id}:{context.field_key}",
                    excerpt=reason,
                    relevance=0.2,
                ),
            ],
            agent_run_id=self._last_run_id,
        )

    @staticmethod
    def _run_contract_coroutine(
        coroutine: Coroutine[object, object, MappingJudgeContract],
    ) -> MappingJudgeContract:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        result_holder: dict[str, MappingJudgeContract | None] = {"result": None}
        error_holder: dict[str, BaseException | None] = {"error": None}

        def _target() -> None:
            try:
                result_holder["result"] = asyncio.run(coroutine)
            except BaseException as exc:  # noqa: BLE001
                error_holder["error"] = exc

        thread = Thread(target=_target, daemon=True)
        thread.start()
        thread.join()

        if error_holder["error"] is not None:
            raise error_holder["error"]
        if result_holder["result"] is None:
            msg = "Mapping judge coroutine returned no contract."
            raise RuntimeError(msg)
        return result_holder["result"]

    @staticmethod
    def _run_void_coroutine(
        coroutine: Coroutine[object, object, None],
    ) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coroutine)
            return

        error_holder: dict[str, BaseException | None] = {"error": None}

        def _target() -> None:
            try:
                asyncio.run(coroutine)
            except BaseException as exc:  # noqa: BLE001
                error_holder["error"] = exc

        thread = Thread(target=_target, daemon=True)
        thread.start()
        thread.join()

        if error_holder["error"] is not None:
            raise error_holder["error"]


__all__ = ["FlujoMappingJudgeAdapter"]
