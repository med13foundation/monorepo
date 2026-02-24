"""ClinVar extraction pipeline."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from flujo import Flujo, Pipeline, Step
from flujo.domain.agent_result import FlujoAgentResult
from flujo.domain.dsl import ConditionalStep, HumanInTheLoopStep
from flujo.domain.models import UsageLimits as FlujoUsageLimits

from src.domain.agents.contexts.extraction_context import ExtractionContext
from src.infrastructure.llm.config.governance import GovernanceConfig, UsageLimits
from src.infrastructure.llm.factories.extraction_agent_factory import (
    create_extraction_agent_for_source,
)
from src.infrastructure.llm.prompts.extraction.clinvar import (
    CLINVAR_EXTRACTION_DISCOVERY_SYSTEM_PROMPT,
    CLINVAR_EXTRACTION_SYNTHESIS_SYSTEM_PROMPT,
)

if TYPE_CHECKING:
    from flujo.state.backends.base import StateBackend

    from src.domain.agents.contracts.extraction import ExtractionContract

logger = logging.getLogger(__name__)

_MAX_DISCOVERY_OBSERVATIONS = 120
_MAX_DISCOVERY_RELATIONS = 120
_MAX_DISCOVERY_REJECTIONS = 200
_MAX_DISCOVERY_EVIDENCE = 120
_MAX_DISCOVERY_STRING_CHARS = 320
_MAX_JSON_COLLECTION_ITEMS = 24
_MAX_JSON_OBJECT_FIELDS = 24
_MAX_JSON_DEPTH = 3
_MAX_SYNTHESIS_INPUT_CHARS = 20000
_MIN_SYNTHESIS_COLLECTION_ITEMS = 8


def _unwrap_agent_output(output: object) -> object:
    if isinstance(output, FlujoAgentResult):
        return output.output
    return output


def _truncate_text(value: object, *, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized[:limit]


def _compact_json_value(value: object, *, depth: int = 0) -> object:
    compact_value: object
    if isinstance(value, str):
        compact_value = value.strip()[:_MAX_DISCOVERY_STRING_CHARS]
    elif isinstance(value, dict):
        if depth >= _MAX_JSON_DEPTH:
            compact_value = {}
        else:
            compact_dict: dict[str, object] = {}
            for index, (key, item_value) in enumerate(value.items()):
                if index >= _MAX_JSON_OBJECT_FIELDS:
                    break
                compact_dict[str(key)] = _compact_json_value(
                    item_value,
                    depth=depth + 1,
                )
            compact_value = compact_dict
    elif isinstance(value, list):
        if depth >= _MAX_JSON_DEPTH:
            compact_value = []
        else:
            compact_value = [
                _compact_json_value(item, depth=depth + 1)
                for item in value[:_MAX_JSON_COLLECTION_ITEMS]
            ]
    elif isinstance(value, int | float | bool) or value is None:
        compact_value = value
    else:
        compact_value = str(value)[:_MAX_DISCOVERY_STRING_CHARS]
    return compact_value


def _payload_size_chars(payload: dict[str, object]) -> int:
    return len(json.dumps(payload, ensure_ascii=True, default=str))


def _shrink_discovery_list(discovery_output: dict[str, object], key: str) -> None:
    list_value = discovery_output.get(key)
    if not isinstance(list_value, list):
        return
    if len(list_value) <= _MIN_SYNTHESIS_COLLECTION_ITEMS:
        return
    truncated_size = max(_MIN_SYNTHESIS_COLLECTION_ITEMS, len(list_value) // 2)
    discovery_output[key] = list_value[:truncated_size]


def _trim_payload_for_synthesis_budget(payload: dict[str, object]) -> dict[str, object]:
    record_snapshot_raw = payload.get("record_snapshot")
    record_snapshot = (
        {
            str(key): _compact_json_value(value)
            for key, value in record_snapshot_raw.items()
        }
        if isinstance(record_snapshot_raw, dict)
        else {}
    )
    discovery_output_raw = payload.get("discovery_output")
    discovery_output = (
        {
            str(key): _compact_json_value(value)
            for key, value in discovery_output_raw.items()
        }
        if isinstance(discovery_output_raw, dict)
        else {}
    )
    compact_payload: dict[str, object] = {
        "source_type": payload.get("source_type"),
        "document_id": payload.get("document_id"),
        "shadow_mode": payload.get("shadow_mode"),
        "record_snapshot": record_snapshot,
        "discovery_output": discovery_output,
    }
    if _payload_size_chars(compact_payload) > _MAX_SYNTHESIS_INPUT_CHARS:
        for _ in range(8):
            if _payload_size_chars(compact_payload) <= _MAX_SYNTHESIS_INPUT_CHARS:
                break
            for key in ("evidence", "rejected_facts", "relations", "observations"):
                _shrink_discovery_list(discovery_output, key)
                if _payload_size_chars(compact_payload) <= _MAX_SYNTHESIS_INPUT_CHARS:
                    break
    if _payload_size_chars(compact_payload) > _MAX_SYNTHESIS_INPUT_CHARS:
        rationale_value = discovery_output.get("rationale")
        if isinstance(rationale_value, str):
            discovery_output["rationale"] = rationale_value[:300]
    if _payload_size_chars(compact_payload) > _MAX_SYNTHESIS_INPUT_CHARS:
        discovery_output["evidence"] = []
    if _payload_size_chars(compact_payload) > _MAX_SYNTHESIS_INPUT_CHARS:
        discovery_output["rejected_facts"] = []
    return compact_payload


def _serialize_discovery_output(output: object) -> dict[str, object]:
    resolved = _unwrap_agent_output(output)
    if isinstance(resolved, dict):
        raw_payload = {str(key): value for key, value in resolved.items()}
    else:
        dump_callable = getattr(resolved, "model_dump", None)
        if callable(dump_callable):
            dumped = dump_callable(mode="json")
            if isinstance(dumped, dict):
                raw_payload = {str(key): value for key, value in dumped.items()}
            else:
                raw_payload = {}
        else:
            raw_payload = {}

    observations = raw_payload.get("observations")
    relations = raw_payload.get("relations")
    rejected_facts = raw_payload.get("rejected_facts")
    evidence = raw_payload.get("evidence")

    compact_payload: dict[str, object] = {
        "decision": raw_payload.get("decision"),
        "confidence_score": raw_payload.get("confidence_score"),
        "rationale": _truncate_text(raw_payload.get("rationale"), limit=1200) or "",
        "source_type": raw_payload.get("source_type"),
        "document_id": raw_payload.get("document_id"),
        "shadow_mode": raw_payload.get("shadow_mode"),
        "observations": (
            [
                _compact_json_value(item)
                for item in observations[:_MAX_DISCOVERY_OBSERVATIONS]
            ]
            if isinstance(observations, list)
            else []
        ),
        "relations": (
            [_compact_json_value(item) for item in relations[:_MAX_DISCOVERY_RELATIONS]]
            if isinstance(relations, list)
            else []
        ),
        "rejected_facts": (
            [
                _compact_json_value(item)
                for item in rejected_facts[:_MAX_DISCOVERY_REJECTIONS]
            ]
            if isinstance(rejected_facts, list)
            else []
        ),
        "evidence": (
            [_compact_json_value(item) for item in evidence[:_MAX_DISCOVERY_EVIDENCE]]
            if isinstance(evidence, list)
            else []
        ),
    }
    return compact_payload


def _build_clinvar_record_snapshot(context: ExtractionContext) -> dict[str, object]:
    raw_record = context.raw_record
    snapshot: dict[str, object] = {}
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
        if value is not None:
            snapshot[field] = value
    return snapshot


async def _prepare_clinvar_synthesis_input(
    output: object,
    /,
    *,
    context: ExtractionContext,
) -> str:
    payload = {
        "source_type": context.source_type,
        "document_id": context.document_id,
        "shadow_mode": context.shadow_mode,
        "record_snapshot": _build_clinvar_record_snapshot(context),
        "discovery_output": _serialize_discovery_output(output),
    }
    return json.dumps(
        _trim_payload_for_synthesis_budget(payload),
        ensure_ascii=True,
        default=str,
    )


def _check_extraction_confidence(
    output: object,
    _ctx: ExtractionContext | None,
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


def create_clinvar_extraction_pipeline(
    state_backend: StateBackend,
    *,
    model: str | None = None,
    use_governance: bool = True,
    usage_limits: UsageLimits | None = None,
    tools: list[object] | None = None,
) -> Flujo[str, ExtractionContract, ExtractionContext]:
    """Create a ClinVar extraction pipeline."""
    governance = GovernanceConfig.from_environment()
    limits = usage_limits or governance.usage_limits
    discovery_agent = create_extraction_agent_for_source(
        "clinvar",
        model=model,
        system_prompt=CLINVAR_EXTRACTION_DISCOVERY_SYSTEM_PROMPT,
        tools=None,
    )
    synthesis_agent = create_extraction_agent_for_source(
        "clinvar",
        model=model,
        system_prompt=CLINVAR_EXTRACTION_SYNTHESIS_SYSTEM_PROMPT,
        tools=tools,
    )

    steps: list[Step[object, object] | ConditionalStep[ExtractionContext]] = [
        Step(
            name="discover_clinvar_extraction_candidates",
            agent=discovery_agent,
        ),
        Step.from_callable(
            _prepare_clinvar_synthesis_input,
            name="prepare_clinvar_extraction_synthesis_input",
        ),
        Step(
            name="synthesize_clinvar_extraction_contract",
            agent=synthesis_agent,
        ),
    ]

    if use_governance:
        steps.append(
            ConditionalStep[ExtractionContext](
                name="extraction_confidence_gate",
                condition_callable=_check_extraction_confidence,
                branches={
                    "escalate": Pipeline(
                        steps=[
                            HumanInTheLoopStep(
                                name="extraction_human_review",
                                message_for_user=(
                                    "Extraction confidence is below threshold. "
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
        context_model=ExtractionContext,
        state_backend=state_backend,
        persist_state=True,
        usage_limits=_to_flujo_usage_limits(limits),
    )


def _to_flujo_usage_limits(limits: UsageLimits) -> FlujoUsageLimits:
    return FlujoUsageLimits(
        total_cost_usd_limit=limits.total_cost_usd,
        total_tokens_limit=limits.max_tokens,
    )
