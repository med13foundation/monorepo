"""Harness-owned graph-connection orchestration runtime."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from artana.kernel import ArtanaKernel
from artana.models import TenantContext
from artana.ports.model import LiteLLMAdapter

from services.graph_harness_api.harness_registry import get_harness_template
from services.graph_harness_api.policy import build_graph_harness_policy
from services.graph_harness_api.runtime_skill_agent import (
    GraphHarnessSkillAutonomousAgent,
    GraphHarnessSkillContextBuilder,
)
from services.graph_harness_api.runtime_skill_registry import (
    load_graph_harness_skill_registry,
)
from services.graph_harness_api.tool_registry import build_graph_harness_tool_registry
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_connection import GraphConnectionContract
from src.domain.agents.models import ModelCapability
from src.graph.runtime import create_graph_domain_pack
from src.infrastructure.llm.adapters._openai_json_schema_model_port import (
    has_configured_openai_api_key,
)
from src.infrastructure.llm.config import (
    GovernanceConfig,
    get_model_registry,
    load_runtime_policy,
)
from src.infrastructure.llm.state.shared_postgres_store import (
    get_shared_artana_postgres_store,
)

_DEFAULT_AGENT_IDENTITY = "You are the graph-harness autonomous graph-connection agent."
_MAX_GRAPH_CONNECTION_ITERATIONS = 6

if TYPE_CHECKING:
    from services.graph_harness_api.harness_registry import HarnessTemplate
    from src.type_definitions.common import ResearchSpaceSettings


@dataclass(frozen=True, slots=True)
class HarnessGraphConnectionRequest:
    """One graph-connection AI execution request."""

    harness_id: str
    seed_entity_id: str
    research_space_id: str
    source_type: str | None
    source_id: str | None
    model_id: str | None
    relation_types: list[str] | None
    max_depth: int
    shadow_mode: bool
    pipeline_run_id: str | None
    research_space_settings: ResearchSpaceSettings


@dataclass(frozen=True, slots=True)
class HarnessGraphConnectionResult:
    """One graph-connection execution result with skill metadata."""

    contract: GraphConnectionContract
    agent_run_id: str | None
    active_skill_names: tuple[str, ...]


class HarnessGraphConnectionRunner:
    """Run graph-connection through a skill-aware Artana autonomous agent."""

    def __init__(self) -> None:
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()

    async def run(
        self,
        request: HarnessGraphConnectionRequest,
    ) -> HarnessGraphConnectionResult:
        """Execute one AI-backed graph-connection request."""
        harness_template = self._require_harness_template(request.harness_id)
        graph_domain_pack = create_graph_domain_pack()
        prompt_config = graph_domain_pack.graph_connection_prompt
        resolved_source_type = prompt_config.resolve_source_type(request.source_type)
        if resolved_source_type not in prompt_config.supported_source_types():
            contract = self._unsupported_source_contract(
                request,
                source_type=resolved_source_type,
            )
            return HarnessGraphConnectionResult(
                contract=contract,
                agent_run_id=None,
                active_skill_names=(),
            )
        if not has_configured_openai_api_key():
            contract = self._fallback_contract(
                request,
                source_type=resolved_source_type,
                reason="missing_openai_api_key",
                agent_run_id=None,
            )
            return HarnessGraphConnectionResult(
                contract=contract,
                agent_run_id=None,
                active_skill_names=(),
            )

        effective_model = self._resolve_model_id(request.model_id)
        run_id = self._create_run_id(
            harness_id=request.harness_id,
            source_type=resolved_source_type,
            model_id=effective_model,
            research_space_id=request.research_space_id,
            source_id=request.source_id,
            pipeline_run_id=request.pipeline_run_id,
            seed_entity_id=request.seed_entity_id,
        )
        tenant = self._create_tenant(
            tenant_id=request.research_space_id,
            budget_usd_limit=self._budget_limit_usd(),
        )
        skill_registry = load_graph_harness_skill_registry()
        domain_prompt = prompt_config.system_prompt_for(resolved_source_type)
        if domain_prompt is None:
            contract = self._unsupported_source_contract(
                request,
                source_type=resolved_source_type,
            )
            return HarnessGraphConnectionResult(
                contract=contract,
                agent_run_id=None,
                active_skill_names=(),
            )
        context_builder = GraphHarnessSkillContextBuilder(
            skill_registry=skill_registry,
            preloaded_skill_names=harness_template.preloaded_skill_names,
            identity=_DEFAULT_AGENT_IDENTITY,
            task_category="graph_connection",
        )
        kernel = ArtanaKernel(
            store=get_shared_artana_postgres_store(),
            model_port=LiteLLMAdapter(
                timeout_seconds=self._resolve_timeout_seconds(effective_model),
            ),
            tool_port=build_graph_harness_tool_registry(),
            policy=build_graph_harness_policy(),
        )
        agent = GraphHarnessSkillAutonomousAgent(
            kernel,
            skill_registry=skill_registry,
            preloaded_skill_names=harness_template.preloaded_skill_names,
            allowed_skill_names=harness_template.allowed_skill_names,
            context_builder=context_builder,
            replay_policy=self._runtime_policy.replay_policy,
        )
        try:
            contract = await agent.run(
                run_id=run_id,
                tenant=tenant,
                model=effective_model,
                system_prompt=self._system_prompt(domain_prompt=domain_prompt),
                prompt=self._request_prompt(
                    request=request,
                    source_type=resolved_source_type,
                ),
                output_schema=GraphConnectionContract,
                max_iterations=_MAX_GRAPH_CONNECTION_ITERATIONS,
            )
            active_skill_names = await agent.emit_active_skill_summary(
                run_id=run_id,
                tenant=tenant,
                step_key="graph_connection.active_skills",
            )
            normalized_contract = contract.model_copy(
                update={
                    "source_type": resolved_source_type,
                    "research_space_id": request.research_space_id,
                    "seed_entity_id": request.seed_entity_id,
                    "shadow_mode": request.shadow_mode,
                    "agent_run_id": contract.agent_run_id or run_id,
                },
            )
            return HarnessGraphConnectionResult(
                contract=normalized_contract,
                agent_run_id=normalized_contract.agent_run_id,
                active_skill_names=active_skill_names,
            )
        except Exception:  # noqa: BLE001
            contract = self._fallback_contract(
                request,
                source_type=resolved_source_type,
                reason="agent_execution_failed",
                agent_run_id=run_id,
            )
            return HarnessGraphConnectionResult(
                contract=contract,
                agent_run_id=run_id,
                active_skill_names=(),
            )
        finally:
            await kernel.close()

    def _resolve_model_id(self, requested_model_id: str | None) -> str:
        if (
            self._registry.allow_runtime_model_overrides()
            and requested_model_id is not None
            and self._registry.validate_model_for_capability(
                requested_model_id,
                ModelCapability.EVIDENCE_EXTRACTION,
            )
        ):
            return requested_model_id
        return self._registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        ).model_id

    def _resolve_timeout_seconds(self, model_id: str) -> float:
        try:
            return float(self._registry.get_model(model_id).timeout_seconds)
        except (KeyError, ValueError):
            return 120.0

    def _budget_limit_usd(self) -> float:
        usage_limits = self._governance.usage_limits
        total_cost = usage_limits.total_cost_usd
        return max(float(total_cost if total_cost else 1.0), 0.01)

    @staticmethod
    def _create_tenant(*, tenant_id: str, budget_usd_limit: float) -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=budget_usd_limit,
        )

    @staticmethod
    def _create_run_id(  # noqa: PLR0913
        *,
        harness_id: str,
        source_type: str,
        model_id: str,
        research_space_id: str,
        source_id: str | None,
        pipeline_run_id: str | None,
        seed_entity_id: str,
    ) -> str:
        normalized_source_id = source_id.strip() if isinstance(source_id, str) else ""
        normalized_pipeline_run_id = (
            pipeline_run_id.strip() if isinstance(pipeline_run_id, str) else ""
        )
        payload = (
            f"{harness_id.strip()}|{source_type}|{model_id}|{research_space_id}|"
            f"{normalized_source_id}|{normalized_pipeline_run_id}|{seed_entity_id}"
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
        return f"graph_connection:{source_type}:{digest}"

    @staticmethod
    def _system_prompt(*, domain_prompt: str) -> str:
        return (
            f"{domain_prompt}\n\n"
            "Service runtime overlay:\n"
            "- Ignore any legacy tool names mentioned above if they are not visible in "
            "the runtime skill panel.\n"
            "- Use only the currently active tools exposed by runtime skills.\n"
            "- load_skill(skill_name=...) loads one named runtime skill, not an "
            "individual tool.\n"
            "- Base discovery should stay inside the active research space and use only "
            "returned IDs.\n"
        )

    @staticmethod
    def _request_prompt(
        *,
        request: HarnessGraphConnectionRequest,
        source_type: str,
    ) -> str:
        relation_types = (
            json.dumps(request.relation_types, default=str)
            if request.relation_types is not None
            else "null"
        )
        settings_payload = json.dumps(request.research_space_settings, default=str)
        return (
            "REQUEST CONTEXT\n"
            "---\n"
            f"SOURCE TYPE: {source_type}\n"
            f"RESEARCH SPACE ID: {request.research_space_id}\n"
            f"SOURCE ID: {request.source_id or 'unknown'}\n"
            f"PIPELINE RUN ID: {request.pipeline_run_id or 'none'}\n"
            f"SEED ENTITY ID: {request.seed_entity_id}\n"
            f"MAX DEPTH: {request.max_depth}\n"
            f"RELATION TYPES FILTER: {relation_types}\n"
            f"SHADOW MODE: {request.shadow_mode}\n\n"
            f"RESEARCH SPACE SETTINGS JSON:\n{settings_payload}\n"
            "Return a valid GraphConnectionContract.\n"
        )

    @staticmethod
    def _require_harness_template(harness_id: str) -> HarnessTemplate:
        template = get_harness_template(harness_id)
        if template is None:
            msg = f"Unknown graph-harness template {harness_id!r}."
            raise ValueError(msg)
        return template

    @staticmethod
    def _fallback_contract(
        request: HarnessGraphConnectionRequest,
        *,
        source_type: str,
        reason: str,
        agent_run_id: str | None,
    ) -> GraphConnectionContract:
        return GraphConnectionContract(
            decision="fallback",
            confidence_score=0.35,
            rationale=f"Graph connection fallback triggered ({reason}).",
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"graph-connection:{request.research_space_id}",
                    excerpt=f"Fallback reason: {reason}",
                    relevance=0.4,
                ),
            ],
            source_type=source_type,
            research_space_id=request.research_space_id,
            seed_entity_id=request.seed_entity_id,
            proposed_relations=[],
            rejected_candidates=[],
            shadow_mode=request.shadow_mode,
            agent_run_id=agent_run_id,
        )

    @staticmethod
    def _unsupported_source_contract(
        request: HarnessGraphConnectionRequest,
        *,
        source_type: str,
    ) -> GraphConnectionContract:
        return GraphConnectionContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=f"Source type '{source_type}' is not supported",
            evidence=[],
            source_type=source_type,
            research_space_id=request.research_space_id,
            seed_entity_id=request.seed_entity_id,
            proposed_relations=[],
            rejected_candidates=[],
            shadow_mode=request.shadow_mode,
            agent_run_id=None,
        )


__all__ = [
    "HarnessGraphConnectionRequest",
    "HarnessGraphConnectionResult",
    "HarnessGraphConnectionRunner",
]
