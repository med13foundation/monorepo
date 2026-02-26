"""Artana-based adapter for mapping-judge operations."""

from __future__ import annotations

import asyncio
import logging
from threading import Thread
from typing import TYPE_CHECKING, Literal

from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.mapping_judge import MappingJudgeContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
from src.infrastructure.llm.adapters._artana_step_helpers import (
    run_single_step_with_policy,
    stable_sha256_digest,
)
from src.infrastructure.llm.adapters._openai_json_schema_model_port import (
    OpenAIJSONSchemaModelPort,
    has_configured_openai_api_key,
)
from src.infrastructure.llm.config import (
    GovernanceConfig,
    get_model_registry,
    load_runtime_policy,
    resolve_artana_state_uri,
)
from src.infrastructure.llm.prompts.mapping_judge import MAPPING_JUDGE_SYSTEM_PROMPT

if TYPE_CHECKING:
    from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext

logger = logging.getLogger(__name__)

_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
    from artana.store import PostgresStore
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_IMPORT_ERROR = exc

# Backward-compatible alias for adapter unit-test patch hooks.
_OpenAIChatModelPort = OpenAIJSONSchemaModelPort


class ArtanaMappingJudgeAdapter(MappingJudgePort):
    """Adapter that executes mapping-judge workflows through Artana."""

    def __init__(self, model: str | None = None) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import-time guard
            msg = (
                "artana-kernel is required for mapping judge execution. Install "
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
            schema_name_fallback="mapping_judge_contract",
        )
        self._kernel = ArtanaKernel(
            store=self._create_store(),
            model_port=self._model_port,
        )
        self._client = SingleStepModelClient(kernel=self._kernel)

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

        if not context.candidates:
            return self._fallback_contract(
                context,
                decision="no_match",
                reason="Mapping-judge received no candidates.",
            )

        effective_model = self._resolve_model_id(model_id)
        run_id = self._create_run_id(
            model_id=effective_model,
            source_id=context.source_id,
            field_key=context.field_key,
            field_value_preview=context.field_value_preview,
            candidate_ids=[candidate.variable_id for candidate in context.candidates],
        )
        self._last_run_id = run_id

        try:
            return self._run_contract_coroutine(
                self._judge_async(
                    context=context,
                    model_id=effective_model,
                    run_id=run_id,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Mapping-judge execution failed for field_key=%s: %s",
                context.field_key,
                exc,
            )
            return self._fallback_contract(
                context,
                decision="no_match",
                reason="Mapping-judge execution failed.",
            )

    def close(self) -> None:
        self._run_void_coroutine(self._close_async())

    async def _close_async(self) -> None:
        await self._model_port.aclose()
        await self._kernel.close()

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
    def _create_store() -> object:
        state_uri = resolve_artana_state_uri()
        if state_uri.startswith("postgresql://"):
            return PostgresStore(state_uri)
        msg = f"Unsupported ARTANA_STATE_URI scheme: {state_uri}"
        raise ValueError(msg)

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
    def _create_run_id(
        *,
        model_id: str,
        source_id: str,
        field_key: str,
        field_value_preview: str,
        candidate_ids: list[str],
    ) -> str:
        payload = "|".join(
            [
                model_id,
                source_id,
                field_key.strip(),
                field_value_preview.strip(),
                ",".join(sorted(candidate_ids)),
            ],
        )
        digest = stable_sha256_digest(payload)
        return f"mapping_judge:{digest}"

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
            f"{MAPPING_JUDGE_SYSTEM_PROMPT}\n\n"
            "---\n"
            "REQUEST CONTEXT\n"
            "---\n"
            f"FIELD KEY: {context.field_key}\n"
            f"FIELD VALUE: {context.field_value_preview}\n"
            f"SOURCE ID: {context.source_id}\n"
            f"SOURCE TYPE: {context.source_type or 'unknown'}\n"
            f"DOMAIN CONTEXT: {context.domain_context or 'none'}\n"
            "CANDIDATES:\n"
            f"{candidates_blob}\n"
        )

    @staticmethod
    def _create_tenant(tenant_id: str, budget_usd_limit: float) -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=budget_usd_limit,
        )

    async def _judge_async(
        self,
        *,
        context: MappingJudgeContext,
        model_id: str,
        run_id: str,
    ) -> MappingJudgeContract:
        input_text = self._build_input_text(context)
        usage_limits = self._governance.usage_limits
        budget_limit = (
            usage_limits.total_cost_usd if usage_limits.total_cost_usd else 1.0
        )
        tenant = self._create_tenant(
            tenant_id=f"mapping_judge:{context.source_id}",
            budget_usd_limit=max(float(budget_limit), 0.01),
        )

        result = await run_single_step_with_policy(
            self._client,
            run_id=run_id,
            tenant=tenant,
            model=model_id,
            prompt=input_text,
            output_schema=MappingJudgeContract,
            step_key="mapping.judge.v1",
            replay_policy=self._runtime_policy.replay_policy,
        )
        output = result.output
        contract = (
            output
            if isinstance(output, MappingJudgeContract)
            else MappingJudgeContract.model_validate(output)
        )
        normalized = self._normalize_contract(contract=contract, context=context)
        if normalized.agent_run_id is None:
            normalized = normalized.model_copy(update={"agent_run_id": run_id})
        return normalized

    def _normalize_contract(
        self,
        *,
        contract: MappingJudgeContract,
        context: MappingJudgeContext,
    ) -> MappingJudgeContract:
        candidate_map = {
            candidate.variable_id: candidate for candidate in context.candidates
        }
        candidate_count = len(context.candidates)

        if contract.decision == "matched":
            selected_id = contract.selected_variable_id
            if selected_id is None or selected_id not in candidate_map:
                reason = (
                    "Mapping-judge selected a variable_id outside provided candidates. "
                    "Converted to no_match."
                )
                return self._fallback_contract(
                    context,
                    decision="no_match",
                    reason=reason,
                )
            selected_candidate = candidate_map[selected_id]
            normalized = contract.model_copy(
                update={
                    "candidate_count": candidate_count,
                    "selected_candidate": selected_candidate,
                    "selected_variable_id": selected_id,
                },
            )
            if normalized.evidence:
                return normalized
            return normalized.model_copy(
                update={
                    "evidence": [
                        EvidenceItem(
                            source_type="note",
                            locator=f"mapping-judge:{context.source_id}:{context.field_key}",
                            excerpt="LLM selected a provided mapping candidate.",
                            relevance=0.5,
                        ),
                    ],
                },
            )

        return contract.model_copy(
            update={
                "candidate_count": candidate_count,
                "selected_variable_id": None,
                "selected_candidate": None,
            },
        )

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
    def _run_contract_coroutine(coroutine: object) -> MappingJudgeContract:
        if not asyncio.iscoroutine(coroutine):
            msg = "Expected coroutine for mapping judge execution."
            raise TypeError(msg)

        async def _typed_coroutine() -> MappingJudgeContract:
            result = await coroutine
            if not isinstance(result, MappingJudgeContract):
                msg = "Mapping judge coroutine returned unexpected result type."
                raise TypeError(msg)
            return result

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_typed_coroutine())

        result_holder: dict[str, MappingJudgeContract | None] = {"result": None}
        error_holder: dict[str, BaseException | None] = {"error": None}

        def _target() -> None:
            try:
                result_holder["result"] = asyncio.run(_typed_coroutine())
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
    def _run_void_coroutine(coroutine: object) -> None:
        if not asyncio.iscoroutine(coroutine):
            msg = "Expected coroutine for close operation."
            raise TypeError(msg)
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


__all__ = ["ArtanaMappingJudgeAdapter"]
