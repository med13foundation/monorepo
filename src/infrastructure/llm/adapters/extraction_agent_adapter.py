"""Flujo-based adapter for extraction agent operations."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

from flujo.domain.models import PipelineResult, StepResult
from flujo.exceptions import FlujoError, PausedException, PipelineAbortSignal

from src.domain.agents.contracts import EvidenceItem, ExtractionContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.extraction_agent_port import ExtractionAgentPort
from src.infrastructure.llm.config import GovernanceConfig, get_model_registry
from src.infrastructure.llm.pipelines.extraction_pipelines import (
    create_clinvar_extraction_pipeline,
    create_pubmed_extraction_pipeline,
)
from src.infrastructure.llm.skills import build_extraction_validation_tools
from src.infrastructure.llm.state import get_lifecycle_manager, get_state_backend
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable

    from flujo import Flujo

    from src.domain.agents.contexts.extraction_context import ExtractionContext
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)

_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})
_SUPPORTED_SOURCE_TYPES = frozenset({"clinvar", "pubmed"})
_PIPELINE_EXCEPTIONS = (
    FlujoError,
    RuntimeError,
    ValueError,
    TypeError,
    LookupError,
    OSError,
    ConnectionError,
)

if TYPE_CHECKING:
    ExtractionPipelineFactory = Callable[
        ...,
        Flujo[str, ExtractionContract, ExtractionContext],
    ]

_PIPELINE_FACTORIES: dict[str, ExtractionPipelineFactory] = {
    "clinvar": create_clinvar_extraction_pipeline,
    "pubmed": create_pubmed_extraction_pipeline,
}


class FlujoExtractionAdapter(ExtractionAgentPort):
    """Adapter that executes extraction workflows through Flujo."""

    def __init__(
        self,
        model: str | None = None,
        *,
        use_governance: bool = True,
        dictionary_service: DictionaryPort | None = None,
    ) -> None:
        self._default_model = model
        self._use_governance = use_governance
        self._dictionary_service = dictionary_service
        self._state_backend = get_state_backend()
        self._governance = GovernanceConfig.from_environment()
        self._registry = get_model_registry()
        self._lifecycle_manager = get_lifecycle_manager()
        self._pipelines: dict[
            tuple[str, str, bool],
            Flujo[str, ExtractionContract, ExtractionContext],
        ] = {}
        self._last_run_id: str | None = None

    async def extract(
        self,
        context: ExtractionContext,
        *,
        model_id: str | None = None,
    ) -> ExtractionContract:
        self._last_run_id = None
        source_type = context.source_type.strip().lower()
        if source_type not in _SUPPORTED_SOURCE_TYPES:
            return self._unsupported_source_contract(context)

        if not self._has_openai_key():
            return self._ai_required_contract(
                context,
                reason="missing_openai_api_key",
            )

        effective_model = self._resolve_model_id(model_id)
        pipeline = self._get_or_create_pipeline(
            effective_model,
            source_type=source_type,
            bind_tools=True,
        )
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
        except _PIPELINE_EXCEPTIONS as exc:
            logger.warning(
                "Extraction pipeline failed for document=%s: %s",
                context.document_id,
                exc,
            )
            retry_output = await self._retry_without_tools(
                source_type=source_type,
                model_id=effective_model,
                context=context,
                input_text=input_text,
                initial_context=initial_context,
            )
            if retry_output is not None:
                return retry_output
            return self._ai_required_contract(
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
                    "Error closing extraction pipeline for key=%s: %s",
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
        source_type: str,
        bind_tools: bool = True,
    ) -> Flujo[str, ExtractionContract, ExtractionContext]:
        cache_key = (source_type, model_id, bind_tools)
        if cache_key in self._pipelines:
            return self._pipelines[cache_key]

        tools: list[object] | None = None
        if bind_tools and self._dictionary_service is not None:
            try:
                tools = list(
                    build_extraction_validation_tools(
                        dictionary_service=self._dictionary_service,
                    ),
                )
            except (LookupError, PermissionError) as exc:
                logger.warning(
                    "Extraction tools unavailable; running without tool binding: %s",
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
            tools=tools if bind_tools else None,
        )
        self._pipelines[cache_key] = pipeline
        self._lifecycle_manager.register_runner(pipeline)
        return pipeline

    async def _retry_without_tools(
        self,
        *,
        source_type: str,
        model_id: str,
        context: ExtractionContext,
        input_text: str,
        initial_context: JSONObject,
    ) -> ExtractionContract | None:
        retry_pipeline = self._get_or_create_pipeline(
            model_id,
            source_type=source_type,
            bind_tools=False,
        )
        retry_initial_context = self._build_retry_initial_context(initial_context)
        try:
            return await self._execute_pipeline(
                retry_pipeline,
                input_text=input_text,
                initial_context=retry_initial_context,
                fallback_context=context,
            )
        except (PausedException, PipelineAbortSignal):
            raise
        except _PIPELINE_EXCEPTIONS as exc:
            logger.warning(
                "Extraction no-tools retry failed for document=%s: %s",
                context.document_id,
                exc,
            )
            return None

    @staticmethod
    def _build_retry_initial_context(initial_context: JSONObject) -> JSONObject:
        return {
            str(key): to_json_value(value)
            for key, value in initial_context.items()
            if key != "run_id"
        }

    @staticmethod
    def _build_input_text(context: ExtractionContext) -> str:
        serialized_raw_record = json.dumps(context.raw_record, default=str)
        serialized_entities = json.dumps(
            [entity.model_dump(mode="json") for entity in context.recognized_entities],
            default=str,
        )
        serialized_observations = json.dumps(
            [
                observation.model_dump(mode="json")
                for observation in context.recognized_observations
            ],
            default=str,
        )
        return (
            f"SOURCE TYPE: {context.source_type}\n"
            f"DOCUMENT ID: {context.document_id}\n"
            f"RESEARCH SPACE ID: {context.research_space_id or 'none'}\n"
            f"SHADOW MODE: {context.shadow_mode}\n\n"
            f"RAW RECORD JSON:\n{serialized_raw_record}\n\n"
            f"RECOGNIZED ENTITIES:\n{serialized_entities}\n\n"
            f"RECOGNIZED OBSERVATIONS:\n{serialized_observations}"
        )

    async def _execute_pipeline(
        self,
        pipeline: Flujo[str, ExtractionContract, ExtractionContext],
        *,
        input_text: str,
        initial_context: JSONObject,
        fallback_context: ExtractionContext,
    ) -> ExtractionContract:
        final_output: ExtractionContract | None = None

        async for item in pipeline.run_async(
            input_text,
            initial_context_data=initial_context,
        ):
            if isinstance(item, StepResult):
                if isinstance(item.output, ExtractionContract):
                    final_output = item.output
            elif isinstance(item, PipelineResult):
                self._capture_run_id(item)
                candidate = self._extract_from_pipeline_result(item)
                if candidate is not None:
                    final_output = candidate

        if final_output is None:
            return self._ai_required_contract(
                fallback_context,
                reason="pipeline_returned_no_contract",
            )
        return final_output

    def _ai_required_contract(
        self,
        context: ExtractionContext,
        *,
        reason: str,
    ) -> ExtractionContract:
        return ExtractionContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=(
                "AI-only extraction is required for PubMed/ClinVar pipeline stages; "
                f"no deterministic fallback was executed ({reason})."
            ),
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"source_document:{context.document_id}",
                    excerpt=f"AI extraction unavailable: {reason}",
                    relevance=1.0,
                ),
            ],
            source_type=context.source_type,
            document_id=context.document_id,
            observations=[],
            relations=[],
            rejected_facts=[],
            pipeline_payloads=[],
            shadow_mode=context.shadow_mode,
            agent_run_id=self._last_run_id,
        )

    def _extract_from_pipeline_result(
        self,
        result: PipelineResult[ExtractionContext],
    ) -> ExtractionContract | None:
        step_history = getattr(result, "step_history", None)
        if not isinstance(step_history, list):
            return None
        for step_result in reversed(step_history):
            if isinstance(
                step_result,
                StepResult,
            ) and isinstance(step_result.output, ExtractionContract):
                return step_result.output
        return None

    def _capture_run_id(self, result: PipelineResult[ExtractionContext]) -> None:
        context = result.final_pipeline_context
        run_id = getattr(context, "run_id", None)
        if isinstance(run_id, str) and run_id.strip():
            self._last_run_id = run_id.strip()

    @staticmethod
    def _unsupported_source_contract(context: ExtractionContext) -> ExtractionContract:
        return ExtractionContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=f"Source type '{context.source_type}' is not supported",
            evidence=[],
            source_type=context.source_type,
            document_id=context.document_id,
            shadow_mode=context.shadow_mode,
        )


__all__ = ["FlujoExtractionAdapter"]
