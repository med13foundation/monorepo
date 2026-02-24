"""Focused Flujo relation-extraction smoke test with synthetic text."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import uuid4

from flujo import Flujo, Pipeline, Step
from flujo.agents import make_agent_async
from flujo.domain.agent_result import FlujoAgentResult
from flujo.domain.models import PipelineResult, StepResult
from flujo.domain.models import UsageLimits as FlujoUsageLimits
from pydantic import BaseModel, Field

from src.domain.agents.models import ModelCapability
from src.infrastructure.llm.config.governance import GovernanceConfig
from src.infrastructure.llm.config.model_registry import get_model_registry
from src.infrastructure.llm.state import get_state_backend

logger = logging.getLogger(__name__)

_DEFAULT_CHUNK_SIZE_CHARS = 4000
_DEFAULT_CHUNK_OVERLAP_CHARS = 300
_DEFAULT_MAX_CHUNKS = 12
_DEFAULT_CHARS_PER_TOKEN = 4
_DEFAULT_CHARS_PER_PAGE = 3000
_DEFAULT_SYNTHESIS_SOURCE_SLICE_CHARS = 6000
_DEFAULT_TRACE_PREVIEW_CHARS = 1200

_DEFAULT_TEXT = """
MED13 is a subunit of the Mediator complex.
MED25 physically interacts with MED13 and MED16.
The Mediator complex links DNA-bound transcription factors to RNA polymerase II.
MED13 is required for proper transcriptional regulation in plants.
""".strip()

_DISCOVERY_PROMPT = """
You are a focused relation-discovery agent.

Task:
- Read the provided text and extract explicit relation triples only.
- Use only these predicates: INTERACTS_WITH, PART_OF, LINKS_TO, REGULATES.
- Keep entity labels short and concrete (e.g., MED13, MED25, MED16, Mediator complex).
- If a relation is uncertain, place it in rejected instead of relations.

Output:
- Return FocusedDiscoveryContract.
""".strip()

_SYNTHESIS_PROMPT = """
You are a focused relation-synthesis agent.

Task:
- Input contains:
  - SOURCE_TEXT
  - DISCOVERY_JSON (candidate output from discovery step)
- Normalize predicate labels to one of:
  INTERACTS_WITH, PART_OF, LINKS_TO, REGULATES.
- Deduplicate relations.
- Keep only relations with confidence >= 0.4.
- Preserve rejected reasons.

