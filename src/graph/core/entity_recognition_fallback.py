"""Graph-core contracts for heuristic entity-recognition fallback behavior."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntityRecognitionHeuristicFieldMap:
    """Pack-owned fallback field mappings for source-specific entity heuristics."""

    source_type_fields: dict[str, dict[str, tuple[str, ...]]]
    default_source_type: str
    primary_entity_types: dict[str, str]

    def field_keys_for(self, source_type: str, field: str) -> tuple[str, ...]:
        source_mapping = self.source_type_fields.get(
            source_type,
            self.source_type_fields[self.default_source_type],
        )
        return source_mapping.get(field, ())

    def primary_entity_type_for(self, source_type: str) -> str:
        return self.primary_entity_types.get(
            source_type,
            self.primary_entity_types[self.default_source_type],
        )
