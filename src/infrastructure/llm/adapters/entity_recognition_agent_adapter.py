"""Artana-based adapter for entity-recognition agent operations."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

from src.domain.agents.contracts import EntityRecognitionContract, EvidenceItem
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.entity_recognition_port import EntityRecognitionPort
from src.infrastructure.llm.adapters._artana_step_helpers import (
    build_deterministic_run_id,
    resolve_external_record_id,
    run_single_step_with_policy,
)
from src.infrastructure.llm.adapters._openai_json_schema_model_port import (
    OpenAIJSONSchemaModelPort,
    has_configured_openai_api_key,
)
from src.infrastructure.llm.config import (
    GovernanceConfig,
    UsageLimits,
    get_model_registry,
    load_runtime_policy,
)
from src.infrastructure.llm.prompts.entity_recognition import (
    CLINVAR_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT,
    CLINVAR_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT,
    PUBMED_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT,
    PUBMED_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT,
)
from src.infrastructure.llm.state.shared_postgres_store import (
    get_shared_artana_postgres_store,
)
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from artana.store import PostgresStore

    from src.domain.agents.contexts.entity_recognition_context import (
        EntityRecognitionContext,
    )

logger = logging.getLogger(__name__)

_SUPPORTED_SOURCE_TYPES = frozenset({"clinvar", "pubmed"})
_DEFAULT_ENTITY_RECOGNITION_USAGE_MAX_TOKENS = 65536
_ENV_ENTITY_RECOGNITION_USAGE_MAX_TOKENS = "MED13_ENTITY_RECOGNITION_USAGE_MAX_TOKENS"
_MAX_ENTITY_RECOGNITION_RAW_JSON_CHARS = 20000
_MAX_ENTITY_RECOGNITION_TEXT_CHARS = 4000
_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_IMPORT_ERROR = exc

# Backward-compatible alias for adapter unit-test patch hooks.
_OpenAIChatModelPort = OpenAIJSONSchemaModelPort


class ArtanaEntityRecognitionAdapter(EntityRecognitionPort):
    """Adapter that executes entity-recognition workflows through Artana."""

    def __init__(
        self,
        model: str | None = None,
        *,
        use_governance: bool = True,
        dictionary_service: object | None = None,
        agent_created_by: str = "agent:entity_recognition",
        artana_store: PostgresStore | None = None,
    ) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import-time guard
            msg = (
                "artana-kernel is required for entity recognition execution. Install dependency "
                "'artana @ git+https://github.com/aandresalvarez/artana-kernel.git@main'."
            )
            raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

        self._default_model = model
        self._use_governance = use_governance
        self._dictionary_service = dictionary_service
        normalized_created_by = agent_created_by.strip()
        self._agent_created_by = normalized_created_by or "agent:entity_recognition"
        self._governance = GovernanceConfig.from_environment()
        self._pipeline_usage_limits = self._resolve_pipeline_usage_limits(
            self._governance.usage_limits,
        )
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()
        self._last_run_id: str | None = None
        timeout_seconds = self._resolve_timeout_seconds(model)
        self._model_port = _OpenAIChatModelPort(
            timeout_seconds=timeout_seconds,
            schema_name_fallback="entity_recognition_contract",
        )
        resolved_artana_store = artana_store or self._create_store()
        self._kernel = ArtanaKernel(
            store=resolved_artana_store,
            model_port=self._model_port,
        )
        self._client = SingleStepModelClient(kernel=self._kernel)

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
        external_record_id = resolve_external_record_id(
            source_type=source_type,
            raw_record=context.raw_record,
            fallback_document_id=context.document_id,
        )
        run_id = self._create_run_id(
            source_type=source_type,
            research_space_id=context.research_space_id,
            external_id=external_record_id,
            extraction_config_version=self._runtime_policy.extraction_config_version,
            run_attempt_token=context.created_at.isoformat(),
        )
        self._last_run_id = run_id

        try:
            usage_limits = self._pipeline_usage_limits
            budget_limit = (
                usage_limits.total_cost_usd if usage_limits.total_cost_usd else 1.0
            )
            tenant = self._create_tenant(
                tenant_id=context.research_space_id or "entity_recognition",
                budget_usd_limit=max(float(budget_limit), 0.01),
            )
            result = await run_single_step_with_policy(
                self._client,
                run_id=run_id,
                tenant=tenant,
                model=effective_model,
                prompt=self._build_prompt(source_type=source_type, context=context),
                output_schema=EntityRecognitionContract,
                step_key=f"entity.recognition.{source_type}.v1",
                replay_policy=self._runtime_policy.replay_policy,
                context_version=self._runtime_policy.to_context_version(),
            )
            output = result.output
            contract = (
                output
                if isinstance(output, EntityRecognitionContract)
                else EntityRecognitionContract.model_validate(output)
            )
            return self._normalize_contract(
                contract=contract,
                context=context,
                source_type=source_type,
                run_id=run_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Entity-recognition Artana step failed for document=%s: %s",
                context.document_id,
                exc,
            )
            return self._ai_required_contract(
                context,
                reason=f"pipeline_execution_failed:{type(exc).__name__}",
            )

    async def close(self) -> None:
        await self._model_port.aclose()

    def get_last_run_id(self) -> str | None:
        """Return the last Artana run id if available."""
        return self._last_run_id

    @staticmethod
    def _has_openai_key() -> bool:
        return has_configured_openai_api_key()

    def _resolve_timeout_seconds(self, model: str | None) -> float:
        if model:
            try:
                model_spec = self._registry.get_model(model)
                return float(model_spec.timeout_seconds)
            except (KeyError, ValueError):
                pass
        try:
            default_spec = self._registry.get_default_model(
                ModelCapability.EVIDENCE_EXTRACTION,
            )
            return float(default_spec.timeout_seconds)
        except (KeyError, ValueError):
            return 120.0

    @staticmethod
    def _create_store() -> PostgresStore:
        return get_shared_artana_postgres_store()

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

    @staticmethod
    def _create_run_id(  # noqa: PLR0913
        *,
        source_type: str,
        research_space_id: str | None = None,
        external_id: str | None = None,
        extraction_config_version: str = "v1",
        run_attempt_token: str | None = None,
        model_id: str | None = None,
        document_id: str | None = None,
    ) -> str:
        _ = model_id  # retained for backward-compatible call sites/tests
        resolved_external_id = (external_id or document_id or "").strip() or "unknown"
        normalized_attempt = (
            run_attempt_token.strip() if isinstance(run_attempt_token, str) else ""
        )
        effective_config_version = extraction_config_version
        if normalized_attempt:
            effective_config_version = (
                f"{extraction_config_version}|attempt:{normalized_attempt}"
            )
        return build_deterministic_run_id(
            prefix="entity_recognition",
            research_space_id=research_space_id,
            source_type=source_type,
            external_id=resolved_external_id,
            extraction_config_version=effective_config_version,
        )

    @staticmethod
    def _create_tenant(tenant_id: str, budget_usd_limit: float) -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=budget_usd_limit,
        )

    @staticmethod
    def _get_system_prompt(source_type: str) -> str:
        if source_type == "pubmed":
            return (
                f"{PUBMED_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT}\n\n"
                f"{PUBMED_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT}"
            )
        return (
            f"{CLINVAR_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{CLINVAR_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT}"
        )

    def _build_prompt(
        self,
        *,
        source_type: str,
        context: EntityRecognitionContext,
    ) -> str:
        return (
            f"{self._get_system_prompt(source_type)}\n\n"
            "---\n"
            "REQUEST CONTEXT\n"
            "---\n"
            f"{self._build_input_text(context)}"
        )

    @classmethod
    def _build_input_text(cls, context: EntityRecognitionContext) -> str:
        compact_raw_record = cls._build_compact_raw_record(context)
        serialized_payload = json.dumps(compact_raw_record, default=str)
        if len(serialized_payload) > _MAX_ENTITY_RECOGNITION_RAW_JSON_CHARS:
            serialized_payload = serialized_payload[
                :_MAX_ENTITY_RECOGNITION_RAW_JSON_CHARS
            ]
        return (
            f"SOURCE TYPE: {context.source_type}\n"
            f"DOCUMENT ID: {context.document_id}\n"
            f"RESEARCH SPACE ID: {context.research_space_id or 'none'}\n"
            f"SHADOW MODE: {context.shadow_mode}\n\n"
            f"RAW RECORD JSON:\n{serialized_payload}"
        )

    @classmethod
    def _build_compact_raw_record(
        cls,
        context: EntityRecognitionContext,
    ) -> dict[str, object]:
        raw_record = context.raw_record
        source_type = context.source_type.strip().lower()
        if source_type == "pubmed":
            compact: dict[str, object] = {}
            allowed_fields: tuple[str, ...] = (
                "pubmed_id",
                "title",
                "doi",
                "source",
                "full_text_source",
                "full_text_chunk_index",
                "full_text_chunk_total",
                "full_text_chunk_start_char",
                "full_text_chunk_end_char",
                "publication_date",
                "publication_types",
                "journal",
                "keywords",
            )
            for field in allowed_fields:
                value = raw_record.get(field)
                if value is None:
                    continue
                compact[field] = to_json_value(value)
            full_text = raw_record.get("full_text")
            if isinstance(full_text, str) and full_text.strip():
                compact["full_text"] = full_text[:_MAX_ENTITY_RECOGNITION_TEXT_CHARS]
            else:
                abstract = raw_record.get("abstract")
                if isinstance(abstract, str) and abstract.strip():
                    compact["abstract"] = abstract[:_MAX_ENTITY_RECOGNITION_TEXT_CHARS]
            return compact
        if source_type == "clinvar":
            compact = {}
            for field in (
                "variation_id",
                "gene_symbol",
                "variant_name",
                "clinical_significance",
                "condition_name",
                "review_status",
                "submission_count",
                "source",
            ):
                value = raw_record.get(field)
                if value is None:
                    continue
                compact[field] = to_json_value(value)
            return compact
        return {str(key): to_json_value(value) for key, value in raw_record.items()}

    @classmethod
    def _resolve_pipeline_usage_limits(cls, base_limits: UsageLimits) -> UsageLimits:
        env_override = cls._read_positive_int_from_env(
            _ENV_ENTITY_RECOGNITION_USAGE_MAX_TOKENS,
        )
        base_max_tokens = (
            base_limits.max_tokens
            if isinstance(base_limits.max_tokens, int) and base_limits.max_tokens > 0
            else None
        )
        minimum_tokens = (
            env_override
            if env_override is not None
            else _DEFAULT_ENTITY_RECOGNITION_USAGE_MAX_TOKENS
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
        if not normalized or not normalized.isdigit():
            return None
        parsed = int(normalized)
        return parsed if parsed > 0 else None

    def _normalize_contract(
        self,
        *,
        contract: EntityRecognitionContract,
        context: EntityRecognitionContext,
        source_type: str,
        run_id: str,
    ) -> EntityRecognitionContract:
        updates: dict[str, object] = {
            "source_type": source_type,
            "document_id": context.document_id,
            "shadow_mode": context.shadow_mode,
        }
        if contract.agent_run_id is None:
            updates["agent_run_id"] = run_id
        if not contract.pipeline_payloads:
            compact_payload = self._build_compact_raw_record(context)
            if compact_payload:
                updates["pipeline_payloads"] = [compact_payload]
        return contract.model_copy(update=updates)

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


__all__ = ["ArtanaEntityRecognitionAdapter"]
