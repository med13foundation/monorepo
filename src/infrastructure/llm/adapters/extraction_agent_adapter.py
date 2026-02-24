"""Flujo-based adapter for extraction agent operations."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from flujo.domain.agent_result import FlujoAgentResult
from flujo.domain.models import PipelineResult, StepResult
from flujo.exceptions import FlujoError, PausedException, PipelineAbortSignal

from src.domain.agents.contracts import EvidenceItem, ExtractionContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.extraction_agent_port import ExtractionAgentPort
from src.infrastructure.llm.config import GovernanceConfig, get_model_registry
from src.infrastructure.llm.config.governance import UsageLimits
from src.infrastructure.llm.pipelines.extraction_pipelines import (
    create_clinvar_extraction_pipeline,
    create_pubmed_extraction_pipeline,
)
from src.infrastructure.llm.skills import build_extraction_validation_tools
from src.infrastructure.llm.state import get_lifecycle_manager, get_state_backend
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Literal

    from flujo import Flujo

    from src.domain.agents.contexts.extraction_context import ExtractionContext
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.type_definitions.common import JSONObject, JSONValue, ResearchSpaceSettings

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
_TEMPORAL_FIELD_NAMES = frozenset(
    {
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
        "processed_at",
        "published_at",
        "observed_at",
        "fetched_at",
    },
)
_MAX_CONTEXT_ENTITY_CANDIDATES = 12
_MAX_CONTEXT_OBSERVATION_CANDIDATES = 12
_DEFAULT_EXTRACTION_USAGE_MAX_TOKENS = 65536
_ENV_EXTRACTION_USAGE_MAX_TOKENS = "MED13_EXTRACTION_USAGE_MAX_TOKENS"
_ESCAPED_NULL_SEQUENCE_PATTERN = re.compile(r"\\+(?:u0000|x00)", re.IGNORECASE)

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
        self._pipeline_usage_limits = self._resolve_pipeline_usage_limits(
            self._governance.usage_limits,
        )
        self._registry = get_model_registry()
        self._lifecycle_manager = get_lifecycle_manager()
        self._pipelines: dict[
            tuple[str, str, bool, str],
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
        relation_governance_mode = self._resolve_relation_governance_mode(
            context.research_space_settings,
        )
        pipeline = self._get_or_create_pipeline(
            effective_model,
            source_type=source_type,
            bind_tools=True,
            relation_governance_mode=relation_governance_mode,
        )
        input_text = self._build_input_text(context)
        initial_context = self._normalize_temporal_context(
            context.model_dump(mode="json"),
        )

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
                "Extraction pipeline failed for document=%s source_type=%s model=%s: %s",
                context.document_id,
                source_type,
                effective_model,
                exc,
                exc_info=True,
            )
            if self._is_datetime_offset_mismatch_error(exc):
                logger.warning(
                    "Detected timezone mismatch in extraction pipeline; "
                    "resetting pipeline cache for source=%s model=%s",
                    source_type,
                    effective_model,
                )
                self._drop_cached_pipelines(
                    source_type=source_type,
                    model_id=effective_model,
                )
                initial_context = self._normalize_temporal_context(initial_context)
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
        bind_tools: bool = True,
        relation_governance_mode: str = "HUMAN_IN_LOOP",
    ) -> Flujo[str, ExtractionContract, ExtractionContext]:
        normalized_relation_governance_mode: Literal["HUMAN_IN_LOOP", "FULL_AUTO"]
        if relation_governance_mode.strip().upper() == "FULL_AUTO":
            normalized_relation_governance_mode = "FULL_AUTO"
        else:
            normalized_relation_governance_mode = "HUMAN_IN_LOOP"
        cache_key = (
            source_type,
            model_id,
            bind_tools,
            normalized_relation_governance_mode,
        )
        if cache_key in self._pipelines:
            return self._pipelines[cache_key]

        tools: list[object] | None = None
        if bind_tools and self._dictionary_service is not None:
            try:
                tool_settings: ResearchSpaceSettings = {
                    "relation_governance_mode": normalized_relation_governance_mode,
                }
                tools = list(
                    build_extraction_validation_tools(
                        dictionary_service=self._dictionary_service,
                        research_space_settings=tool_settings,
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
            usage_limits=self._pipeline_usage_limits,
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
        relation_governance_mode = self._resolve_relation_governance_mode(
            context.research_space_settings,
        )
        retry_pipeline = self._get_or_create_pipeline(
            model_id,
            source_type=source_type,
            bind_tools=False,
            relation_governance_mode=relation_governance_mode,
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
                "Extraction no-tools retry failed for document=%s source_type=%s model=%s: %s",
                context.document_id,
                source_type,
                model_id,
                exc,
                exc_info=True,
            )
            return None

    def _drop_cached_pipelines(
        self,
        *,
        source_type: str,
        model_id: str,
    ) -> None:
        keys_to_remove = [
            key
            for key in self._pipelines
            if key[0] == source_type and key[1] == model_id
        ]
        for key in keys_to_remove:
            pipeline = self._pipelines.pop(key, None)
            if pipeline is None:
                continue
            try:
                self._lifecycle_manager.unregister_runner(pipeline)
            except Exception as exc:  # noqa: BLE001 - defensive cache cleanup
                logger.debug(
                    "Failed to unregister cached extraction runner for key=%s: %s",
                    key,
                    exc,
                    exc_info=True,
                )
                continue

    @staticmethod
    def _resolve_relation_governance_mode(
        settings: ResearchSpaceSettings,
    ) -> str:
        raw_mode = settings.get("relation_governance_mode")
        if isinstance(raw_mode, str) and raw_mode.strip().upper() == "FULL_AUTO":
            return "FULL_AUTO"
        return "HUMAN_IN_LOOP"

    @classmethod
    def _build_retry_initial_context(cls, initial_context: JSONObject) -> JSONObject:
        retry_context = {
            str(key): to_json_value(value)
            for key, value in initial_context.items()
            if key != "run_id"
        }
        return cls._normalize_temporal_context(retry_context)

    @classmethod
    def _resolve_pipeline_usage_limits(cls, base_limits: UsageLimits) -> UsageLimits:
        env_override = cls._read_positive_int_from_env(
            _ENV_EXTRACTION_USAGE_MAX_TOKENS,
        )
        base_max_tokens = (
            base_limits.max_tokens
            if isinstance(base_limits.max_tokens, int) and base_limits.max_tokens > 0
            else None
        )
        minimum_tokens = (
            env_override
            if env_override is not None
            else _DEFAULT_EXTRACTION_USAGE_MAX_TOKENS
        )
        resolved_max_tokens = minimum_tokens
        if base_max_tokens is not None and base_max_tokens > resolved_max_tokens:
            resolved_max_tokens = base_max_tokens
        return UsageLimits(
            total_cost_usd=base_limits.total_cost_usd,
            max_turns=base_limits.max_turns,
            max_tokens=resolved_max_tokens,
        )

    @staticmethod
    def _read_positive_int_from_env(name: str) -> int | None:
        raw_value = os.getenv(name)
        if raw_value is None:
            return None
        normalized = raw_value.strip()
        if not normalized:
            return None
        if not normalized.isdigit():
            return None
        parsed = int(normalized)
        return parsed if parsed > 0 else None

    def _build_input_text(self, context: ExtractionContext) -> str:
        entity_candidates = sorted(
            context.recognized_entities,
            key=lambda candidate: candidate.confidence,
            reverse=True,
        )[:_MAX_CONTEXT_ENTITY_CANDIDATES]
        observation_candidates = sorted(
            context.recognized_observations,
            key=lambda candidate: candidate.confidence,
            reverse=True,
        )[:_MAX_CONTEXT_OBSERVATION_CANDIDATES]
        compact_raw_record = self._sanitize_json_value(
            self._build_compact_raw_record(context),
        )
        entity_payloads = [
            self._sanitize_json_value(entity.model_dump(mode="json"))
            for entity in entity_candidates
        ]
        observation_payloads = [
            self._sanitize_json_value(observation.model_dump(mode="json"))
            for observation in observation_candidates
        ]
        serialized_raw_record = json.dumps(
            compact_raw_record,
            default=str,
        )
        serialized_entities = json.dumps(
            entity_payloads,
            default=str,
        )
        serialized_observations = json.dumps(
            observation_payloads,
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

    @classmethod
    def _sanitize_json_value(cls, value: object) -> JSONValue:
        if isinstance(value, dict):
            return {
                str(key): cls._sanitize_json_value(item) for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls._sanitize_json_value(item) for item in value]
        if isinstance(value, str):
            return to_json_value(cls._sanitize_text_value(value))
        return to_json_value(value)

    @staticmethod
    def _sanitize_text_value(value: str) -> str:
        without_raw_null = value.replace("\x00", "")
        return _ESCAPED_NULL_SEQUENCE_PATTERN.sub("", without_raw_null)

    @staticmethod
    def _build_compact_raw_record(context: ExtractionContext) -> JSONObject:
        raw_record = context.raw_record
        source_type = context.source_type.strip().lower()
        if source_type == "pubmed":
            is_chunk_scope = raw_record.get("full_text_chunk_index") is not None
            allowed_fields: tuple[str, ...] = (
                (
                    "pubmed_id",
                    "title",
                    "doi",
                    "source",
                    "full_text",
                    "full_text_source",
                    "full_text_chunk_index",
                    "full_text_chunk_total",
                    "full_text_chunk_start_char",
                    "full_text_chunk_end_char",
                )
                if is_chunk_scope
                else (
                    "pubmed_id",
                    "title",
                    "abstract",
                    "full_text",
                    "keywords",
                    "journal",
                    "publication_date",
                    "publication_types",
                    "doi",
                    "source",
                    "full_text_source",
                    "full_text_chunk_index",
                    "full_text_chunk_total",
                    "full_text_chunk_start_char",
                    "full_text_chunk_end_char",
                )
            )
            compact: JSONObject = {}
            for field in allowed_fields:
                value = raw_record.get(field)
                if value is None:
                    continue
                compact[field] = to_json_value(value)
            if "full_text" not in compact and isinstance(raw_record.get("text"), str):
                compact["text"] = raw_record["text"]
            return compact
        if source_type == "clinvar":
            clinvar_fields: tuple[str, ...] = (
                "variation_id",
                "gene_symbol",
                "variant_name",
                "clinical_significance",
                "condition_name",
                "review_status",
                "submission_count",
                "source",
            )
            compact = {}
            for field in clinvar_fields:
                value = raw_record.get(field)
                if value is None:
                    continue
                compact[field] = to_json_value(value)
            return compact
        return {str(key): to_json_value(value) for key, value in raw_record.items()}

    @classmethod
    def _normalize_temporal_context(cls, payload: JSONObject) -> JSONObject:
        return {
            str(key): cls._normalize_temporal_value(key=str(key), value=value)
            for key, value in payload.items()
        }

    @classmethod
    def _normalize_temporal_value(cls, *, key: str, value: object) -> JSONValue:
        if isinstance(value, dict):
            return {
                str(child_key): cls._normalize_temporal_value(
                    key=str(child_key),
                    value=child_value,
                )
                for child_key, child_value in value.items()
            }
        if isinstance(value, list):
            return [
                cls._normalize_temporal_value(key=key, value=item) for item in value
            ]
        if isinstance(value, str):
            sanitized = cls._sanitize_text_value(value)
            if key in _TEMPORAL_FIELD_NAMES:
                coerced = cls._coerce_utc_iso_datetime(sanitized)
                return coerced if coerced is not None else sanitized
            return to_json_value(sanitized)
        if isinstance(value, datetime):
            coerced = cls._coerce_utc_iso_datetime(value)
            return coerced if coerced is not None else value.isoformat()
        return to_json_value(value)

    @staticmethod
    def _coerce_utc_iso_datetime(raw_value: str | datetime) -> str | None:
        parsed: datetime
        if isinstance(raw_value, datetime):
            parsed = raw_value
        else:
            normalized = raw_value.strip()
            if not normalized:
                return None
            if normalized.endswith("Z"):
                normalized = f"{normalized[:-1]}+00:00"
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        else:
            parsed = parsed.astimezone(UTC)
        return parsed.isoformat()

    @staticmethod
    def _is_datetime_offset_mismatch_error(exc: Exception) -> bool:
        return "offset-naive and offset-aware datetimes" in str(exc)

    async def _execute_pipeline(
        self,
        pipeline: Flujo[str, ExtractionContract, ExtractionContext],
        *,
        input_text: str,
        initial_context: JSONObject,
        fallback_context: ExtractionContext,
    ) -> ExtractionContract:
        final_output: ExtractionContract | None = None
        run_id = self._build_run_id(fallback_context.document_id)

        async for item in pipeline.run_async(
            input_text,
            run_id=run_id,
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
        return self._ensure_pipeline_payloads(
            contract=final_output,
            fallback_context=fallback_context,
        )

    def _ensure_pipeline_payloads(
        self,
        *,
        contract: ExtractionContract,
        fallback_context: ExtractionContext,
    ) -> ExtractionContract:
        if contract.pipeline_payloads:
            return contract
        compact_payload = self._build_compact_raw_record(fallback_context)
        if not compact_payload:
            return contract
        return contract.model_copy(
            update={
                "pipeline_payloads": [compact_payload],
            },
        )

    @staticmethod
    def _build_run_id(document_id: str) -> str:
        compact_document_id = document_id.replace("-", "")[:12]
        return f"extract_{compact_document_id}_{uuid4().hex}"

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

    @staticmethod
    def _extract_contract(output: object) -> ExtractionContract | None:
        if isinstance(output, ExtractionContract):
            return output
        if isinstance(output, FlujoAgentResult):
            wrapped_output = output.output
            if isinstance(wrapped_output, ExtractionContract):
                return wrapped_output
        return None

    def _extract_from_pipeline_result(
        self,
        result: PipelineResult[ExtractionContext],
    ) -> ExtractionContract | None:
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
