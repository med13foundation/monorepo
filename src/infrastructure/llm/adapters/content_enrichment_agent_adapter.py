"""Artana-based adapter for Tier-2 content-enrichment workflows."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.content_enrichment import ContentEnrichmentContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.content_enrichment_port import ContentEnrichmentPort
from src.infrastructure.llm.adapters._artana_step_helpers import (
    build_deterministic_run_id,
    run_single_step_with_policy,
)
from src.infrastructure.llm.adapters._openai_json_schema_model_port import (
    OpenAIJSONSchemaModelPort,
    has_configured_openai_api_key,
)
from src.infrastructure.llm.config import (
    GovernanceConfig,
    get_model_registry,
    load_runtime_policy,
)
from src.infrastructure.llm.prompts.content_enrichment import (
    CONTENT_ENRICHMENT_SYSTEM_PROMPT,
)
from src.infrastructure.llm.state.shared_postgres_store import (
    get_shared_artana_postgres_store,
)
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from artana.store import PostgresStore

    from src.domain.agents.contexts.content_enrichment_context import (
        ContentEnrichmentContext,
    )
    from src.type_definitions.common import JSONObject, JSONValue
else:
    type JSONValue = object
    type JSONObject = dict[str, object]

_STRUCTURED_SOURCE_TYPES = frozenset({"clinvar", "api", "database", "file_upload"})
_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_IMPORT_ERROR = exc

# Backward-compatible alias for adapter unit-test patch hooks.
_OpenAIChatModelPort = OpenAIJSONSchemaModelPort


class ArtanaContentEnrichmentAdapter(ContentEnrichmentPort):
    """Adapter that executes content-enrichment workflows through Artana."""

    def __init__(
        self,
        model: str | None = None,
        *,
        artana_store: PostgresStore | None = None,
    ) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import-time guard
            msg = (
                "artana-kernel is required for content enrichment execution. Install dependency "
                "'artana @ git+https://github.com/aandresalvarez/artana-kernel.git@main'."
            )
            raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

        self._default_model = model
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()
        self._last_run_id: str | None = None
        timeout_seconds = self._resolve_timeout_seconds(model)
        self._model_port = _OpenAIChatModelPort(
            timeout_seconds=timeout_seconds,
            schema_name_fallback="content_enrichment_contract",
        )
        resolved_artana_store = artana_store or self._create_store()
        self._kernel = ArtanaKernel(
            store=resolved_artana_store,
            model_port=self._model_port,
        )
        self._client = SingleStepModelClient(kernel=self._kernel)

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
            return self._ai_required_contract(
                context,
                reason="missing_openai_api_key",
            )

        effective_model = self._resolve_model_id(model_id)
        run_id = self._create_run_id(
            source_type=source_type,
            research_space_id=context.research_space_id,
            external_id=context.external_record_id,
            extraction_config_version=self._runtime_policy.extraction_config_version,
        )
        self._last_run_id = run_id

        try:
            usage_limits = self._governance.usage_limits
            budget_limit = (
                usage_limits.total_cost_usd if usage_limits.total_cost_usd else 1.0
            )
            tenant = self._create_tenant(
                tenant_id=context.research_space_id or "content_enrichment",
                budget_usd_limit=max(float(budget_limit), 0.01),
            )
            result = await run_single_step_with_policy(
                self._client,
                run_id=run_id,
                tenant=tenant,
                model=effective_model,
                prompt=self._build_prompt(context),
                output_schema=ContentEnrichmentContract,
                step_key="content.enrichment.v1",
                replay_policy=self._runtime_policy.replay_policy,
                context_version=self._runtime_policy.to_context_version(),
            )
            output = result.output
            contract = (
                output
                if isinstance(output, ContentEnrichmentContract)
                else ContentEnrichmentContract.model_validate(output)
            )
            return contract.model_copy(
                update={
                    "document_id": context.document_id,
                    "source_type": context.source_type,
                    "agent_run_id": contract.agent_run_id or run_id,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return self._ai_required_contract(
                context,
                reason=f"pipeline_execution_failed:{type(exc).__name__}",
            )

    async def close(self) -> None:
        await self._model_port.aclose()

    @staticmethod
    def _has_openai_key() -> bool:
        return has_configured_openai_api_key()

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

    @staticmethod
    def _create_run_id(  # noqa: PLR0913
        *,
        source_type: str,
        research_space_id: str | None = None,
        external_id: str | None = None,
        extraction_config_version: str = "v1",
        model_id: str | None = None,
        document_id: str | None = None,
    ) -> str:
        _ = model_id  # retained for backward-compatible call sites/tests
        resolved_external_id = (external_id or document_id or "").strip() or "unknown"
        return build_deterministic_run_id(
            prefix="content_enrichment",
            research_space_id=research_space_id,
            source_type=source_type,
            external_id=resolved_external_id,
            extraction_config_version=extraction_config_version,
        )

    @staticmethod
    def _create_tenant(tenant_id: str, budget_usd_limit: float) -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=budget_usd_limit,
        )

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

    def _build_prompt(self, context: ContentEnrichmentContext) -> str:
        return (
            f"{CONTENT_ENRICHMENT_SYSTEM_PROMPT}\n\n"
            "---\n"
            "REQUEST CONTEXT\n"
            "---\n"
            f"{self._build_input_text(context)}"
        )

    def _heuristic_contract(
        self,
        context: ContentEnrichmentContext,
        *,
        warning: str,
    ) -> ContentEnrichmentContract:
        source_type = context.source_type.strip().lower()
        if source_type in _STRUCTURED_SOURCE_TYPES:
            return self._pass_through_contract(context, warning=warning)
        return self._ai_required_contract(
            context,
            reason=warning.strip() or "heuristic_fallback_disabled",
        )

    def _ai_required_contract(
        self,
        context: ContentEnrichmentContext,
        *,
        reason: str,
    ) -> ContentEnrichmentContract:
        return ContentEnrichmentContract(
            decision="failed",
            confidence_score=0.0,
            rationale=(
                "AI-only content enrichment with full-text acquisition is required; "
                f"no metadata abstract/title fallback is allowed ({reason})."
            ),
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"document:{context.document_id}",
                    excerpt=f"AI content enrichment unavailable: {reason}",
                    relevance=1.0,
                ),
            ],
            document_id=context.document_id,
            source_type=context.source_type,
            acquisition_method="skipped",
            content_format="text",
            content_length_chars=0,
            warning=f"AI content enrichment unavailable: {reason}",
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
    def _extract_structured_payload(metadata: dict[str, JSONValue]) -> JSONObject:
        raw_record = metadata.get("raw_record")
        if isinstance(raw_record, dict):
            return {str(key): to_json_value(value) for key, value in raw_record.items()}
        return {str(key): to_json_value(value) for key, value in metadata.items()}

    @staticmethod
    def _extract_text_from_metadata(metadata: dict[str, JSONValue]) -> str | None:
        raw_record = metadata.get("raw_record")
        candidate_sources: list[dict[str, JSONValue]] = []
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


__all__ = ["ArtanaContentEnrichmentAdapter"]
