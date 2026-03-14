"""Graph-core contracts for extraction payload shaping."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractionCompactRecordRule:
    """Pack-owned compact-record shaping rules for one extraction source type."""

    fields: tuple[str, ...]
    chunk_fields: tuple[str, ...] | None = None
    chunk_indicator_field: str | None = None
    fallback_text_field: str | None = None

    def fields_for_chunk_scope(self, *, is_chunk_scope: bool) -> tuple[str, ...]:
        if is_chunk_scope and self.chunk_fields is not None:
            return self.chunk_fields
        return self.fields


@dataclass(frozen=True)
class ExtractionPayloadConfig:
    """Pack-owned payload shaping config for extraction adapters."""

    compact_record_rules: dict[str, ExtractionCompactRecordRule]

    def compact_record_rule_for(
        self,
        source_type: str,
    ) -> ExtractionCompactRecordRule | None:
        return self.compact_record_rules.get(source_type)
