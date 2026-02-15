"""
Kernel domain entities (Layer 0/1 core graph + dictionary concepts).

These are domain-level representations of the kernel tables (dictionary, entities,
observations, relations, provenance). They intentionally do NOT depend on
SQLAlchemy models so that the domain layer remains infrastructure-agnostic.
"""

from .dictionary import (
    DictionaryChangelog,
    DictionaryDataType,
    DictionaryDomainContext,
    DictionaryEntityType,
    DictionaryRelationType,
    DictionarySearchResult,
    DictionarySensitivityLevel,
    EntityResolutionPolicy,
    RelationConstraint,
    TransformRegistry,
    ValueSet,
    ValueSetItem,
    VariableDefinition,
    VariableSynonym,
)
from .entities import KernelEntity, KernelEntityIdentifier
from .observations import KernelObservation
from .provenance import KernelProvenanceRecord
from .relations import KernelRelation

__all__ = [
    "DictionaryChangelog",
    "DictionaryDataType",
    "DictionaryDomainContext",
    "DictionaryEntityType",
    "DictionaryRelationType",
    "DictionarySearchResult",
    "DictionarySensitivityLevel",
    "EntityResolutionPolicy",
    "KernelEntity",
    "KernelEntityIdentifier",
    "KernelObservation",
    "KernelProvenanceRecord",
    "KernelRelation",
    "RelationConstraint",
    "TransformRegistry",
    "ValueSet",
    "ValueSetItem",
    "VariableDefinition",
    "VariableSynonym",
]
