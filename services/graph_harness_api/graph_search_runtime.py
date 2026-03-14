"""Harness-owned graph-search orchestration runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

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
from src.domain.agents.contracts.graph_search import GraphSearchContract
from src.domain.agents.models import ModelCapability
from src.graph.runtime import create_graph_domain_pack
from src.infrastructure.llm.adapters._artana_step_helpers import stable_sha256_digest
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

_DEFAULT_AGENT_IDENTITY = "You are the graph-harness autonomous graph-search agent."
_MAX_GRAPH_SEARCH_ITERATIONS = 6

if TYPE_CHECKING:
    from services.graph_harness_api.harness_registry import HarnessTemplate


@dataclass(frozen=True, slots=True)
class HarnessGraphSearchRequest:
    """One graph-search AI execution request."""

    harness_id: str
    question: str
    research_space_id: str
    max_depth: int
    top_k: int
    curation_statuses: list[str] | None
    include_evidence_chains: bool
    model_id: str | None


@dataclass(frozen=True, slots=True)
class HarnessGraphSearchResult:
    """One graph-search execution result with skill metadata."""

    contract: GraphSearchContract
    agent_run_id: str | None
    active_skill_names: tuple[str, ...]


class HarnessGraphSearchRunner:
    """Run graph-search through a skill-aware Artana autonomous agent."""

    def __init__(self) -> None:
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()

    async def run(
        self,
        request: HarnessGraphSearchRequest,
    ) -> HarnessGraphSearchResult:
        """Execute one AI-backed graph-search request."""
        if not has_configured_openai_api_key():
            contract = self._fallback_contract(
                request,
                decision="fallback",
                reason="Graph-search agent API key is not configured.",
                agent_run_id=None,
            )
            return HarnessGraphSearchResult(
                contract=contract,
                agent_run_id=None,
                active_skill_names=(),
            )

        harness_template = self._require_harness_template(request.harness_id)
        graph_domain_pack = create_graph_domain_pack()
        effective_model = self._resolve_model_id(request.model_id)
        run_id = self._create_run_id(
            model_id=effective_model,
            research_space_id=request.research_space_id,
            question=request.question,
            harness_id=request.harness_id,
        )
        tenant = self._create_tenant(
            tenant_id=request.research_space_id,
            budget_usd_limit=self._budget_limit_usd(),
        )
        skill_registry = load_graph_harness_skill_registry()
        context_builder = GraphHarnessSkillContextBuilder(
            skill_registry=skill_registry,
            preloaded_skill_names=harness_template.preloaded_skill_names,
            identity=_DEFAULT_AGENT_IDENTITY,
            task_category="graph_search",
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
                system_prompt=self._system_prompt(
                    graph_domain_pack.search_extension.system_prompt,
                ),
                prompt=self._request_prompt(request),
                output_schema=GraphSearchContract,
                max_iterations=_MAX_GRAPH_SEARCH_ITERATIONS,
            )
            active_skill_names = await agent.emit_active_skill_summary(
                run_id=run_id,
                tenant=tenant,
                step_key="graph_search.active_skills",
            )
            normalized_contract = contract.model_copy(
                update={
                    "research_space_id": request.research_space_id,
                    "original_query": request.question,
                    "total_results": len(contract.results),
                    "executed_path": "agent",
                    "agent_run_id": contract.agent_run_id or run_id,
                },
            )
            return HarnessGraphSearchResult(
                contract=normalized_contract,
                agent_run_id=normalized_contract.agent_run_id,
                active_skill_names=active_skill_names,
            )
        except Exception:  # noqa: BLE001
            contract = self._fallback_contract(
                request,
                decision="fallback",
                reason="Graph-search agent execution failed.",
                agent_run_id=run_id,
            )
            return HarnessGraphSearchResult(
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
                ModelCapability.QUERY_GENERATION,
            )
        ):
            return requested_model_id
        return self._registry.get_default_model(
            ModelCapability.QUERY_GENERATION,
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
    def _create_run_id(
        *,
        model_id: str,
        research_space_id: str,
        question: str,
        harness_id: str,
    ) -> str:
        payload = (
            f"{harness_id.strip()}|{model_id}|{research_space_id}|{question.strip()}"
        )
        return f"graph_search:{stable_sha256_digest(payload)}"

    @staticmethod
    def _system_prompt(domain_prompt: str) -> str:
        return (
            f"{domain_prompt}\n\n"
            "Service runtime overlay:\n"
            "- Ignore any legacy tool names mentioned above if they are not visible in "
            "the runtime skill panel.\n"
            "- Use only the currently active tools exposed by runtime skills.\n"
            "- load_skill(skill_name=...) loads one named runtime skill, not an "
            "individual tool.\n"
            "- Never invent hidden tools, extra evidence IDs, or graph writes.\n"
        )

    @staticmethod
    def _request_prompt(request: HarnessGraphSearchRequest) -> str:
        curation_statuses = (
            ", ".join(request.curation_statuses) if request.curation_statuses else "ALL"
        )
        return (
            "REQUEST CONTEXT\n"
            "---\n"
            f"QUESTION: {request.question}\n"
            f"RESEARCH SPACE ID: {request.research_space_id}\n"
            f"MAX DEPTH: {request.max_depth}\n"
            f"TOP K: {request.top_k}\n"
            f"CURATION STATUSES: {curation_statuses}\n"
            f"INCLUDE EVIDENCE CHAINS: {request.include_evidence_chains}\n"
            "Return a valid GraphSearchContract.\n"
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
        request: HarnessGraphSearchRequest,
        *,
        decision: Literal["fallback", "escalate"],
        reason: str,
        agent_run_id: str | None,
    ) -> GraphSearchContract:
        return GraphSearchContract(
            decision=decision,
            confidence_score=0.35 if decision == "fallback" else 0.05,
            rationale=reason,
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"graph-search:{request.research_space_id}",
                    excerpt=reason,
                    relevance=0.4 if decision == "fallback" else 0.1,
                ),
            ],
            research_space_id=request.research_space_id,
            original_query=request.question,
            interpreted_intent=request.question,
            query_plan_summary="Graph-search harness fallback.",
            total_results=0,
            results=[],
            executed_path="agent_fallback",
            warnings=[reason],
            agent_run_id=agent_run_id,
        )


__all__ = [
    "HarnessGraphSearchRequest",
    "HarnessGraphSearchResult",
    "HarnessGraphSearchRunner",
]
