"""
Dictionary repository interface.

Defines the abstract contract for reads/writes to the Layer 1
dictionary tables: variable_definitions, variable_synonyms,
transform_registry, entity_resolution_policies, and relation_constraints.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.database.kernel.dictionary import (
        EntityResolutionPolicyModel,
        RelationConstraintModel,
        TransformRegistryModel,
        VariableDefinitionModel,
    )
    from src.type_definitions.common import JSONObject


class DictionaryRepository(ABC):
    """
    Read/write interface for the kernel dictionary (Layer 1).

    The dictionary is the single source of truth for what data elements
    are allowed, how they relate, and how entities are deduplicated.
    """

    # ── Variable definitions ──────────────────────────────────────────

    @abstractmethod
    def get_variable(self, variable_id: str) -> VariableDefinitionModel | None:
        """Retrieve a single variable definition by ID."""

    @abstractmethod
    def find_variables(
        self,
        *,
        domain_context: str | None = None,
        data_type: str | None = None,
    ) -> list[VariableDefinitionModel]:
        """List variable definitions, optionally filtered by domain and/or type."""

    @abstractmethod
    def find_variable_by_synonym(
        self,
        synonym: str,
    ) -> VariableDefinitionModel | None:
        """
        Resolve a field name to its canonical variable definition.

        Looks up the synonym in ``variable_synonyms`` and returns
        the parent ``VariableDefinitionModel`` if found.
        """

    @abstractmethod
    def create_variable(  # noqa: PLR0913
        self,
        *,
        variable_id: str,
        canonical_name: str,
        display_name: str,
        data_type: str,
        domain_context: str = "general",
        sensitivity: str = "INTERNAL",
        preferred_unit: str | None = None,
        constraints: JSONObject | None = None,
        description: str | None = None,
    ) -> VariableDefinitionModel:
        """Create a new variable definition."""

    # ── Entity resolution policies ────────────────────────────────────

    @abstractmethod
    def get_resolution_policy(
        self,
        entity_type: str,
    ) -> EntityResolutionPolicyModel | None:
        """Get the resolution policy for a given entity type."""

    @abstractmethod
    def find_resolution_policies(self) -> list[EntityResolutionPolicyModel]:
        """List all entity resolution policies."""

    # ── Relation constraints ──────────────────────────────────────────

    @abstractmethod
    def get_constraints(
        self,
        *,
        source_type: str | None = None,
        relation_type: str | None = None,
    ) -> list[RelationConstraintModel]:
        """List relation constraints, optionally filtered."""

    @abstractmethod
    def is_triple_allowed(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        """Check if a (source_type, relation_type, target_type) triple is allowed."""

    @abstractmethod
    def requires_evidence(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        """Check if the given triple requires evidence."""

    # ── Transform registry ────────────────────────────────────────────

    @abstractmethod
    def get_transform(
        self,
        input_unit: str,
        output_unit: str,
    ) -> TransformRegistryModel | None:
        """Find a unit transformation between input and output units."""

    @abstractmethod
    def find_transforms(
        self,
        *,
        status: str = "ACTIVE",
    ) -> list[TransformRegistryModel]:
        """List all transforms, optionally filtered by status."""


__all__ = ["DictionaryRepository"]
