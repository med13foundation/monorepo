"""Flujo-based adapter for entity-recognition agent operations."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

from flujo.domain.agent_result import FlujoAgentResult
from flujo.domain.models import PipelineResult, StepResult
from flujo.exceptions import FlujoError, PausedException, PipelineAbortSignal

from src.domain.agents.contracts import EntityRecognitionContract, EvidenceItem
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.entity_recognition_port import EntityRecognitionPort
from src.infrastructure.llm.config import GovernanceConfig, get_model_registry
from src.infrastructure.llm.pipelines.entity_recognition_pipelines import (
    create_clinvar_entity_recognition_pipeline,
    create_pubmed_entity_recognition_pipeline,
)
from src.infrastructure.llm.skills import build_entity_recognition_dictionary_tools
from src.infrastructure.llm.state import get_lifecycle_manager, get_state_backend
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable

    from flujo import Flujo

    from src.domain.agents.contexts.entity_recognition_context import (
        EntityRecognitionContext,
    )
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)

_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})
_SUPPORTED_SOURCE_TYPES = frozenset({"clinvar", "pubmed"})
_DEFAULT_DICTIONARY_POLICY_KEY = "DEFAULT"
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
    EntityRecognitionPipelineFactory = Callable[
        ...,
        Flujo[str, EntityRecognitionContract, EntityRecognitionContext],
    ]

_PIPELINE_FACTORIES: dict[str, EntityRecognitionPipelineFactory] = {
    "clinvar": create_clinvar_entity_recognition_pipeline,
    "pubmed": create_pubmed_entity_recognition_pipeline,
}


class FlujoEntityRecognitionAdapter(EntityRecognitionPort):
    """Adapter that executes entity-recognition workflows through Flujo."""

    def __init__(
        self,
        model: str | None = None,
        *,
        use_governance: bool = True,
        dictionary_service: DictionaryPort | None = None,
        agent_created_by: str = "agent:entity_recognition",
    ) -> None:
        self._default_model = model
        self._use_governance = use_governance
        self._dictionary_service = dictionary_service
        normalized_created_by = agent_created_by.strip()
        self._agent_created_by = normalized_created_by or "agent:entity_recognition"
        self._state_backend = get_state_backend()
        self._governance = GovernanceConfig.from_environment()
        self._registry = get_model_registry()
        self._lifecycle_manager = get_lifecycle_manager()
        self._pipelines: dict[
            tuple[str, str, str, bool],
            Flujo[str, EntityRecognitionContract, EntityRecognitionContext],
        ] = {}
        self._last_run_id: str | None = None

    async def recognize(
        self,
        context: EntityRecognitionContext,
        *,
        model_id: str | None = None,
    ) -> EntityRecognitionContract:
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
        policy_key = self._resolve_dictionary_policy_key(context)
        pipeline = self._get_or_create_pipeline(
            effective_model,
            source_type=source_type,
            policy_key=policy_key,
            context=context,
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
                "Entity-recognition pipeline failed for document=%s: %s",
                context.document_id,
                exc,
            )
            retry_output = await self._retry_without_tools(
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
        for model_id, pipeline in self._pipelines.items():
            try:
                if hasattr(pipeline, "aclose"):
                    await pipeline.aclose()
                self._lifecycle_manager.unregister_runner(pipeline)
            except (RuntimeError, OSError, ConnectionError) as exc:
                logger.warning(
                    "Error closing entity-recognition pipeline for model=%s: %s",
                    model_id,
                    exc,
                )
        self._pipelines.clear()

    def get_last_run_id(self) -> str | None:
        """Return the last Flujo run id if available."""
        return self._last_run_id

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
        *,
        source_type: str,
        policy_key: str,
        context: EntityRecognitionContext,
        bind_tools: bool = True,
    ) -> Flujo[str, EntityRecognitionContract, EntityRecognitionContext]:
        cache_key = (source_type, model_id, policy_key, bind_tools)
        if cache_key in self._pipelines:
            return self._pipelines[cache_key]

        discovery_tools: list[object] | None = None
        policy_tools: list[object] | None = None
        if bind_tools and self._dictionary_service is not None:
            try:
                discovery_tools = list(
                    build_entity_recognition_dictionary_tools(
                        dictionary_service=self._dictionary_service,
                        created_by=self._agent_created_by,
                        research_space_settings=context.research_space_settings,
                        include_mutation_tools=False,
                    ),
                )
                policy_tools = list(
                    build_entity_recognition_dictionary_tools(
                        dictionary_service=self._dictionary_service,
                        created_by=self._agent_created_by,
                        research_space_settings=context.research_space_settings,
                        include_mutation_tools=True,
                    ),
                )
            except (LookupError, PermissionError) as exc:
                logger.warning(
                    "Dictionary tools unavailable for policy=%s; "
                    "falling back to no-tool agent run: %s",
                    policy_key,
                    exc,
                )
                discovery_tools = None
                policy_tools = None

        pipeline_factory = _PIPELINE_FACTORIES.get(source_type)
        if pipeline_factory is None:
            msg = f"Unsupported source type for pipeline dispatch: {source_type}"
            raise ValueError(msg)

        pipeline = pipeline_factory(
            state_backend=self._state_backend,
            model=model_id,
            use_governance=self._use_governance,
            usage_limits=self._governance.usage_limits,
            discovery_tools=discovery_tools if bind_tools else None,
            policy_tools=policy_tools if bind_tools else None,
        )
        self._pipelines[cache_key] = pipeline
        self._lifecycle_manager.register_runner(pipeline)
        return pipeline

    async def _retry_without_tools(
        self,
        *,
        model_id: str,
        context: EntityRecognitionContext,
        input_text: str,
        initial_context: JSONObject,
    ) -> EntityRecognitionContract | None:
        source_type = context.source_type.strip().lower()
        policy_key = self._resolve_dictionary_policy_key(context)
        retry_pipeline = self._get_or_create_pipeline(
            model_id,
            source_type=source_type,
            policy_key=policy_key,
            context=context,
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
                "Entity-recognition no-tools retry failed for document=%s: %s",
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
    def _resolve_dictionary_policy_key(context: EntityRecognitionContext) -> str:
        raw_policy = context.research_space_settings.get(
            "dictionary_agent_creation_policy",
        )
        if not isinstance(raw_policy, str):
            return _DEFAULT_DICTIONARY_POLICY_KEY
        normalized = raw_policy.strip().upper()
        return normalized or _DEFAULT_DICTIONARY_POLICY_KEY

    @staticmethod
    def _build_input_text(context: EntityRecognitionContext) -> str:
        serialized_payload = json.dumps(context.raw_record, default=str)
        return (
            f"SOURCE TYPE: {context.source_type}\n"
            f"DOCUMENT ID: {context.document_id}\n"
            f"RESEARCH SPACE ID: {context.research_space_id or 'none'}\n"
            f"SHADOW MODE: {context.shadow_mode}\n\n"
            f"RAW RECORD JSON:\n{serialized_payload}"
        )

    async def _execute_pipeline(
        self,
        pipeline: Flujo[str, EntityRecognitionContract, EntityRecognitionContext],
        *,
        input_text: str,
        initial_context: JSONObject,
        fallback_context: EntityRecognitionContext,
    ) -> EntityRecognitionContract:
        final_output: EntityRecognitionContract | None = None

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
            return self._ai_required_contract(
                fallback_context,
                reason="pipeline_returned_no_contract",
            )
        return final_output

    def _ai_required_contract(
        self,
        context: EntityRecognitionContext,
        *,
        reason: str,
    ) -> EntityRecognitionContract:
        return EntityRecognitionContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=(
                "AI-only entity recognition is required; "
                f"no deterministic fallback was executed ({reason})."
            ),
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"source_document:{context.document_id}",
                    excerpt=f"AI entity recognition unavailable: {reason}",
                    relevance=1.0,
                ),
            ],
            source_type=context.source_type,
            document_id=context.document_id,
            primary_entity_type="VARIANT",
            field_candidates=[],
            recognized_entities=[],
            recognized_observations=[],
            pipeline_payloads=[],
            created_definitions=[],
            created_synonyms=[],
            created_entity_types=[],
            created_relation_types=[],
            created_relation_constraints=[],
            shadow_mode=context.shadow_mode,
            agent_run_id=self._last_run_id,
        )

    @staticmethod
    def _extract_contract(output: object) -> EntityRecognitionContract | None:
        if isinstance(output, EntityRecognitionContract):
            return output
        if isinstance(output, FlujoAgentResult):
            wrapped_output = output.output
            if isinstance(wrapped_output, EntityRecognitionContract):
                return wrapped_output
        return None

    def _extract_from_pipeline_result(
        self,
        result: PipelineResult[EntityRecognitionContext],
    ) -> EntityRecognitionContract | None:
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
        result: PipelineResult[EntityRecognitionContext],
    ) -> None:
        context = result.final_pipeline_context
        run_id = getattr(context, "run_id", None)
        if isinstance(run_id, str) and run_id.strip():
            self._last_run_id = run_id.strip()

    @staticmethod
    def _unsupported_source_contract(
        context: EntityRecognitionContext,
    ) -> EntityRecognitionContract:
        return EntityRecognitionContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=f"Source type '{context.source_type}' is not supported",
            evidence=[],
            source_type=context.source_type,
            document_id=context.document_id,
            primary_entity_type="VARIANT",
            shadow_mode=context.shadow_mode,
        )


__all__ = ["FlujoEntityRecognitionAdapter"]
