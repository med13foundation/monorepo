"""Flujo-based adapter for Tier-2 content-enrichment workflows."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

from flujo.domain.models import PipelineResult, StepResult
from flujo.exceptions import FlujoError, PausedException, PipelineAbortSignal

from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.content_enrichment import ContentEnrichmentContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.content_enrichment_port import ContentEnrichmentPort
from src.infrastructure.llm.config.governance import GovernanceConfig
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.pipelines.content_enrichment_pipelines import (
    create_content_enrichment_pipeline,
)
from src.infrastructure.llm.skills.registry import build_content_enrichment_tools
from src.infrastructure.llm.state import get_lifecycle_manager, get_state_backend
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from flujo import Flujo

    from src.domain.agents.contexts.content_enrichment_context import (
        ContentEnrichmentContext,
    )
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)

_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})
_STRUCTURED_SOURCE_TYPES = frozenset({"clinvar", "api", "database", "file_upload"})


class FlujoContentEnrichmentAdapter(ContentEnrichmentPort):
    """Adapter that executes content-enrichment workflows through Flujo."""

    def __init__(
        self,
        model: str | None = None,
    ) -> None:
        self._default_model = model
        self._state_backend = get_state_backend()
        self._governance = GovernanceConfig.from_environment()
        self._registry = get_model_registry()
        self._lifecycle_manager = get_lifecycle_manager()
        self._pipelines: dict[
            str,
            Flujo[str, ContentEnrichmentContract, ContentEnrichmentContext],
        ] = {}
        self._last_run_id: str | None = None

    async def enrich(
        self,
        context: ContentEnrichmentContext,
        *,
        model_id: str | None = None,
    ) -> ContentEnrichmentContract:
        self._last_run_id = None
        source_type = context.source_type.strip().lower()
        if source_type in _STRUCTURED_SOURCE_TYPES:
            return self._pass_through_contract(context, warning=None)

        if not self._has_openai_key():
            return self._heuristic_contract(
                context,
                warning="Content-enrichment agent API key is not configured.",
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
                "Content-enrichment pipeline failed for document=%s: %s",
                context.document_id,
                exc,
            )
            return self._heuristic_contract(
                context,
                warning="Content-enrichment agent execution failed.",
            )

    async def close(self) -> None:
        for cache_key, pipeline in self._pipelines.items():
            try:
                if hasattr(pipeline, "aclose"):
                    await pipeline.aclose()
                self._lifecycle_manager.unregister_runner(pipeline)
            except (RuntimeError, OSError, ConnectionError) as exc:
                logger.warning(
                    "Error closing content-enrichment pipeline for key=%s: %s",
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
    ) -> Flujo[str, ContentEnrichmentContract, ContentEnrichmentContext]:
        if model_id in self._pipelines:
            return self._pipelines[model_id]
        pipeline = create_content_enrichment_pipeline(
            state_backend=self._state_backend,
            model=model_id,
            usage_limits=self._governance.usage_limits,
            tools=list(build_content_enrichment_tools()),
        )
        self._pipelines[model_id] = pipeline
        self._lifecycle_manager.register_runner(pipeline)
        return pipeline

    @staticmethod
    def _build_input_text(context: ContentEnrichmentContext) -> str:
        metadata_payload = json.dumps(context.existing_metadata, default=str)
        return (
            f"DOCUMENT ID: {context.document_id}\n"
            f"SOURCE TYPE: {context.source_type}\n"
            f"EXTERNAL RECORD ID: {context.external_record_id}\n"
            f"RESEARCH SPACE ID: {context.research_space_id or 'none'}\n"
            f"RAW STORAGE KEY: {context.raw_storage_key or 'none'}\n\n"
            f"METADATA JSON:\n{metadata_payload}"
        )

    async def _execute_pipeline(
        self,
        pipeline: Flujo[str, ContentEnrichmentContract, ContentEnrichmentContext],
        *,
        input_text: str,
        initial_context: JSONObject,
        fallback_context: ContentEnrichmentContext,
    ) -> ContentEnrichmentContract:
        final_output: ContentEnrichmentContract | None = None
        async for item in pipeline.run_async(
            input_text,
            initial_context_data=initial_context,
        ):
            if isinstance(item, StepResult):
                if isinstance(item.output, ContentEnrichmentContract):
                    final_output = item.output
            elif isinstance(item, PipelineResult):
                self._capture_run_id(item)
                candidate = self._extract_from_pipeline_result(item)
                if candidate is not None:
                    final_output = candidate

        if final_output is None:
            return self._heuristic_contract(
                fallback_context,
                warning="Content-enrichment agent returned no structured result.",
            )
        if self._last_run_id is not None and final_output.agent_run_id is None:
            final_output.agent_run_id = self._last_run_id
        return final_output

    def _extract_from_pipeline_result(
        self,
        result: PipelineResult[ContentEnrichmentContext],
    ) -> ContentEnrichmentContract | None:
        step_history = getattr(result, "step_history", None)
        if not isinstance(step_history, list):
            return None
        for step_result in reversed(step_history):
            if isinstance(step_result, StepResult) and isinstance(
                step_result.output,
                ContentEnrichmentContract,
            ):
                return step_result.output
        return None

    def _capture_run_id(
        self,
        result: PipelineResult[ContentEnrichmentContext],
    ) -> None:
        context = result.final_pipeline_context
        run_id = getattr(context, "run_id", None)
        if isinstance(run_id, str) and run_id.strip():
            self._last_run_id = run_id.strip()

    def _heuristic_contract(
        self,
        context: ContentEnrichmentContext,
        *,
        warning: str,
    ) -> ContentEnrichmentContract:
        source_type = context.source_type.strip().lower()
        if source_type in _STRUCTURED_SOURCE_TYPES:
            return self._pass_through_contract(context, warning=warning)

        extracted_text = self._extract_text_from_metadata(context.existing_metadata)
        if extracted_text is None:
            return ContentEnrichmentContract(
                decision="skipped",
                confidence_score=0.4,
                rationale="No enrichment-compatible content was available.",
                evidence=[
                    EvidenceItem(
                        source_type="note",
                        locator=f"document:{context.document_id}",
                        excerpt="No abstract/title/full_text found in metadata payload.",
                        relevance=0.4,
                    ),
                ],
                document_id=context.document_id,
                source_type=context.source_type,
                acquisition_method="skipped",
                content_format="text",
                content_length_chars=0,
                warning=warning or "No enrichment content available.",
                agent_run_id=self._last_run_id,
            )

        return ContentEnrichmentContract(
            decision="enriched",
            confidence_score=0.65,
            rationale="Heuristic enrichment used existing metadata text.",
            evidence=[
                EvidenceItem(
                    source_type="db",
                    locator=f"document:{context.document_id}",
                    excerpt="Used metadata title/abstract/full_text as enrichment payload.",
                    relevance=0.65,
                ),
            ],
            document_id=context.document_id,
            source_type=context.source_type,
            acquisition_method="pass_through",
            content_format="text",
            content_length_chars=len(extracted_text),
            content_text=extracted_text,
            warning=warning,
            agent_run_id=self._last_run_id,
        )

    def _pass_through_contract(
        self,
        context: ContentEnrichmentContext,
        *,
        warning: str | None,
    ) -> ContentEnrichmentContract:
        payload = self._extract_structured_payload(context.existing_metadata)
        serialized = json.dumps(payload, default=str)
        return ContentEnrichmentContract(
            decision="enriched",
            confidence_score=0.95,
            rationale="Structured source type uses deterministic pass-through enrichment.",
            evidence=[
                EvidenceItem(
                    source_type="db",
                    locator=f"document:{context.document_id}",
                    excerpt="Structured source data was passed through unchanged.",
                    relevance=0.95,
                ),
            ],
            document_id=context.document_id,
            source_type=context.source_type,
            acquisition_method="pass_through",
            content_format="structured_json",
            content_length_chars=len(serialized),
            content_payload=payload,
            warning=warning,
            agent_run_id=self._last_run_id,
        )

    @staticmethod
    def _extract_structured_payload(metadata: JSONObject) -> JSONObject:
        raw_record = metadata.get("raw_record")
        if isinstance(raw_record, dict):
            return {str(key): to_json_value(value) for key, value in raw_record.items()}
        return {str(key): to_json_value(value) for key, value in metadata.items()}

    @staticmethod
    def _extract_text_from_metadata(metadata: JSONObject) -> str | None:
        raw_record = metadata.get("raw_record")
        candidate_sources: list[JSONObject] = []
        if isinstance(raw_record, dict):
            candidate_sources.append(raw_record)
        candidate_sources.append(metadata)

        for source in candidate_sources:
            for key in ("full_text", "abstract", "title"):
                value = source.get(key)
                if isinstance(value, str):
                    normalized = value.strip()
                    if normalized:
                        return normalized
        return None


__all__ = ["FlujoContentEnrichmentAdapter"]