Output:
- Return FocusedSynthesisContract.
""".strip()

_EXPECTED_RELATIONS: tuple[tuple[str, str, str], ...] = (
    ("MED25", "INTERACTS_WITH", "MED13"),
    ("MED13", "PART_OF", "Mediator complex"),
)


class FocusedRelation(BaseModel):
    """Single relation triple for focused validation."""

    source: str = Field(..., min_length=1, max_length=128)
    predicate: str = Field(..., min_length=1, max_length=64)
    target: str = Field(..., min_length=1, max_length=128)
    evidence: str = Field(default="", max_length=500)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class FocusedDiscoveryContract(BaseModel):
    """Discovery-stage relation output."""

    decision: Literal["generated", "escalate"] = "generated"
    relations: list[FocusedRelation] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)
    rationale: str = ""


class FocusedSynthesisContract(BaseModel):
    """Synthesis-stage relation output."""

    decision: Literal["generated", "escalate"] = "generated"
    relations: list[FocusedRelation] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)
    rationale: str = ""


class FocusedRunContext(BaseModel):
    """Minimal context for focused Flujo runs."""

    scenario: str = "focused_relation_smoke"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a focused two-step Flujo relation extraction test on a synthetic text."
        ),
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model override (e.g., openai:gpt-5-mini).",
    )
    parser.add_argument(
        "--text-file",
        type=Path,
        default=None,
        help="Optional input text file. Defaults to built-in synthetic text.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON report output path.",
    )
    parser.add_argument(
        "--chunk-size-chars",
        type=int,
        default=_DEFAULT_CHUNK_SIZE_CHARS,
        help=f"Chunk size in characters (default: {_DEFAULT_CHUNK_SIZE_CHARS}).",
    )
    parser.add_argument(
        "--chunk-overlap-chars",
        type=int,
        default=_DEFAULT_CHUNK_OVERLAP_CHARS,
        help=(
            f"Chunk overlap in characters (default: {_DEFAULT_CHUNK_OVERLAP_CHARS})."
        ),
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=_DEFAULT_MAX_CHUNKS,
        help=f"Maximum number of chunks to process (default: {_DEFAULT_MAX_CHUNKS}).",
    )
    parser.add_argument(
        "--chars-per-token",
        type=int,
        default=_DEFAULT_CHARS_PER_TOKEN,
        help=(
            "Character-to-token estimation ratio for diagnostics "
            f"(default: {_DEFAULT_CHARS_PER_TOKEN})."
        ),
    )
    parser.add_argument(
        "--chars-per-page",
        type=int,
        default=_DEFAULT_CHARS_PER_PAGE,
        help=(
            "Character-to-page estimation ratio for diagnostics "
            f"(default: {_DEFAULT_CHARS_PER_PAGE})."
        ),
    )
    parser.add_argument(
        "--synthesis-source-slice-chars",
        type=int,
        default=_DEFAULT_SYNTHESIS_SOURCE_SLICE_CHARS,
        help=(
            "Maximum source-text chars included in synthesis input "
            f"(default: {_DEFAULT_SYNTHESIS_SOURCE_SLICE_CHARS})."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--provider-debug",
        action="store_true",
        help="Enable detailed provider/transport debug logs (openai/httpx/httpcore).",
    )
    parser.add_argument(
        "--agent-timeout-seconds",
        type=int,
        default=None,
        help=(
            "Per-agent timeout in seconds. "
            "Defaults to model timeout from artana.toml."
        ),
    )
    parser.add_argument(
        "--agent-max-retries",
        type=int,
        default=None,
        help=(
            "Max retries per agent invocation. "
            "Defaults to model max_retries from artana.toml."
        ),
    )
    parser.add_argument(
        "--trace-preview-chars",
        type=int,
        default=_DEFAULT_TRACE_PREVIEW_CHARS,
        help=(
            "Max chars of prompt/input previews captured into report "
            f"(default: {_DEFAULT_TRACE_PREVIEW_CHARS})."
        ),
    )
    return parser.parse_args()


def _configure_logging(*, verbose: bool, provider_debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    if provider_debug:
        os.environ.setdefault("OPENAI_LOG", "debug")
        for logger_name in ("openai", "httpx", "httpcore", "pydantic_ai", "flujo"):
            logging.getLogger(logger_name).setLevel(logging.DEBUG)


def _resolve_model_id(override: str | None) -> str:
    registry = get_model_registry()
    if override:
        return override
    return registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION).model_id


def _build_input_text(text: str) -> str:
    return f"TEXT:\n{text}"


def _extract_discovery_contract(output: object) -> FocusedDiscoveryContract | None:
    if isinstance(output, FocusedDiscoveryContract):
        return output
    if isinstance(output, FlujoAgentResult) and isinstance(
        output.output,
        FocusedDiscoveryContract,
    ):
        return output.output
    return None


def _extract_synthesis_contract(output: object) -> FocusedSynthesisContract | None:
    if isinstance(output, FocusedSynthesisContract):
        return output
    if isinstance(output, FlujoAgentResult) and isinstance(
        output.output,
        FocusedSynthesisContract,
    ):
        return output.output
    return None


def _normalize_relation_key(relation: FocusedRelation) -> tuple[str, str, str]:
    source = relation.source.strip()
    predicate = relation.predicate.strip().upper()
    target = relation.target.strip()
    return (source, predicate, target)


def _coerce_positive_int(value: int, *, fallback: int, minimum: int = 1) -> int:
    if value < minimum:
        return max(fallback, minimum)
    return value


def _estimate_text_metrics(
    text: str,
    *,
    chars_per_token: int,
    chars_per_page: int,
) -> dict[str, int | float]:
    char_count = len(text)
    word_count = len(text.split())
    safe_chars_per_token = _coerce_positive_int(
        chars_per_token,
        fallback=_DEFAULT_CHARS_PER_TOKEN,
    )
    safe_chars_per_page = _coerce_positive_int(
        chars_per_page,
        fallback=_DEFAULT_CHARS_PER_PAGE,
    )
    estimated_tokens = (
        math.ceil(char_count / safe_chars_per_token) if char_count > 0 else 0
    )
    estimated_pages = (
        round(char_count / safe_chars_per_page, 2) if char_count > 0 else 0.0
    )
    return {
        "char_count": char_count,
        "word_count": word_count,
        "estimated_tokens": estimated_tokens,
        "estimated_pages": estimated_pages,
    }


def _build_text_chunks(  # noqa: PLR0913
    text: str,
    *,
    chunk_size_chars: int,
    chunk_overlap_chars: int,
    max_chunks: int,
    chars_per_token: int,
    chars_per_page: int,
) -> list[dict[str, object]]:
    normalized_text = text.strip()
    if not normalized_text:
        return []

    safe_chunk_size = _coerce_positive_int(
        chunk_size_chars,
        fallback=_DEFAULT_CHUNK_SIZE_CHARS,
        minimum=256,
    )
    safe_overlap = max(
        0,
        min(
            chunk_overlap_chars,
            safe_chunk_size - 1,
        ),
    )
    safe_max_chunks = _coerce_positive_int(
        max_chunks,
        fallback=_DEFAULT_MAX_CHUNKS,
    )
    total_length = len(normalized_text)
    cursor = 0
    chunk_index = 0
    chunks: list[dict[str, object]] = []

    while cursor < total_length and len(chunks) < safe_max_chunks:
        end = min(cursor + safe_chunk_size, total_length)
        if end < total_length:
            candidate_break = normalized_text.rfind(" ", cursor, end)
            if candidate_break > cursor + (safe_chunk_size // 2):
                end = candidate_break

        chunk_text = normalized_text[cursor:end].strip()
        if not chunk_text:
            cursor = max(end + 1, cursor + 1)
            continue

        metrics = _estimate_text_metrics(
            chunk_text,
            chars_per_token=chars_per_token,
            chars_per_page=chars_per_page,
        )
        chunks.append(
            {
                "chunk_index": chunk_index,
                "start_char": cursor,
                "end_char": end,
                "text": chunk_text,
                **metrics,
            },
        )
        chunk_index += 1

        if end >= total_length:
            break
        cursor = max(end - safe_overlap, cursor + 1)

    return chunks


def _serialize_object(value: object) -> object:
    if isinstance(value, FlujoAgentResult):
        return _serialize_object(value.output)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _serialize_object(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_serialize_object(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _snapshot_step_result(step_result: StepResult) -> dict[str, object]:
    error_value = getattr(step_result, "error", None)
    return {
        "name": str(getattr(step_result, "name", "unknown")),
        "status": str(getattr(step_result, "status", "unknown")),
        "error": str(error_value) if error_value is not None else None,
        "output": _serialize_object(getattr(step_result, "output", None)),
    }


def _snapshot_pipeline_result(
    pipeline_result: PipelineResult[FocusedRunContext],
) -> dict[str, object]:
    history: list[dict[str, object]] = []
    step_history = getattr(pipeline_result, "step_history", [])
    if isinstance(step_history, list):
        history.extend(
            _snapshot_step_result(step_result)
            for step_result in step_history
            if isinstance(step_result, StepResult)
        )
    return {
        "status": str(getattr(pipeline_result, "status", "unknown")),
        "step_history": history,
    }


def _extract_event_error(
    *,
    step_events: list[dict[str, object]],
    pipeline_events: list[dict[str, object]],
) -> str | None:
    for step in step_events:
        status = str(step.get("status", "")).lower()
        error = step.get("error")
        if status in {"failed", "error"}:
            if isinstance(error, str) and error.strip():
                return error.strip()
            return f"Step {step.get('name', 'unknown')} failed without explicit error."

    for pipeline in pipeline_events:
        status = str(pipeline.get("status", "")).lower()
        if status in {"failed", "error"}:
            return "Pipeline failed without explicit exception details."
    return None


def _classify_error(error: str | None) -> str | None:
    if error is None:
        return None
    lowered = error.lower()
    if "timeout" in lowered or "timed out" in lowered or "deadline" in lowered:
        return "timeout"
    if "quota" in lowered or "rate limit" in lowered or "429" in lowered:
        return "quota_or_rate_limit"
    if "validation" in lowered or "schema" in lowered:
        return "output_validation"
    if "request_limit" in lowered or "tool_calls_limit" in lowered:
        return "usage_limit"
    return "runtime"


def _merge_discovery_contracts(
    contracts: list[FocusedDiscoveryContract],
) -> FocusedDiscoveryContract | None:
    if not contracts:
        return None

    relation_by_key: dict[tuple[str, str, str], FocusedRelation] = {}
    rejected: list[str] = []
    rationale_parts: list[str] = []

    for contract in contracts:
        if contract.rationale and contract.rationale not in rationale_parts:
            rationale_parts.append(contract.rationale)
        for reason in contract.rejected:
            if reason not in rejected:
                rejected.append(reason)
        for relation in contract.relations:
            relation_key = _normalize_relation_key(relation)
            existing = relation_by_key.get(relation_key)
            if existing is None or relation.confidence > existing.confidence:
                relation_by_key[relation_key] = relation

    merged_relations = list(relation_by_key.values())
    merged_decision: Literal["generated", "escalate"] = (
        "generated" if merged_relations or rejected else "escalate"
    )
    merged_rationale = " | ".join(rationale_parts[:5])[:2000]
    return FocusedDiscoveryContract(
        decision=merged_decision,
        relations=merged_relations,
        rejected=rejected,
        rationale=merged_rationale,
    )


def _build_discovery_input(
    *,
    chunk_text: str,
    chunk_index: int,
    chunk_total: int,
    start_char: int,
    end_char: int,
) -> str:
    return (
        "TEXT_CHUNK_METADATA:\n"
        f"- chunk_index: {chunk_index}\n"
        f"- chunk_total: {chunk_total}\n"
        f"- start_char: {start_char}\n"
        f"- end_char: {end_char}\n\n"
        "TEXT:\n"
        f"{chunk_text}"
    )


def _build_synthesis_input(
    *,
    source_text: str,
    discovery_payload: str,
    source_slice_chars: int,
) -> str:
    safe_slice = _coerce_positive_int(
        source_slice_chars,
        fallback=_DEFAULT_SYNTHESIS_SOURCE_SLICE_CHARS,
    )
    source_excerpt = source_text[:safe_slice]
    return (
        "SOURCE_TEXT:\n" + source_excerpt + "\n\nDISCOVERY_JSON:\n" + discovery_payload
    )


async def _run_focused_test(  # noqa: PLR0912, PLR0913, PLR0915
    *,
    model_id: str,
    text: str,
    chunk_size_chars: int,
    chunk_overlap_chars: int,
    max_chunks: int,
    chars_per_token: int,
    chars_per_page: int,
    synthesis_source_slice_chars: int,
    agent_timeout_seconds: int,
    agent_max_retries: int,
    provider_debug: bool,
    trace_preview_chars: int,
) -> tuple[FocusedSynthesisContract | None, str | None, dict[str, object]]:
    state_backend = get_state_backend()
    governance = GovernanceConfig.from_environment()
    model_registry = get_model_registry()
    model_spec = model_registry.get_model(model_id)
    reasoning_settings = model_spec.get_reasoning_settings()
    limits = governance.usage_limits
    flujo_limits = FlujoUsageLimits(
        total_cost_usd_limit=limits.total_cost_usd,
        total_tokens_limit=limits.max_tokens,
    )
    safe_trace_preview_chars = _coerce_positive_int(
        trace_preview_chars,
        fallback=_DEFAULT_TRACE_PREVIEW_CHARS,
        minimum=64,
    )
    prompt_metrics = {
        "discovery_prompt_chars": len(_DISCOVERY_PROMPT),
        "discovery_prompt_est_tokens": math.ceil(
            len(_DISCOVERY_PROMPT)
            / _coerce_positive_int(
                chars_per_token,
                fallback=_DEFAULT_CHARS_PER_TOKEN,
            ),
        ),
        "synthesis_prompt_chars": len(_SYNTHESIS_PROMPT),
        "synthesis_prompt_est_tokens": math.ceil(
            len(_SYNTHESIS_PROMPT)
            / _coerce_positive_int(
                chars_per_token,
                fallback=_DEFAULT_CHARS_PER_TOKEN,
            ),
        ),
        "discovery_schema_chars": len(
            json.dumps(FocusedDiscoveryContract.model_json_schema(), ensure_ascii=True),
        ),
        "synthesis_schema_chars": len(
            json.dumps(FocusedSynthesisContract.model_json_schema(), ensure_ascii=True),
        ),
    }

    text_metrics = _estimate_text_metrics(
        text,
        chars_per_token=chars_per_token,
        chars_per_page=chars_per_page,
    )
    chunks = _build_text_chunks(
        text,
        chunk_size_chars=chunk_size_chars,
        chunk_overlap_chars=chunk_overlap_chars,
        max_chunks=max_chunks,
        chars_per_token=chars_per_token,
        chars_per_page=chars_per_page,
    )
    if not chunks:
        chunks = [
            {
                "chunk_index": 0,
                "start_char": 0,
                "end_char": len(text),
                "text": text,
                **text_metrics,
            },
        ]

    logger.info(
        (
            "Focused input metrics: chars=%s words=%s est_tokens=%s est_pages=%s "
            "chunk_count=%s model=%s timeout_seconds=%s retries=%s"
        ),
        text_metrics["char_count"],
        text_metrics["word_count"],
        text_metrics["estimated_tokens"],
        text_metrics["estimated_pages"],
        len(chunks),
        model_id,
        agent_timeout_seconds,
        agent_max_retries,
    )
    for chunk in chunks:
        logger.info(
            "Chunk %s/%s chars=%s range=[%s,%s] est_tokens=%s",
            int(chunk["chunk_index"]) + 1,
            len(chunks),
            int(chunk["char_count"]),
            int(chunk["start_char"]),
            int(chunk["end_char"]),
            int(chunk["estimated_tokens"]),
        )

    discovery_agent = make_agent_async(
        model=model_id,
        system_prompt=_DISCOVERY_PROMPT,
        output_type=FocusedDiscoveryContract,
        max_retries=agent_max_retries,
        timeout=agent_timeout_seconds,
        model_settings=reasoning_settings,
    )
    synthesis_agent = make_agent_async(
        model=model_id,
        system_prompt=_SYNTHESIS_PROMPT,
        output_type=FocusedSynthesisContract,
        max_retries=agent_max_retries,
        timeout=agent_timeout_seconds,
        model_settings=reasoning_settings,
    )

    discovery_runner = Flujo(
        Pipeline(
            steps=[
                Step(
                    name="discover_relations",
                    agent=discovery_agent,
                ),
            ],
        ),
        context_model=FocusedRunContext,
        state_backend=state_backend,
        persist_state=True,
        usage_limits=flujo_limits,
    )
    synthesis_runner = Flujo(
        Pipeline(
            steps=[
                Step(
                    name="synthesize_relations",
                    agent=synthesis_agent,
                ),
            ],
        ),
        context_model=FocusedRunContext,
        state_backend=state_backend,
        persist_state=True,
        usage_limits=flujo_limits,
    )

    discovery_contracts: list[FocusedDiscoveryContract] = []
    discovery_trace: list[dict[str, object]] = []
    discovery_run_ids: list[str] = []

    for chunk in chunks:
        chunk_run_id = f"focused_relation_discovery_{uuid4().hex}"
        discovery_run_ids.append(chunk_run_id)
        chunk_index = int(chunk["chunk_index"])
        chunk_start = int(chunk["start_char"])
        chunk_end = int(chunk["end_char"])
        chunk_text = str(chunk["text"])
        discovery_input = _build_discovery_input(
            chunk_text=chunk_text,
            chunk_index=chunk_index,
            chunk_total=len(chunks),
            start_char=chunk_start,
            end_char=chunk_end,
        )

        step_events: list[dict[str, object]] = []
        pipeline_events: list[dict[str, object]] = []
        chunk_output: FocusedDiscoveryContract | None = None
        execution_error: str | None = None
        started = perf_counter()
        discovery_input_metrics = _estimate_text_metrics(
            discovery_input,
            chars_per_token=chars_per_token,
            chars_per_page=chars_per_page,
        )
        logger.info(
            (
                "Discovery chunk %s/%s start run_id=%s input_chars=%s "
                "input_est_tokens=%s range=[%s,%s]"
            ),
            chunk_index + 1,
            len(chunks),
            chunk_run_id,
            discovery_input_metrics["char_count"],
            discovery_input_metrics["estimated_tokens"],
            chunk_start,
            chunk_end,
        )

        try:
            async for item in discovery_runner.run_async(
                discovery_input,
                run_id=chunk_run_id,
                initial_context_data=FocusedRunContext().model_dump(mode="json"),
            ):
                if isinstance(item, StepResult):
                    step_events.append(_snapshot_step_result(item))
                    candidate = _extract_discovery_contract(item.output)
                    if candidate is not None:
                        chunk_output = candidate
                elif isinstance(item, PipelineResult):
                    pipeline_events.append(_snapshot_pipeline_result(item))
                    for step_result in reversed(item.step_history):
                        if not isinstance(step_result, StepResult):
                            continue
                        candidate = _extract_discovery_contract(step_result.output)
                        if candidate is not None:
                            chunk_output = candidate
                            break
        except Exception as exc:  # noqa: BLE001
            execution_error = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "Discovery execution failed for chunk %s/%s",
                chunk_index + 1,
                len(chunks),
            )
        if execution_error is None:
            execution_error = _extract_event_error(
                step_events=step_events,
                pipeline_events=pipeline_events,
            )

        elapsed_ms = int((perf_counter() - started) * 1000)
        if chunk_output is not None:
            discovery_contracts.append(chunk_output)

        discovery_trace.append(
            {
                "run_id": chunk_run_id,
                "chunk_index": chunk_index,
                "chunk_start": chunk_start,
                "chunk_end": chunk_end,
                "chunk_char_count": int(chunk["char_count"]),
                "chunk_estimated_tokens": int(chunk["estimated_tokens"]),
                "chunk_estimated_pages": float(chunk["estimated_pages"]),
                "chunk_text_preview": chunk_text[:safe_trace_preview_chars],
                "chunk_input_chars": int(discovery_input_metrics["char_count"]),
                "chunk_input_estimated_tokens": int(
                    discovery_input_metrics["estimated_tokens"],
                ),
                "elapsed_ms": elapsed_ms,
                "error": execution_error,
                "error_classification": _classify_error(execution_error),
                "step_events": step_events,
                "pipeline_events": pipeline_events,
                "output": (
                    chunk_output.model_dump(mode="json")
                    if chunk_output is not None
                    else None
                ),
            },
        )

        logger.info(
            (
                "Discovery chunk %s/%s finished in %sms "
                "(relations=%s rejected=%s error=%s)"
            ),
            chunk_index + 1,
            len(chunks),
            elapsed_ms,
            len(chunk_output.relations) if chunk_output is not None else 0,
            len(chunk_output.rejected) if chunk_output is not None else 0,
            execution_error or "none",
        )

    merged_discovery = _merge_discovery_contracts(discovery_contracts)
    merged_discovery_count = len(discovery_contracts)
    combined_discovery_run_id = (
        "|".join(discovery_run_ids) if discovery_run_ids else None
    )
    if merged_discovery is None:
        trace_payload = {
            "text_metrics": text_metrics,
            "agent_config": {
                "model_id": model_id,
                "provider": model_spec.provider,
                "model_is_reasoning": model_spec.is_reasoning_model,
                "model_reasoning_settings": (
                    model_spec.default_reasoning_settings.model_dump(mode="json")
                    if model_spec.default_reasoning_settings is not None
                    else None
                ),
                "agent_timeout_seconds": agent_timeout_seconds,
                "agent_max_retries": agent_max_retries,
                "provider_debug_enabled": provider_debug,
                "governance_usage_limits": {
                    "total_cost_usd_limit": limits.total_cost_usd,
                    "max_tokens_limit": limits.max_tokens,
                },
                "flujo_usage_limits": {
                    "total_cost_usd_limit": flujo_limits.total_cost_usd_limit,
                    "total_tokens_limit": flujo_limits.total_tokens_limit,
                },
            },
            "prompt_diagnostics": prompt_metrics,
            "chunking": {
                "chunk_size_chars": chunk_size_chars,
                "chunk_overlap_chars": chunk_overlap_chars,
                "max_chunks": max_chunks,
                "processed_chunks": len(chunks),
                "truncated": (
                    bool(chunks) and int(chunks[-1]["end_char"]) < len(text.strip())
                ),
            },
            "discovery": {
                "successful_chunk_contracts": merged_discovery_count,
                "runs": discovery_trace,
                "merged_output": None,
            },
            "synthesis": None,
        }
        return None, combined_discovery_run_id, trace_payload

    logger.info(
        ("Merged discovery output: successful_chunks=%s relations=%s rejected=%s"),
        merged_discovery_count,
        len(merged_discovery.relations),
        len(merged_discovery.rejected),
    )

    synthesis_run_id = f"focused_relation_synthesis_{uuid4().hex}"
    discovery_payload = json.dumps(
        merged_discovery.model_dump(mode="json"),
        ensure_ascii=True,
    )
    synthesis_input = _build_synthesis_input(
        source_text=text,
        discovery_payload=discovery_payload,
        source_slice_chars=synthesis_source_slice_chars,
    )

    final_output: FocusedSynthesisContract | None = None
    synthesis_step_events: list[dict[str, object]] = []
    synthesis_pipeline_events: list[dict[str, object]] = []
    synthesis_error: str | None = None
    synthesis_started = perf_counter()
    synthesis_input_metrics = _estimate_text_metrics(
        synthesis_input,
        chars_per_token=chars_per_token,
        chars_per_page=chars_per_page,
    )
    logger.info(
        "Synthesis start run_id=%s input_chars=%s input_est_tokens=%s",
        synthesis_run_id,
        synthesis_input_metrics["char_count"],
        synthesis_input_metrics["estimated_tokens"],
    )
    try:
        async for item in synthesis_runner.run_async(
            synthesis_input,
            run_id=synthesis_run_id,
            initial_context_data=FocusedRunContext().model_dump(mode="json"),
        ):
            if isinstance(item, StepResult):
                synthesis_step_events.append(_snapshot_step_result(item))
                candidate = _extract_synthesis_contract(item.output)
                if candidate is not None:
                    final_output = candidate
            elif isinstance(item, PipelineResult):
                synthesis_pipeline_events.append(_snapshot_pipeline_result(item))
                for step_result in reversed(item.step_history):
                    if not isinstance(step_result, StepResult):
                        continue
                    candidate = _extract_synthesis_contract(step_result.output)
                    if candidate is not None:
                        final_output = candidate
                        break
    except Exception as exc:  # noqa: BLE001
        synthesis_error = f"{type(exc).__name__}: {exc}"
        logger.exception("Synthesis execution failed.")
    if synthesis_error is None:
        synthesis_error = _extract_event_error(
            step_events=synthesis_step_events,
            pipeline_events=synthesis_pipeline_events,
        )

    synthesis_elapsed_ms = int((perf_counter() - synthesis_started) * 1000)
    logger.info(
        "Synthesis finished in %sms (relations=%s rejected=%s error=%s)",
        synthesis_elapsed_ms,
        len(final_output.relations) if final_output is not None else 0,
        len(final_output.rejected) if final_output is not None else 0,
        synthesis_error or "none",
    )

    trace_payload = {
        "text_metrics": text_metrics,
        "agent_config": {
            "model_id": model_id,
            "provider": model_spec.provider,
            "model_is_reasoning": model_spec.is_reasoning_model,
            "model_reasoning_settings": (
                model_spec.default_reasoning_settings.model_dump(mode="json")
                if model_spec.default_reasoning_settings is not None
                else None
            ),
            "agent_timeout_seconds": agent_timeout_seconds,
            "agent_max_retries": agent_max_retries,
            "provider_debug_enabled": provider_debug,
            "governance_usage_limits": {
                "total_cost_usd_limit": limits.total_cost_usd,
                "max_tokens_limit": limits.max_tokens,
            },
            "flujo_usage_limits": {
                "total_cost_usd_limit": flujo_limits.total_cost_usd_limit,
                "total_tokens_limit": flujo_limits.total_tokens_limit,
            },
        },
        "prompt_diagnostics": prompt_metrics,
        "chunking": {
            "chunk_size_chars": chunk_size_chars,
            "chunk_overlap_chars": chunk_overlap_chars,
            "max_chunks": max_chunks,
            "processed_chunks": len(chunks),
            "truncated": bool(chunks)
            and int(chunks[-1]["end_char"]) < len(text.strip()),
            "chunks": [
                {key: value for key, value in chunk.items() if key != "text"}
                for chunk in chunks
            ],
        },
        "discovery": {
            "successful_chunk_contracts": merged_discovery_count,
            "runs": discovery_trace,
            "merged_output": merged_discovery.model_dump(mode="json"),
        },
        "synthesis": {
            "run_id": synthesis_run_id,
            "elapsed_ms": synthesis_elapsed_ms,
            "error": synthesis_error,
            "error_classification": _classify_error(synthesis_error),
            "source_slice_chars": synthesis_source_slice_chars,
            "input_chars": int(synthesis_input_metrics["char_count"]),
            "input_estimated_tokens": int(
                synthesis_input_metrics["estimated_tokens"],
            ),
            "input_source_excerpt": text[:safe_trace_preview_chars],
            "input_discovery_payload": json.loads(discovery_payload),
            "step_events": synthesis_step_events,
            "pipeline_events": synthesis_pipeline_events,
            "output": (
                final_output.model_dump(mode="json")
                if final_output is not None
                else None
            ),
        },
    }
    all_run_ids = discovery_run_ids + [synthesis_run_id]
    combined_run_id = "|".join(all_run_ids) if all_run_ids else None
    return final_output, combined_run_id, trace_payload


def _default_output_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("logs") / f"focused_flujo_relation_test_{timestamp}.json"


def _build_report(
    *,
    model_id: str,
    run_id: str | None,
    text: str,
    output_contract: FocusedSynthesisContract | None,
    trace: dict[str, object],
) -> dict[str, object]:
    relation_keys: list[tuple[str, str, str]] = []
    if output_contract is not None:
        relation_keys = [
            _normalize_relation_key(item) for item in output_contract.relations
        ]

    expected = list(_EXPECTED_RELATIONS)
    missing_expected = [item for item in expected if item not in relation_keys]
    passed = output_contract is not None and not missing_expected

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": model_id,
        "run_id": run_id,
        "passed": passed,
        "decision": output_contract.decision if output_contract is not None else None,
        "expected_relations": expected,
        "actual_relations": relation_keys,
        "missing_expected_relations": missing_expected,
        "rejected": output_contract.rejected if output_contract is not None else [],
        "rationale": output_contract.rationale if output_contract is not None else None,
        "input_text": text,
        "debug_trace": trace,
    }


async def _main_async(args: argparse.Namespace) -> int:
    model_id = _resolve_model_id(args.model)
    model_registry = get_model_registry()
    model_spec = model_registry.get_model(model_id)
    text = (
        args.text_file.read_text(encoding="utf-8").strip()
        if args.text_file is not None
        else _DEFAULT_TEXT
    )
    chunk_size_chars = _coerce_positive_int(
        args.chunk_size_chars,
        fallback=_DEFAULT_CHUNK_SIZE_CHARS,
        minimum=256,
    )
    chunk_overlap_chars = max(0, args.chunk_overlap_chars)
    max_chunks = _coerce_positive_int(
        args.max_chunks,
        fallback=_DEFAULT_MAX_CHUNKS,
    )
    chars_per_token = _coerce_positive_int(
        args.chars_per_token,
        fallback=_DEFAULT_CHARS_PER_TOKEN,
    )
    chars_per_page = _coerce_positive_int(
        args.chars_per_page,
        fallback=_DEFAULT_CHARS_PER_PAGE,
    )
    synthesis_source_slice_chars = _coerce_positive_int(
        args.synthesis_source_slice_chars,
        fallback=_DEFAULT_SYNTHESIS_SOURCE_SLICE_CHARS,
    )
    agent_timeout_seconds = _coerce_positive_int(
        (
            args.agent_timeout_seconds
            if isinstance(args.agent_timeout_seconds, int)
            else int(model_spec.timeout_seconds)
        ),
        fallback=int(model_spec.timeout_seconds),
    )
    agent_max_retries = _coerce_positive_int(
        (
            args.agent_max_retries
            if isinstance(args.agent_max_retries, int)
            else model_spec.max_retries
        ),
        fallback=model_spec.max_retries,
    )
    trace_preview_chars = _coerce_positive_int(
        args.trace_preview_chars,
        fallback=_DEFAULT_TRACE_PREVIEW_CHARS,
        minimum=64,
    )

    output_contract, run_id, trace = await _run_focused_test(
        model_id=model_id,
        text=text,
        chunk_size_chars=chunk_size_chars,
        chunk_overlap_chars=chunk_overlap_chars,
        max_chunks=max_chunks,
        chars_per_token=chars_per_token,
        chars_per_page=chars_per_page,
        synthesis_source_slice_chars=synthesis_source_slice_chars,
        agent_timeout_seconds=agent_timeout_seconds,
        agent_max_retries=agent_max_retries,
        provider_debug=args.provider_debug,
        trace_preview_chars=trace_preview_chars,
    )

    report = _build_report(
        model_id=model_id,
        run_id=run_id,
        text=text,
        output_contract=output_contract,
        trace=trace,
    )
    output_path = args.output or _default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    logger.info("Focused report written to: %s", output_path)
    logger.info("Focused relation test passed: %s", report["passed"])
    if report["missing_expected_relations"]:
        logger.info(
            "Missing expected relations: %s",
            report["missing_expected_relations"],
        )

    return 0 if bool(report["passed"]) else 2


def main() -> int:
    args = _parse_args()
    _configure_logging(verbose=args.verbose, provider_debug=args.provider_debug)
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
