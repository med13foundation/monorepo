"""Artana-based adapter for extraction agent operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain.agents.contracts import EvidenceItem, ExtractionContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.extraction_agent_port import ExtractionAgentPort
from src.infrastructure.llm.adapters._artana_step_helpers import (
    build_deterministic_run_id,
    resolve_external_record_id,
    run_single_step_with_policy,
)
from src.infrastructure.llm.adapters._extraction_adapter_payloads import (
    DEFAULT_EXTRACTION_USAGE_MAX_TOKENS,
    ENV_EXTRACTION_USAGE_MAX_TOKENS,
    build_compact_raw_record,
    build_extraction_input_text,
    build_extraction_prompt,
    coerce_utc_iso_datetime,
    get_extraction_system_prompt,
    normalize_temporal_context,
    normalize_temporal_value,
    sanitize_json_value,
    sanitize_text_value,
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
from src.infrastructure.llm.state.shared_postgres_store import (
    create_artana_postgres_store,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from artana.store import PostgresStore

    from src.domain.agents.contexts.extraction_context import ExtractionContext

logger = logging.getLogger(__name__)

_SUPPORTED_SOURCE_TYPES = frozenset({"clinvar", "pubmed"})
_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_IMPORT_ERROR = exc

# Backward-compatible alias for adapter unit-test patch hooks.
_OpenAIChatModelPort = OpenAIJSONSchemaModelPort


class ArtanaExtractionAdapter(ExtractionAgentPort):
    """Adapter that executes extraction workflows through Artana."""

    def __init__(
        self,
        model: str | None = None,
        *,
        use_governance: bool = True,
        dictionary_service: object | None = None,
        artana_store: PostgresStore | None = None,
    ) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import-time guard
            msg = (
                "artana-kernel is required for extraction execution. Install dependency "
                "'artana @ git+https://github.com/aandresalvarez/artana-kernel.git@main'."
            )
            raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

        self._default_model = model
        self._use_governance = use_governance
        self._dictionary_service = dictionary_service
        self._governance = GovernanceConfig.from_environment()
        self._pipeline_usage_limits = self._resolve_pipeline_usage_limits(
            self._governance.usage_limits,
        )
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()
        self._last_run_id: str | None = None
        self._artana_store = artana_store

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
        relation_governance_mode = self._resolve_relation_governance_mode(
            context.research_space_settings,
        )

        try:
            usage_limits = self._pipeline_usage_limits
            budget_limit = (
                usage_limits.total_cost_usd if usage_limits.total_cost_usd else 1.0
            )
            tenant = self._create_tenant(
                tenant_id=context.research_space_id or "extraction",
                budget_usd_limit=max(float(budget_limit), 0.01),
            )
            kernel, client, model_port = self._create_runtime()
            result = await run_single_step_with_policy(
                client,
                run_id=run_id,
                tenant=tenant,
                model=effective_model,
                prompt=self._build_prompt(
                    source_type=source_type,
                    context=context,
                    relation_governance_mode=relation_governance_mode,
                ),
                output_schema=ExtractionContract,
                step_key=f"extraction.{source_type}.v1",
                replay_policy=self._runtime_policy.replay_policy,
                context_version=self._runtime_policy.to_context_version(),
            )
            output = result.output
            contract = (
                output
                if isinstance(output, ExtractionContract)
                else ExtractionContract.model_validate(output)
            )
            return self._normalize_contract(
                contract=contract,
                context=context,
                source_type=source_type,
                run_id=run_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Extraction Artana step failed for document=%s source_type=%s model=%s: %s",
                context.document_id,
                source_type,
                effective_model,
                exc,
                exc_info=True,
            )
            return self._ai_required_contract(
                context,
                reason=f"pipeline_execution_failed:{type(exc).__name__}",
            )
        finally:
            if "kernel" in locals() and "model_port" in locals():
                try:
                    await kernel.close()
                finally:
                    await model_port.aclose()

    async def close(self) -> None:
        return

    @staticmethod
    def _has_openai_key() -> bool:
        return has_configured_openai_api_key()

    def _create_runtime(
        self,
    ) -> tuple[ArtanaKernel, SingleStepModelClient, _OpenAIChatModelPort]:
        timeout_seconds = self._resolve_timeout_seconds(self._default_model)
        model_port = _OpenAIChatModelPort(
            timeout_seconds=timeout_seconds,
            schema_name_fallback="extraction_contract",
        )
        kernel = ArtanaKernel(
            store=self._artana_store or self._create_store(),
            model_port=model_port,
        )
        client = SingleStepModelClient(kernel=kernel)
        return kernel, client, model_port

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
        return create_artana_postgres_store()

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
            prefix="extraction",
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
        return get_extraction_system_prompt(source_type)

    def _build_prompt(
        self,
        *,
        source_type: str,
        context: ExtractionContext,
        relation_governance_mode: str,
    ) -> str:
        return build_extraction_prompt(
            source_type=source_type,
            context=context,
            relation_governance_mode=relation_governance_mode,
        )

    @classmethod
    def _resolve_pipeline_usage_limits(cls, base_limits: UsageLimits) -> UsageLimits:
        env_override = cls._read_positive_int_from_env(
            ENV_EXTRACTION_USAGE_MAX_TOKENS,
        )
        base_max_tokens = (
            base_limits.max_tokens
            if isinstance(base_limits.max_tokens, int) and base_limits.max_tokens > 0
            else None
        )
        minimum_tokens = (
            env_override
            if env_override is not None
            else DEFAULT_EXTRACTION_USAGE_MAX_TOKENS
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
        import os

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

    @staticmethod
    def _resolve_relation_governance_mode(settings: Mapping[str, object]) -> str:
        raw_mode = settings.get("relation_governance_mode")
        if isinstance(raw_mode, str) and raw_mode.strip().upper() == "FULL_AUTO":
            return "FULL_AUTO"
        return "HUMAN_IN_LOOP"

    def _build_input_text(self, context: ExtractionContext) -> str:
        return build_extraction_input_text(context)

    @classmethod
    def _sanitize_json_value(cls, value: object) -> object:
        return sanitize_json_value(value)

    @staticmethod
    def _sanitize_text_value(value: str) -> str:
        return sanitize_text_value(value)

    @staticmethod
    def _build_compact_raw_record(context: ExtractionContext) -> dict[str, object]:
        return build_compact_raw_record(context)

    @classmethod
    def _normalize_temporal_context(
        cls,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return normalize_temporal_context(payload)

    @classmethod
    def _normalize_temporal_value(cls, *, key: str, value: object) -> object:
        return normalize_temporal_value(key=key, value=value)

    @staticmethod
    def _coerce_utc_iso_datetime(raw_value: str | datetime) -> str | None:
        return coerce_utc_iso_datetime(raw_value)

    def _normalize_contract(
        self,
        *,
        contract: ExtractionContract,
        context: ExtractionContext,
        source_type: str,
        run_id: str,
    ) -> ExtractionContract:
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


__all__ = ["ArtanaExtractionAdapter"]
