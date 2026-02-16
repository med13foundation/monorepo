"""Flujo-based adapter for entity-recognition agent operations."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Literal

from flujo.domain.models import PipelineResult, StepResult
from flujo.exceptions import FlujoError, PausedException, PipelineAbortSignal

from src.domain.agents.contracts import (
    EntityRecognitionContract,
    EvidenceItem,
    RecognizedEntityCandidate,
    RecognizedObservationCandidate,
)
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

if TYPE_CHECKING:
    EntityRecognitionPipelineFactory = Callable[
        ...,
        Flujo[str, EntityRecognitionContract, EntityRecognitionContext],
    ]

_PIPELINE_FACTORIES: dict[str, EntityRecognitionPipelineFactory] = {
    "clinvar": create_clinvar_entity_recognition_pipeline,
    "pubmed": create_pubmed_entity_recognition_pipeline,
}

_HEURISTIC_FIELD_MAP: dict[str, dict[str, tuple[str, ...]]] = {
    "clinvar": {
        "variant": ("clinvar_id", "variation_id", "accession", "hgvs"),
        "gene": ("gene_symbol", "gene", "hgnc_id"),
        "phenotype": ("condition", "disease_name", "phenotype"),
        "publication": ("title", "pubmed_id", "doi"),
    },
    "pubmed": {
        "variant": ("hgvs", "variant"),
        "gene": ("gene_symbol", "gene", "hgnc_id"),
        "phenotype": ("condition", "disease", "phenotype"),
        "publication": ("title", "pubmed_id", "pmid", "doi"),
    },
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
            return self._heuristic_contract(context, decision="fallback")

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
            primary_output = await self._execute_pipeline(
                pipeline,
                input_text=input_text,
                initial_context=initial_context,
                fallback_context=context,
            )
        except (PausedException, PipelineAbortSignal):
            raise
        except FlujoError as exc:
            logger.warning(
                "Entity-recognition pipeline failed for document=%s: %s",
                context.document_id,
                exc,
            )
            primary_output = self._heuristic_contract(context, decision="fallback")

        if source_type == "pubmed" and self._is_heuristic_contract(primary_output):
            retry_output = await self._retry_without_tools(
                model_id=effective_model,
                context=context,
                input_text=input_text,
                initial_context=initial_context,
            )
            if retry_output is not None:
                return self._select_preferred_contract(primary_output, retry_output)
        return primary_output

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
        policy_key: str,
        context: EntityRecognitionContext,
        bind_tools: bool = True,
    ) -> Flujo[str, EntityRecognitionContract, EntityRecognitionContext]:
        cache_key = (source_type, model_id, policy_key, bind_tools)
        if cache_key in self._pipelines:
            return self._pipelines[cache_key]

        tools: list[object] | None = None
        if bind_tools and self._dictionary_service is not None:
            try:
                tools = list(
                    build_entity_recognition_dictionary_tools(
                        dictionary_service=self._dictionary_service,
                        created_by=self._agent_created_by,
                        research_space_settings=context.research_space_settings,
                    ),
                )
            except (LookupError, PermissionError) as exc:
                logger.warning(
                    "Dictionary tools unavailable for policy=%s; "
                    "falling back to no-tool agent run: %s",
                    policy_key,
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
        try:
            return await self._execute_pipeline(
                retry_pipeline,
                input_text=input_text,
                initial_context=initial_context,
                fallback_context=context,
            )
        except (PausedException, PipelineAbortSignal):
            raise
        except FlujoError as exc:
            logger.warning(
                "Entity-recognition no-tools retry failed for document=%s: %s",
                context.document_id,
                exc,
            )
            return None

    @staticmethod
    def _is_heuristic_contract(contract: EntityRecognitionContract) -> bool:
        rationale = contract.rationale.strip().lower()
        return rationale.startswith("heuristic ")

    @staticmethod
    def _entity_signal_score(contract: EntityRecognitionContract) -> tuple[int, float]:
        entity_count = len(contract.recognized_entities)
        observation_count = len(contract.recognized_observations)
        return (entity_count * 3 + observation_count, contract.confidence_score)

    @classmethod
    def _select_preferred_contract(
        cls,
        primary_output: EntityRecognitionContract,
        retry_output: EntityRecognitionContract,
    ) -> EntityRecognitionContract:
        primary_is_heuristic = cls._is_heuristic_contract(primary_output)
        retry_is_heuristic = cls._is_heuristic_contract(retry_output)
        if primary_is_heuristic and not retry_is_heuristic:
            return retry_output
        if retry_is_heuristic and not primary_is_heuristic:
            return primary_output
        if cls._entity_signal_score(retry_output) > cls._entity_signal_score(
            primary_output,
        ):
            return retry_output
        return primary_output

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
                if isinstance(item.output, EntityRecognitionContract):
                    final_output = item.output
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
        result: PipelineResult[EntityRecognitionContext],
    ) -> EntityRecognitionContract | None:
        step_history = getattr(result, "step_history", None)
        if not isinstance(step_history, list):
            return None
        for step_result in reversed(step_history):
            if isinstance(
                step_result,
                StepResult,
            ) and isinstance(step_result.output, EntityRecognitionContract):
                return step_result.output
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
    def _extract_scalar(raw_record: JSONObject, keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = raw_record.get(key)
            if isinstance(value, str):
                normalized = value.strip()
                if normalized:
                    return normalized
            if isinstance(value, int | float):
                return str(value)
        return None

    def _heuristic_contract(
        self,
        context: EntityRecognitionContext,
        *,
        decision: Literal["generated", "fallback", "escalate"],
    ) -> EntityRecognitionContract:
        source_type = context.source_type.strip().lower()
        raw_record = dict(context.raw_record)
        field_candidates = [
            str(key)
            for key, value in raw_record.items()
            if isinstance(value, str | int | float | bool)
        ]

        entities: list[RecognizedEntityCandidate] = []
        variant_label = self._extract_scalar(
            raw_record,
            self._field_keys_for_source(source_type, "variant"),
        )
        if variant_label:
            entities.append(
                RecognizedEntityCandidate(
                    entity_type="VARIANT",
                    display_label=variant_label,
                    identifiers={"variant_id": variant_label},
                    confidence=0.8,
                ),
            )

        gene_label = self._extract_scalar(
            raw_record,
            self._field_keys_for_source(source_type, "gene"),
        )
        if gene_label:
            entities.append(
                RecognizedEntityCandidate(
                    entity_type="GENE",
                    display_label=gene_label,
                    identifiers={"gene_symbol": gene_label},
                    confidence=0.75,
                ),
            )

        phenotype_label = self._extract_scalar(
            raw_record,
            self._field_keys_for_source(source_type, "phenotype"),
        )
        if phenotype_label:
            entities.append(
                RecognizedEntityCandidate(
                    entity_type="PHENOTYPE",
                    display_label=phenotype_label,
                    identifiers={"label": phenotype_label},
                    confidence=0.65,
                ),
            )

        publication_label = self._extract_scalar(
            raw_record,
            self._field_keys_for_source(source_type, "publication"),
        )
        if publication_label:
            entities.append(
                RecognizedEntityCandidate(
                    entity_type="PUBLICATION",
                    display_label=publication_label,
                    identifiers={"publication_ref": publication_label},
                    confidence=0.7,
                ),
            )

        observations: list[RecognizedObservationCandidate] = []
        for field_name in field_candidates:
            value = raw_record.get(field_name)
            if value is None:
                continue
            json_value = to_json_value(value)
            observations.append(
                RecognizedObservationCandidate(
                    field_name=field_name,
                    value=json_value,
                    confidence=0.6,
                ),
            )

        pipeline_payload: JSONObject = {
            str(key): to_json_value(value) for key, value in raw_record.items()
        }
        evidence = [
            EvidenceItem(
                source_type="db",
                locator=f"source_document:{context.document_id}",
                excerpt="Deterministic fallback parsed raw_record fields",
                relevance=0.7 if entities else 0.4,
            ),
        ]
        resolved_decision: Literal["generated", "fallback", "escalate"] = (
            "generated" if entities else decision
        )
        confidence = 0.78 if entities else 0.4

        return EntityRecognitionContract(
            decision=resolved_decision,
            confidence_score=confidence,
            rationale=f"Heuristic {source_type} parsing fallback executed",
            evidence=evidence,
            source_type=context.source_type,
            document_id=context.document_id,
            primary_entity_type=(
                entities[0].entity_type
                if entities
                else ("PUBLICATION" if source_type == "pubmed" else "VARIANT")
            ),
            field_candidates=field_candidates,
            recognized_entities=entities,
            recognized_observations=observations,
            pipeline_payloads=[pipeline_payload] if pipeline_payload else [],
            shadow_mode=context.shadow_mode,
            agent_run_id=self._last_run_id,
        )

    @staticmethod
    def _field_keys_for_source(source_type: str, field: str) -> tuple[str, ...]:
        source_mapping = _HEURISTIC_FIELD_MAP.get(
            source_type,
            _HEURISTIC_FIELD_MAP["clinvar"],
        )
        return source_mapping.get(field, ())

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
