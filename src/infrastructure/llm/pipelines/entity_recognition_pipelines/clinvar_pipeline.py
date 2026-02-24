"""ClinVar entity-recognition pipeline."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flujo import Flujo, Pipeline, Step
from flujo.domain.agent_result import FlujoAgentResult
from flujo.domain.dsl import ConditionalStep, GranularStep, HumanInTheLoopStep
from flujo.domain.models import UsageLimits as FlujoUsageLimits

from src.domain.agents.contexts.entity_recognition_context import (
    EntityRecognitionContext,
)
from src.domain.agents.contracts import EntityRecognitionContract
from src.infrastructure.llm.config.governance import GovernanceConfig, UsageLimits
from src.infrastructure.llm.factories.entity_recognition_agent_factory import (
    create_entity_recognition_agent_for_source,
)
from src.infrastructure.llm.prompts.entity_recognition import (
    CLINVAR_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT,
    CLINVAR_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT,
)

if TYPE_CHECKING:
    from flujo.state.backends.base import StateBackend

logger = logging.getLogger(__name__)


def _unwrap_agent_output(output: object) -> object:
    if isinstance(output, FlujoAgentResult):
        return output.output
    return output


def _check_recognition_confidence(
    output: object,
    _ctx: EntityRecognitionContext | None,
) -> str:
    governance = GovernanceConfig.from_environment()
    threshold = governance.confidence_threshold
    resolved_output = _unwrap_agent_output(output)
    decision = getattr(resolved_output, "decision", None)
    confidence_score = getattr(resolved_output, "confidence_score", 0.0)
    evidence = getattr(resolved_output, "evidence", [])

    if decision == "escalate":
        return "escalate"
    if governance.require_evidence and not evidence:
        return "escalate"
    if governance.needs_human_review(confidence_score):
        return "escalate"
    return "proceed" if confidence_score >= threshold else "escalate"


def _check_requires_dictionary_policy_step(
    output: object,
    _ctx: EntityRecognitionContext | None,
) -> str:
    resolved_output = _unwrap_agent_output(output)

    decision: str | None = None
    created_payloads: list[object] = []
    if isinstance(resolved_output, dict):
        raw_decision = resolved_output.get("decision")
        if isinstance(raw_decision, str):
            decision = raw_decision
        created_payloads = [
            resolved_output.get("created_definitions"),
            resolved_output.get("created_synonyms"),
            resolved_output.get("created_entity_types"),
            resolved_output.get("created_relation_types"),
            resolved_output.get("created_relation_constraints"),
        ]
    else:
        raw_decision = getattr(resolved_output, "decision", None)
        if isinstance(raw_decision, str):
            decision = raw_decision
        created_payloads = [
            getattr(resolved_output, "created_definitions", None),
            getattr(resolved_output, "created_synonyms", None),
            getattr(resolved_output, "created_entity_types", None),
            getattr(resolved_output, "created_relation_types", None),
            getattr(resolved_output, "created_relation_constraints", None),
        ]

    if decision == "escalate":
        return "skip_policy"
    created_proposal_count = sum(
        len(payload) for payload in created_payloads if isinstance(payload, list)
    )
    return "run_policy" if created_proposal_count > 0 else "skip_policy"


async def _normalize_discovery_output(output: object) -> dict[str, object]:
    resolved_output = _unwrap_agent_output(output)
    if isinstance(resolved_output, dict):
        return {str(key): value for key, value in resolved_output.items()}
    dump_callable = getattr(resolved_output, "model_dump", None)
    if callable(dump_callable):
        dumped_output = dump_callable(mode="json")
        if isinstance(dumped_output, dict):
            return {str(key): value for key, value in dumped_output.items()}
    return {}


async def _prepare_dictionary_policy_input(output: object) -> dict[str, object]:
    return await _normalize_discovery_output(output)


async def _normalize_policy_output(output: object) -> object:
    return _unwrap_agent_output(output)


async def _rehydrate_entity_recognition_contract(output: object) -> object:
    resolved_output = _unwrap_agent_output(output)
    if isinstance(resolved_output, EntityRecognitionContract):
        return resolved_output
    if isinstance(resolved_output, dict):
        return EntityRecognitionContract.model_validate(resolved_output)
    return resolved_output


def create_clinvar_entity_recognition_pipeline(  # noqa: PLR0913
    state_backend: StateBackend,
    *,
    model: str | None = None,
    use_governance: bool = True,
    usage_limits: UsageLimits | None = None,
    discovery_tools: list[object] | None = None,
    policy_tools: list[object] | None = None,
    tools: list[object] | None = None,
) -> Flujo[str, EntityRecognitionContract, EntityRecognitionContext]:
    """Create a ClinVar entity-recognition pipeline."""
    governance = GovernanceConfig.from_environment()
    limits = usage_limits or governance.usage_limits
    shared_tools = tools
    discovery_toolset = discovery_tools if discovery_tools is not None else shared_tools
    policy_toolset = policy_tools if policy_tools is not None else shared_tools
    discovery_agent = create_entity_recognition_agent_for_source(
        "clinvar",
        model=model,
        system_prompt=CLINVAR_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT,
        tools=discovery_toolset,
    )
    policy_agent = create_entity_recognition_agent_for_source(
        "clinvar",
        model=model,
        system_prompt=CLINVAR_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT,
        tools=policy_toolset,
    )

    steps: list[
        Step[object, object] | GranularStep | ConditionalStep[EntityRecognitionContext]
    ] = [
        GranularStep(
            name="discover_clinvar_entities",
            agent=discovery_agent,
            enforce_idempotency=True,
            history_max_tokens=8192,
        ),
        Step.from_callable(
            _normalize_discovery_output,
            name="normalize_clinvar_discovery_output",
        ),
        ConditionalStep(
            name="entity_recognition_dictionary_policy_gate",
            condition_callable=_check_requires_dictionary_policy_step,
            branches={
                "run_policy": Pipeline(
                    steps=[
                        Step.from_callable(
                            _prepare_dictionary_policy_input,
                            name="prepare_clinvar_dictionary_policy_input",
                        ),
                        Step(
                            name="apply_clinvar_dictionary_policy",
                            agent=policy_agent,
                        ),
                        Step.from_callable(
                            _normalize_policy_output,
                            name="normalize_clinvar_dictionary_policy_output",
                        ),
                    ],
                ),
                "skip_policy": Pipeline(
                    steps=[
                        Step.from_callable(
                            _rehydrate_entity_recognition_contract,
                            name="restore_clinvar_entity_recognition_contract",
                        ),
                    ],
                ),
            },
        ),
    ]

    if use_governance:
        steps.append(
            ConditionalStep(
                name="entity_recognition_confidence_gate",
                condition_callable=_check_recognition_confidence,
                branches={
                    "escalate": Pipeline(
                        steps=[
                            HumanInTheLoopStep(
                                name="entity_recognition_human_review",
                                message_for_user=(
                                    "Entity-recognition confidence is below threshold. "
                                    "Please review before writing to the graph."
                                ),
                            ),
                        ],
                    ),
                    "proceed": Pipeline(steps=[]),
                },
            ),
        )

    return Flujo(
        Pipeline(steps=steps),
        context_model=EntityRecognitionContext,
        state_backend=state_backend,
        persist_state=True,
        usage_limits=_to_flujo_usage_limits(limits),
    )


def _to_flujo_usage_limits(limits: UsageLimits) -> FlujoUsageLimits:
    return FlujoUsageLimits(
        total_cost_usd_limit=limits.total_cost_usd,
        total_tokens_limit=limits.max_tokens,
    )
