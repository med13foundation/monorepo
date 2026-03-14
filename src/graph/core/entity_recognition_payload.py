"""Graph-core contracts for entity-recognition payload shaping."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntityRecognitionCompactRecordRule:
    """Pack-owned compact-record shaping rules for one source type."""

    fields: tuple[str, ...]
    preferred_text_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class EntityRecognitionPayloadConfig:
    """Pack-owned payload shaping config for entity-recognition adapters."""

    compact_record_rules: dict[str, EntityRecognitionCompactRecordRule]

    def compact_record_rule_for(
        self,
        source_type: str,
    ) -> EntityRecognitionCompactRecordRule | None:
        return self.compact_record_rules.get(source_type)
