"""Shared payload/prompt helpers for extraction adapters."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.infrastructure.llm.prompts import extraction as extraction_prompts
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.domain.agents.contexts.extraction_context import ExtractionContext

DEFAULT_EXTRACTION_USAGE_MAX_TOKENS = 65536
ENV_EXTRACTION_USAGE_MAX_TOKENS = "MED13_EXTRACTION_USAGE_MAX_TOKENS"

_TEMPORAL_FIELD_NAMES = frozenset(
    {
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
        "processed_at",
        "published_at",
        "observed_at",
        "fetched_at",
    },
)
_MAX_CONTEXT_ENTITY_CANDIDATES = 12
_MAX_CONTEXT_OBSERVATION_CANDIDATES = 12
_ESCAPED_NULL_SEQUENCE_PATTERN = re.compile(r"\\+(?:u0000|x00)", re.IGNORECASE)


def get_extraction_system_prompt(source_type: str) -> str:
    if source_type == "pubmed":
        return (
            f"{extraction_prompts.PUBMED_EXTRACTION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{extraction_prompts.PUBMED_EXTRACTION_SYNTHESIS_SYSTEM_PROMPT}"
        )
    return (
        f"{extraction_prompts.CLINVAR_EXTRACTION_DISCOVERY_SYSTEM_PROMPT}\n\n"
        f"{extraction_prompts.CLINVAR_EXTRACTION_SYNTHESIS_SYSTEM_PROMPT}"
    )


def build_extraction_prompt(
    *,
    source_type: str,
    context: ExtractionContext,
    relation_governance_mode: str,
) -> str:
    return (
        f"{get_extraction_system_prompt(source_type)}\n\n"
        "---\n"
        "REQUEST CONTEXT\n"
        "---\n"
        f"RELATION GOVERNANCE MODE: {relation_governance_mode}\n"
        f"{build_extraction_input_text(context)}"
    )


def build_extraction_input_text(context: ExtractionContext) -> str:
    entity_candidates = sorted(
        context.recognized_entities,
        key=lambda candidate: candidate.confidence,
        reverse=True,
    )[:_MAX_CONTEXT_ENTITY_CANDIDATES]
    observation_candidates = sorted(
        context.recognized_observations,
        key=lambda candidate: candidate.confidence,
        reverse=True,
    )[:_MAX_CONTEXT_OBSERVATION_CANDIDATES]
    compact_raw_record = sanitize_json_value(build_compact_raw_record(context))
    entity_payloads = [
        sanitize_json_value(entity.model_dump(mode="json"))
        for entity in entity_candidates
    ]
    observation_payloads = [
        sanitize_json_value(observation.model_dump(mode="json"))
        for observation in observation_candidates
    ]
    serialized_raw_record = json.dumps(compact_raw_record, default=str)
    serialized_entities = json.dumps(entity_payloads, default=str)
    serialized_observations = json.dumps(observation_payloads, default=str)
    return (
        f"SOURCE TYPE: {context.source_type}\n"
        f"DOCUMENT ID: {context.document_id}\n"
        f"RESEARCH SPACE ID: {context.research_space_id or 'none'}\n"
        f"SHADOW MODE: {context.shadow_mode}\n\n"
        f"RAW RECORD JSON:\n{serialized_raw_record}\n\n"
        f"RECOGNIZED ENTITIES:\n{serialized_entities}\n\n"
        f"RECOGNIZED OBSERVATIONS:\n{serialized_observations}"
    )


def sanitize_json_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, str):
        return to_json_value(sanitize_text_value(value))
    return to_json_value(value)


def sanitize_text_value(value: str) -> str:
    without_raw_null = value.replace("\x00", "")
    return _ESCAPED_NULL_SEQUENCE_PATTERN.sub("", without_raw_null)


def build_compact_raw_record(context: ExtractionContext) -> dict[str, object]:
    raw_record = context.raw_record
    source_type = context.source_type.strip().lower()
    if source_type == "pubmed":
        is_chunk_scope = raw_record.get("full_text_chunk_index") is not None
        allowed_fields: tuple[str, ...] = (
            (
                "pubmed_id",
                "title",
                "doi",
                "source",
                "full_text",
                "full_text_source",
                "full_text_chunk_index",
                "full_text_chunk_total",
                "full_text_chunk_start_char",
                "full_text_chunk_end_char",
            )
            if is_chunk_scope
            else (
                "pubmed_id",
                "title",
                "abstract",
                "full_text",
                "keywords",
                "journal",
                "publication_date",
                "publication_types",
                "doi",
                "source",
                "full_text_source",
                "full_text_chunk_index",
                "full_text_chunk_total",
                "full_text_chunk_start_char",
                "full_text_chunk_end_char",
            )
        )
        compact: dict[str, object] = {}
        for field in allowed_fields:
            value = raw_record.get(field)
            if value is None:
                continue
            compact[field] = to_json_value(value)
        if "full_text" not in compact and isinstance(raw_record.get("text"), str):
            compact["text"] = raw_record["text"]
        return compact
    if source_type == "clinvar":
        clinvar_fields: tuple[str, ...] = (
            "variation_id",
            "gene_symbol",
            "variant_name",
            "clinical_significance",
            "condition_name",
            "review_status",
            "submission_count",
            "source",
        )
        compact = {}
        for field in clinvar_fields:
            value = raw_record.get(field)
            if value is None:
                continue
            compact[field] = to_json_value(value)
        return compact
    return {str(key): to_json_value(value) for key, value in raw_record.items()}


def normalize_temporal_context(payload: dict[str, object]) -> dict[str, object]:
    return {
        str(key): normalize_temporal_value(key=str(key), value=value)
        for key, value in payload.items()
    }


def normalize_temporal_value(*, key: str, value: object) -> object:
    if isinstance(value, dict):
        return {
            str(child_key): normalize_temporal_value(
                key=str(child_key),
                value=child_value,
            )
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [normalize_temporal_value(key=key, value=item) for item in value]
    if isinstance(value, str):
        sanitized = sanitize_text_value(value)
        if key in _TEMPORAL_FIELD_NAMES:
            coerced = coerce_utc_iso_datetime(sanitized)
            return coerced if coerced is not None else sanitized
        return to_json_value(sanitized)
    if isinstance(value, datetime):
        coerced = coerce_utc_iso_datetime(value)
        return coerced if coerced is not None else value.isoformat()
    return to_json_value(value)


def coerce_utc_iso_datetime(raw_value: str | datetime) -> str | None:
    parsed: datetime
    if isinstance(raw_value, datetime):
        parsed = raw_value
    else:
        normalized = raw_value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return parsed.isoformat()


__all__ = [
    "DEFAULT_EXTRACTION_USAGE_MAX_TOKENS",
    "ENV_EXTRACTION_USAGE_MAX_TOKENS",
    "build_compact_raw_record",
    "build_extraction_input_text",
    "build_extraction_prompt",
    "coerce_utc_iso_datetime",
    "get_extraction_system_prompt",
    "normalize_temporal_context",
    "normalize_temporal_value",
    "sanitize_json_value",
    "sanitize_text_value",
]
