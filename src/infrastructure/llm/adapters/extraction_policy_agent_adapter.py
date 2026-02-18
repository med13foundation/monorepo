"""Flujo-based adapter for extraction relation-policy operations."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

from flujo.domain.agent_result import FlujoAgentResult
from flujo.domain.models import PipelineResult, StepResult
from flujo.exceptions import FlujoError, PausedException, PipelineAbortSignal

from src.domain.agents.contracts import EvidenceItem
from src.domain.agents.contracts.extraction_policy import ExtractionPolicyContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.extraction_policy_agent_port import (
    ExtractionPolicyAgentPort,
)
from src.infrastructure.llm.config.governance import GovernanceConfig
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.pipelines.extraction_pipelines import (
    create_extraction_policy_pipeline,
)
from src.infrastructure.llm.state.backend_manager import get_state_backend
from src.infrastructure.llm.state.lifecycle import get_lifecycle_manager

if TYPE_CHECKING:
    from flujo import Flujo

    from src.domain.agents.contexts.extraction_policy_context import (
        ExtractionPolicyContext,
    )
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)

_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})


class FlujoExtractionPolicyAdapter(ExtractionPolicyAgentPort):
    """Adapter that executes extraction policy workflows through Flujo."""

    def __init__(self, model: str | None = None) -> None:
        self._default_model = model
        self._state_backend = get_state_backend()
        self._governance = GovernanceConfig.from_environment()
        self._registry = get_model_registry()
        self._lifecycle_manager = get_lifecycle_manager()
        self._pipelines: dict[
            str,
            Flujo[str, ExtractionPolicyContract, ExtractionPolicyContext],
        ] = {}
        self._last_run_id: str | None = None

    async def propose(
        self,
        context: ExtractionPolicyContext,
        *,
        model_id: str | None = None,
    ) -> ExtractionPolicyContract:
        self._last_run_id = None

        if not self._has_openai_key():
            return self._fallback_contract(
                context,
                reason="missing_openai_api_key",
            )

        effective_model = self._resolve_model_id(model_id)
        pipeline = self._get_or_create_pipeline(effective_model)
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
                "Extraction policy pipeline failed for document=%s: %s",
                context.document_id,
                exc,
            )
            return self._fallback_contract(
                context,
                reason=f"pipeline_execution_failed:{type(exc).__name__}",
            )

    async def close(self) -> None:
        for cache_key, pipeline in self._pipelines.items():
            try:
                if hasattr(pipeline, "aclose"):
                    await pipeline.aclose()
                self._lifecycle_manager.unregister_runner(pipeline)
            except (RuntimeError, OSError, ConnectionError) as exc:
                logger.warning(
                    "Error closing extraction-policy pipeline for key=%s: %s",
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
    ) -> Flujo[str, ExtractionPolicyContract, ExtractionPolicyContext]:
        if model_id in self._pipelines:
            return self._pipelines[model_id]

        pipeline = create_extraction_policy_pipeline(
            state_backend=self._state_backend,
            model=model_id,
            usage_limits=self._governance.usage_limits,
        )
        self._pipelines[model_id] = pipeline
        self._lifecycle_manager.register_runner(pipeline)
        return pipeline

    @staticmethod
    def _build_input_text(context: ExtractionPolicyContext) -> str:
        serialized_patterns = json.dumps(
            [
                pattern.model_dump(mode="json")
                for pattern in context.unknown_relation_patterns
            ],
            default=str,
        )
        serialized_constraints = json.dumps(context.current_constraints, default=str)
        serialized_relation_types = json.dumps(
            context.existing_relation_types,
            default=str,
        )
        return (
            f"DOCUMENT ID: {context.document_id}\n"
            f"SOURCE TYPE: {context.source_type}\n"
            f"RESEARCH SPACE ID: {context.research_space_id or 'none'}\n"
            f"SHADOW MODE: {context.shadow_mode}\n\n"
            "UNKNOWN RELATION PATTERNS:\n"
            f"{serialized_patterns}\n\n"
            "CURRENT CONSTRAINTS SNAPSHOT:\n"
            f"{serialized_constraints}\n\n"
            "EXISTING RELATION TYPES:\n"
            f"{serialized_relation_types}\n"
        )

    async def _execute_pipeline(
        self,
        pipeline: Flujo[str, ExtractionPolicyContract, ExtractionPolicyContext],
        *,
        input_text: str,
        initial_context: JSONObject,
        fallback_context: ExtractionPolicyContext,
    ) -> ExtractionPolicyContract:
        final_output: ExtractionPolicyContract | None = None

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
            return self._fallback_contract(
                fallback_context,
                reason="pipeline_returned_no_contract",
            )

        if self._last_run_id is not None and final_output.agent_run_id is None:
            final_output.agent_run_id = self._last_run_id
        return final_output

    @staticmethod
    def _extract_contract(output: object) -> ExtractionPolicyContract | None:
        if isinstance(output, ExtractionPolicyContract):
            return output
        if isinstance(output, FlujoAgentResult):
            wrapped_output = output.output
            if isinstance(wrapped_output, ExtractionPolicyContract):
                return wrapped_output
        return None

    def _extract_from_pipeline_result(
        self,
        result: PipelineResult[ExtractionPolicyContext],
    ) -> ExtractionPolicyContract | None:
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

    def _capture_run_id(
        self,
        result: PipelineResult[ExtractionPolicyContext],
    ) -> None:
        context = result.final_pipeline_context
        run_id = getattr(context, "run_id", None)
        if isinstance(run_id, str) and run_id.strip():
            self._last_run_id = run_id.strip()

    def _fallback_contract(
        self,
        context: ExtractionPolicyContext,
        *,
        reason: str,
    ) -> ExtractionPolicyContract:
        return ExtractionPolicyContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=(
                "Policy agent unavailable; deterministic fail-open path should "
                f"continue ({reason})."
            ),
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"source_document:{context.document_id}",
                    excerpt=f"Policy proposal unavailable: {reason}",
                    relevance=1.0,
                ),
            ],
            source_type=context.source_type,
            document_id=context.document_id,
            unknown_patterns=context.unknown_relation_patterns,
            relation_constraint_proposals=[],
            relation_type_mapping_proposals=[],
            agent_run_id=self._last_run_id,
        )


__all__ = ["FlujoExtractionPolicyAdapter"]
