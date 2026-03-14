"""Pack-owned entity-recognition bootstrap contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.type_definitions.common import JSONValue


@dataclass(frozen=True)
class BootstrapRelationTypeDefinition:
    relation_type: str
    display_name: str
    description: str
    is_directional: bool
    inverse_label: str | None


@dataclass(frozen=True)
class BootstrapRelationConstraintDefinition:
    source_type: str
    relation_type: str
    target_type: str
    requires_evidence: bool


@dataclass(frozen=True)
class BootstrapVariableDefinition:
    variable_id: str
    canonical_name: str
    display_name: str
    data_type: str
    description: str
    constraints: dict[str, JSONValue] | None
    synonyms: tuple[str, ...]


@dataclass(frozen=True)
class DomainBootstrapEntityTypes:
    domain_context: str
    entity_types: tuple[str, ...]


@dataclass(frozen=True)
class EntityRecognitionBootstrapConfig:
    default_relation_type: str
    default_relation_display_name: str
    default_relation_description: str
    default_relation_inverse_label: str | None
    interaction_relation_type: str
    interaction_relation_display_name: str
    interaction_relation_description: str
    interaction_relation_inverse_label: str | None
    min_entity_types_for_default_relation: int
    interaction_entity_types: tuple[str, ...]
    domain_entity_types: tuple[DomainBootstrapEntityTypes, ...]
    source_types_with_publication_baseline: tuple[str, ...]
    publication_baseline_source_label: str
    publication_baseline_entity_description: str
    publication_baseline_entity_types: tuple[str, ...]
    publication_baseline_relation_types: tuple[BootstrapRelationTypeDefinition, ...]
    publication_baseline_constraints: tuple[BootstrapRelationConstraintDefinition, ...]
    publication_metadata_variables: tuple[BootstrapVariableDefinition, ...]
